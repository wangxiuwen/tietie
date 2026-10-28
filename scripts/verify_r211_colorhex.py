# 方向211 真机验证：颜色卡双击直接复制 hex（无视双击偏好设置）
# 剧本（可信双击 + OS 剪贴板对照，结束快照还原）：
#   记双击偏好现值（产品路径读取）→ 色卡可信双击
#   → Get-Clipboard == 该卡 hex（当前偏好即使是 paste 也复制）
#   → 控制组：文本卡双击走当前偏好（paste 时不入剪贴板文本或走回粘——
#     只断言剪贴板 ≠ 文本卡内容即未盲复制）
#   → 偏好不改动（读现值即可，无需写）
import json
import subprocess
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


def clip():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                         capture_output=True)
    return out.stdout.decode("gbk", "replace").rstrip("\r\n")


def set_clip(text):
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Set-Clipboard -Value '{text}'"], capture_output=True)


# 基线：色卡过滤 + 读双击偏好
pref = d.eval(r"""(async () => await window.__TAURI_INTERNALS__.invoke('dblclick_action'))()""")
print("dblclick preference:", pref)
snap = clip()
print("clipboard snapshot:", repr(snap[:40]))

# 色卡过滤：点「颜色」Tab（比 color: 前缀少一次捕获时序依赖）
d.eval(r"""(() => {
  const tabs = [...document.querySelectorAll('.type-tabs .tab')];
  const color = tabs.find(t => t.textContent.startsWith('颜色') || t.textContent.startsWith('Color'));
  if (color) color.click();
})()""")
time.sleep(0.6)


# 抽屉窗拉高（卡在折叠线下，文档无滚动容器——R156 同族坑）
ORIG = d.eval(r"""(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('plugin:window|inner_size')))()""")
d.eval(r"""(async () => {
  await window.__TAURI_INTERNALS__.invoke('plugin:window|set_size',
    { value: { Logical: { width: 1280, height: 760 } } });
})()""")
time.sleep(0.5)


def dbl_click_card(idx):
    pos = json.loads(d.eval(rf"""(() => {{
  const c = document.querySelector('.cards [data-idx="{idx}"]');
  if (!c) return 'NOCARD';
  c.scrollIntoView({{block: 'nearest'}});
  const r = c.getBoundingClientRect();
  return JSON.stringify({{x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 50)}});
}})()"""))
    assert pos != "NOCARD"
    for typ, cnt in (("mousePressed", 1), ("mouseReleased", 1),
                     ("mousePressed", 2), ("mouseReleased", 2)):
        d.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                              "params": {"type": typ, "button": "left",
                                         "buttons": 1 if typ == "mousePressed" else 0,
                                         "clickCount": cnt,
                                         "x": pos["x"], "y": pos["y"]}}))
        d.ws.recv_text()
        time.sleep(0.1)
    time.sleep(1.0)


# 色卡 hex（桥侧预取期望值）
hexes = json.loads(d.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 30}))
    .filter(x => x.kind === 'color').map(x => x.content)))()"""))
assert hexes, "无颜色条目"
want = hexes[0]
print("expect hex:", want)

set_clip("R211基线哨兵-勿动")
dbl_click_card(0)
got = clip()
print("clipboard after color dblclick:", got)
assert got == want, f"色卡双击未复制 hex: {got!r} != {want!r}"

# 控制组：文本卡双击（偏好 paste 时走回粘，剪贴板不含原文本）
d.eval(r"""(() => {
  const tabs = [...document.querySelectorAll('.type-tabs .tab')];
  const text = tabs.find(t => t.textContent.startsWith('文本') || t.textContent.startsWith('Text'));
  if (text) text.click();
})()""")
time.sleep(0.6)
texts = json.loads(d.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 30}))
    .filter(x => x.kind === 'text').map(x => x.content)))()"""))
t0 = texts[0]
set_clip("R211哨兵2")
dbl_click_card(0)
got2 = clip()
print("clipboard after text dblclick:", repr(got2[:40]), "| pref:", pref)
if pref == "copy":
    assert got2 == t0, "copy 偏好下文本卡未复制"
else:
    # paste/edit 偏好：不盲复制（edit 开编辑器、paste 回粘文本——后者会把
    # 文本写回剪贴板！paste(it) 调 paste_item 写剪贴板。故此断言仅对 edit
    assert got2 != t0 or pref == "paste", "edit 偏好下文本卡被误复制"

# 还原：剪贴板 + 窗口尺寸
set_clip(snap)
sz = json.loads(ORIG)
d.eval(rf"""(async () => {{
  await window.__TAURI_INTERNALS__.invoke('plugin:window|set_size',
    {{ value: {{ Physical: {{ width: {sz["width"]}, height: {sz["height"]} }} }} }});
}})()""")
print("PASS: 色卡双击=复制 hex（无视偏好），控制组行为随偏好，剪贴板还原")
