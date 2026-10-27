# 方向165 真机验证：搜索无结果空态轮换使用技巧
# 剧本（合成输入 + DOM 断言，结束清空查询还原）：
#   注入无结果查询 → .empty-tip 出现且内容 ∈ 五条技巧集
#   → 清空→再无结果 → 技巧变化（轮换）；出现有结果查询时无空态
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
TIPS = {
    "试试 text: / img: / link: 前缀按类型过滤",
    "空格分隔多个词是 AND 搜索，-词 可排除",
    "拼音首字母也能搜：nz 匹配「内存」",
    "⌘/Ctrl+数字 快速复制托盘前 10 条",
    "右键卡片可置顶 / 编辑 / 挂到晾衣架",
}

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and (t["url"].endswith("/") or "view=" not in t["url"]))
d = CDP(ws_url)
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)


def set_query(q):
    got = d.eval(rf"""(() => {{
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, {json.dumps(q)});
  i.dispatchEvent(new Event('input', {{bubbles: true}}));
  return i.value;
}})()""")
    assert got == q, f"注入失败: {got!r}"
    time.sleep(0.5)


def read_tip():
    out = d.eval(r"""(() => {
  const el = document.querySelector('.empty-tip');
  const cards = document.querySelectorAll('.cards [data-idx]').length;
  return JSON.stringify({tip: el ? el.textContent.trim() : null, cards});
})()""")
    return json.loads(out)


def miss():
    return f"zzz绝对无结果{int(time.time() * 1000) % 1000000}"


set_query(miss())
r1 = read_tip()
print("miss#1:", r1)
assert r1["cards"] == 0 and r1["tip"], "空态或技巧未出现"
assert r1["tip"].startswith("💡 ") and r1["tip"][2:] in TIPS, f"技巧不在集合内: {r1['tip']}"

set_query("")
time.sleep(0.3)
set_query(miss())
r2 = read_tip()
print("miss#2:", r2)
assert r2["tip"] and r2["tip"] != r1["tip"], "两次进入空态技巧未轮换"
assert r2["tip"][2:] in TIPS, f"技巧不在集合内: {r2['tip']}"

# 有结果查询时不出现空态（也无技巧行）
set_query("text:")
r3 = read_tip()
print("text: hit:", r3)
assert r3["cards"] > 0 and r3["tip"] is None, "有结果时不应出现空态技巧"

set_query("")
print("PASS: 无结果空态轮换技巧、两miss不同条、有结果无空态，查询已清空还原")
