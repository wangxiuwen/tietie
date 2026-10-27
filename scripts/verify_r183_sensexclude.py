# 方向183 真机验证：抽屉搜索排除遮蔽敏感卡（不泄内容与计数）
# 剧本（产品命令标记敏感 + DOM 断言，结束全还原）：
#   记基线可见卡数 N（无查询）
#   → set_item_sensitive(itemA, true)（A 内容含独特词 W）
#   → 注入查询 W → 断言：0 结果（空态在位，无敏感卡、无计数泄）
#   → 注入一个匹配非敏感卡的词 → 正常出卡（搜索本身未坏）
#   → 清查询 → A 以遮蔽态回到列表（🔒 卡不消失于浏览）
#   → set_item_sensitive(A, false) 还原
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and (t["url"].endswith("/") or "view=" not in t["url"]))
d = CDP(ws_url)
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)


def inv(cmd, args=None):
    out = d.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} type")
    return json.loads(out)


def set_query(q):
    got = d.eval(rf"""(() => {{
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, {json.dumps(q)});
  i.dispatchEvent(new Event('input', {{bubbles: true}}));
  return i.value;
}})()""")
    assert got == q, got
    time.sleep(0.6)


def cards():
    return int(d.eval("document.querySelectorAll('.cards [data-idx]').length"))


# 选一个非敏感条目，临时改内容为独特词（产品路径，结束还原内容+敏感位）
items = inv("list_items", {"limit": 50})
target = next(x for x in items if not x.get("sensitive"))
orig_content = target["content"]
W = "R183sensitive词"
inv("update_item_content", {"id": target["id"], "content": W})
time.sleep(0.6)
inv("set_item_sensitive", {"id": target["id"], "on": True})
time.sleep(0.8)

n0 = cards()
print("baseline cards (no query):", n0)
set_query(W)
n1 = cards()
empty = d.eval("document.querySelector('.empty') ? 'y' : 'n'")
print(f"query[{W}]: cards={n1} empty={empty}")
assert n1 == 0 and empty == "y", f"敏感卡泄入搜索结果: {n1}"

# 控制组：普通词仍正常搜索
ctrl = inv("list_items", {"limit": 50})
normal = next((x for x in ctrl if not x.get("sensitive") and x["kind"] == "text"
               and len(x["content"]) >= 4), None)
assert normal, "无可用对照条目"
word = normal["content"].strip()[:3]
set_query(word)
n2 = cards()
print(f"query[{word}]: cards={n2}")
assert n2 > 0, "搜索整体坏了（控制组失败）"

# 清查询 → 敏感卡以遮蔽态回列表
set_query("")
n3 = cards()
masked = d.eval("document.querySelector('.cards .lock') ? 'y' : 'n'")
print("no query: cards=", n3, "| masked lock present:", masked)
assert n3 == n0 and masked == "y", f"浏览态异常: {n3} vs {n0}, lock={masked}"

# 还原：摘敏感 + 恢复原内容
inv("set_item_sensitive", {"id": target["id"], "on": False})
inv("update_item_content", {"id": target["id"], "content": orig_content})
time.sleep(0.6)
final = next(x for x in inv("list_items", {"limit": 50}) if x["id"] == target["id"])
assert not final.get("sensitive") and final["content"] == orig_content, "还原失败"
print("PASS: 敏感卡不泄入搜索（0 结果零计数）、普通搜索不受影响、浏览态遮蔽在位、全还原")
