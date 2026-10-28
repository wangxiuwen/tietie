# 方向192 真机验证：大图浮层右键直接复制图片
# 剧本（合成点击开大图 → 可信右键 → OS 剪贴板位图断言，结束全还原）：
#   img: 过滤 → 点首图开 zoom 层 → meta 文案含「右键复制」提示
#   → 剪贴板快照（文本）→ 可信右键（mousePressed/Released button=right）
#   → meta 出现 ✓ 已复制；Get-Clipboard -Format Image 非空（真位图入板）
#   → Esc 关层 + 还原文本剪贴板
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


def clip_text():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                         capture_output=True)
    return out.stdout.decode("gbk", "replace").rstrip("\r\n")


def clip_has_image():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "if (Get-Clipboard -Format Image) { 'IMG' } else { 'NO' }"],
        capture_output=True)
    return out.stdout.decode("gbk", "replace").strip()


# 开局清场：关残留浮层 + 清残留查询
d.eval(r"""(() => {
  const z = document.querySelector('.zoom-overlay');
  if (z) window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
})()""")
time.sleep(0.3)
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, 'img:');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
time.sleep(0.6)

pos = json.loads(d.eval(r"""(() => {
  const c = document.querySelector('.cards [data-idx="0"]');
  if (!c) return 'NOCARD';
  const r = c.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 80)});
})()"""))
assert pos != "NOCARD"
for typ in ("mousePressed", "mouseReleased"):
    d.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                          "params": {"type": typ, "button": "left",
                                     "buttons": 1 if typ == "mousePressed" else 0,
                                     "clickCount": 1, "x": pos["x"], "y": pos["y"]}}))
    d.ws.recv_text()
    time.sleep(0.12)
time.sleep(1.0)

meta = d.eval(r"""(() => {
  const m = document.querySelector('.zoom-meta');
  return m ? m.textContent : 'NOZOOM';
})()""")
print("meta:", meta)
assert meta != "NOZOOM" and "右键复制" in meta, "zoom 层未开或缺右键复制提示"

snap = clip_text()
print("clipboard snapshot:", repr(snap[:40]))

# 可信右键打在大图本体中心
imgc = json.loads(d.eval(r"""(() => {
  const i = document.querySelector('.zoom-img');
  if (!i) return 'NOIMG';
  const r = i.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2});
})()"""))
assert imgc != "NOIMG"
for typ in ("mousePressed", "mouseReleased"):
    d.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchMouseEvent",
                          "params": {"type": typ, "button": "right",
                                     "buttons": 2 if typ == "mousePressed" else 0,
                                     "clickCount": 1, "x": imgc["x"], "y": imgc["y"]}}))
    d.ws.recv_text()
    time.sleep(0.12)
time.sleep(0.8)

meta2 = d.eval(r"""document.querySelector('.zoom-meta')?.textContent ?? 'GONE'""")
print("meta after right-click:", meta2)
assert "已复制" in meta2, "✓ 反馈未出现"
assert clip_has_image() == "IMG", "OS 剪贴板无位图（复制未落板）"
assert d.eval("document.querySelector('.zoom-overlay') ? 'y' : 'n'") == "y", \
    "右键误关浮层"

# Esc 关层 + 还原文本剪贴板
for typ in ("keyDown", "keyUp"):
    d.ws.send(json.dumps({"id": 9903, "method": "Input.dispatchKeyEvent",
                          "params": {"type": typ, "key": "Escape", "code": "Escape",
                                     "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27}}))
    d.ws.recv_text()
    time.sleep(0.1)
time.sleep(0.4)
assert d.eval("document.querySelector('.zoom-overlay') ? 'n' : 'y'") == "y", "层未关"
subprocess.run(["powershell", "-NoProfile", "-Command",
                f"Set-Clipboard -Value {json.dumps(snap)}"], capture_output=True)
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
print("PASS: 右键复制 → ✓ 反馈 + OS 剪贴板位图在板 + 浮层不误关 + 全还原")
