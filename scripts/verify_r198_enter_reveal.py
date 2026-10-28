# 方向198 真机验证：🔒 卡 Enter 先显形再粘贴（盲粘不泄密）
# 剧本（产品命令标记敏感 → 键盘选中 → 双 Enter 观测剪贴板，结束全还原）：
#   造唯一文本探针（Set-Clipboard 原始串，时间戳唯一）→ set_item_sensitive
#   → 抽屉定位该卡（search 唯一词）→ 选中它（click 或 ArrowDown 到 idx0）
#   → 第一次 Enter：断言剪贴板【不含】探针（被遮蔽拦截）+ 卡已显形
#   → 第二次 Enter：剪贴板 == 探针（显形窗口内放行）
#   → 还原：摘敏感、剪贴板快照恢复
import json
import subprocess
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
TS = int(time.time())
PROBE = f"R198sensitive探针{TS}"

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


def clip():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                         capture_output=True)
    return out.stdout.decode("gbk", "replace").rstrip("\r\n")


def set_clip(text):
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Set-Clipboard -Value '{text}'"], capture_output=True)


def key(k, code, vk, mods=0):
    for typ in ("keyDown", "keyUp"):
        d.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchKeyEvent",
                              "params": {"type": typ, "key": k, "code": code,
                                         "windowsVirtualKeyCode": vk,
                                         "nativeVirtualKeyCode": vk,
                                         "modifiers": mods}}))
        d.ws.recv_text()
    time.sleep(0.4)


def set_query(q):
    got = d.eval(rf"""(() => {{
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, {json.dumps(q)});
  i.dispatchEvent(new Event('input', {{bubbles: true}}));
  return i.value;
}})()""")
    assert got == q, got
    time.sleep(0.5)


# 开局：清残留 R198 探针 + 快照剪贴板
for it in inv("list_items", {"limit": 50}):
    if it["content"].startswith("R198sensitive"):
        inv("delete_item", {"id": it["id"]})
time.sleep(0.5)
snap = clip()

# 造探针（原始中文串直传，等产品捕获入库）
set_clip(PROBE)
pid = None
for _ in range(20):
    time.sleep(1)
    found = [x["id"] for x in inv("list_items", {"limit": 10})
             if x["content"] == PROBE]
    if found:
        pid = found[0]
        break
assert pid, "探针未入库"
print("probe id:", pid)
# 入库后立即还原剪贴板快照（造探针的 Set-Clipboard 会污染后续 Enter 检查）
set_clip(snap)
time.sleep(0.5)

# 标记敏感 + 清查询重开抽屉刷新
inv("set_item_sensitive", {"id": pid, "on": True})
set_query("")
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)

# 唯一词搜索定位该卡（敏感卡被搜索排除？——方向 183 排除的是 search！
# 敏感卡不入搜索结果，所以不能用 query 定位；改走 tab/全量列表 idx 定位）
# 用桥排位：敏感后 used_at 不变，重新拉全量找它的排位
items = inv("list_items", {"limit": 200})
pos = next(i for i, x in enumerate(items) if x["id"] == pid)
print("probe pos in list:", pos)
# 抽屉渲染全部 items（无查询），data-idx 对应 filtered 顺序 = 列表顺序
# 键盘选中：show_drawer 后 selectedIdx=0，ArrowDown×pos 精确走位
#（焦点在搜索框时 ArrowDown 会被搜索历史召回（方向126）拦截——先 blur）
#（卡在视口外时可信点击打不中——scrollIntoView 对 .cards 滚动容器无效）
d.eval(r"""(() => { const el = document.activeElement; if (el && el.blur) el.blur(); })()""")
time.sleep(0.3)
for _ in range(pos):
    key("ArrowDown", "ArrowDown", 40)
time.sleep(0.4)
selected = d.eval(rf"""(() => {{
  const c = document.querySelector('.cards [data-idx="{pos}"]');
  return c && c.className.includes('selected') ? 'y' : 'n';
}})()""") == "y"
assert selected, "ArrowDown 走位未选中目标卡"

# 第一次 Enter：应显形而非粘贴（剪贴板不含探针）
key("Enter", "Enter", 13)
time.sleep(0.8)
c1 = clip()
revealed = json.loads(d.eval(rf"""(() => {{
  const c = document.querySelector('.cards [data-idx="{pos}"]');
  return JSON.stringify({{sel: c?.className.includes('selected'),
    masked: !!c?.querySelector('.lock') && !c?.textContent.includes('{PROBE[:8]}')}});
}})()"""))
print("after Enter#1: clipboard has probe =", PROBE[:6] in c1, "| card:", revealed)
assert PROBE[:6] not in c1, "第一次 Enter 就把密文粘出去了（遮蔽失效）"
assert revealed["sel"], "卡未被选中（Enter 作用对象错）"

# 第二次 Enter：显形窗口内放行 → 剪贴板 == 探针
key("Enter", "Enter", 13)
time.sleep(0.9)
c2 = clip()
print("after Enter#2: clipboard == probe =", c2 == PROBE)
assert c2 == PROBE, f"第二次 Enter 未粘贴: {c2[:30]!r}"

# 还原
inv("set_item_sensitive", {"id": pid, "on": False})
inv("delete_item", {"id": pid})
set_clip(snap)
print("PASS: Enter#1 显形不粘（密文不泄）→ Enter#2 显形窗口内粘贴，全还原")
