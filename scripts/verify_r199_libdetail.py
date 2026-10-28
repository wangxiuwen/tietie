# 方向199 真机验证：Library 行双击进详情浮层（图片行=原图，文本行=复制不变）
# 剧本（可信双击 + DOM 断言，结束 Esc 关浮层）：
#   过滤/定位首个图片行 → 可信双击 → .zoom-overlay 出现且 .zoom-img 加载
#     （blob 原图 naturalWidth>0）
#   → Esc 关闭浮层
#   → 文本行可信双击 → 无浮层 + lib-msg 显示已复制（120 回归）
import json
import subprocess
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


lib = CDP(page_ws(lambda u: "view=library" in u))
lib.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); '
         'await window.__TAURI_INTERNALS__.invoke("plugin:window|set_focus"); })()')
time.sleep(0.8)
lib.eval(r"""(async () => {
  await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 1});
  window.dispatchEvent(new Event('library-open'));
  window.dispatchEvent(new Event('clipboard-changed'));
})()""")
time.sleep(0.6)

snap = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                      capture_output=True).stdout.decode("gbk", "replace").rstrip("\r\n")


def dblclick(x, y):
    for typ, cnt in (("mousePressed", 1), ("mouseReleased", 1),
                     ("mousePressed", 2), ("mouseReleased", 2)):
        lib.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                                "params": {"type": typ, "button": "left",
                                           "buttons": 1 if typ == "mousePressed" else 0,
                                           "clickCount": cnt, "x": x, "y": y}}))
        lib.ws.recv_text()
        time.sleep(0.1)
    time.sleep(1.0)


# ── 图片行：双击开原图浮层 ──
img_row = json.loads(lib.eval(r"""(() => {
  const rows = [...document.querySelectorAll('tbody tr')];
  const r0 = rows.find(r => r.querySelector('.badge.image'));
  if (!r0) return 'NOROW';
  const r = r0.getBoundingClientRect();
  return JSON.stringify({x: r.x + 80, y: r.y + r.height / 2});
})()"""))
print("image row at:", img_row)
assert img_row != "NOROW", "无图片行"

dblclick(img_row["x"], img_row["y"])
ov = json.loads(lib.eval(r"""(() => {
  const ov = document.querySelector('.zoom-overlay');
  const img = ov?.querySelector('.zoom-img') ?? null;
  return JSON.stringify({open: !!ov, img: !!img,
    loaded: img ? (img.complete && img.naturalWidth > 0) : false,
    src: img ? img.src.slice(0, 30) : null});
})()"""))
print("overlay:", ov)
assert ov["open"] and ov["img"] and ov["loaded"], f"图片详情浮层异常: {ov}"

# Esc 关闭
for typ in ("keyDown", "keyUp"):
    lib.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchKeyEvent",
                            "params": {"type": typ, "key": "Escape", "code": "Escape",
                                       "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27}}))
    lib.ws.recv_text()
    time.sleep(0.1)
time.sleep(0.5)
closed = lib.eval("document.querySelector('.zoom-overlay') ? 'n' : 'y'")
assert closed == "y", "Esc 未关浮层"

# ── 文本行：双击仍是复制（120 回归） ──
txt_row = json.loads(lib.eval(r"""(() => {
  const rows = [...document.querySelectorAll('tbody tr')];
  const r0 = rows.find(r => r.querySelector('.badge.text'));
  if (!r0) return 'NOROW';
  const r = r0.getBoundingClientRect();
  return JSON.stringify({x: r.x + 80, y: r.y + r.height / 2,
    text: r0.querySelector('.lib-row-text').textContent.trim().slice(0, 20)});
})()"""))
assert txt_row != "NOROW", "无文本行"
print("text row:", txt_row)

dblclick(txt_row["x"], txt_row["y"])
no_ov = lib.eval("document.querySelector('.zoom-overlay') ? 'n' : 'y'")
msg = lib.eval(r"""document.querySelector('.lib-msg')?.textContent ?? ''""")
print("no overlay:", no_ov, "| msg:", msg[:30])
assert no_ov == "y", "文本行误开浮层"
assert "已复制" in msg or "copied" in msg.lower(), f"复制反馈缺失: {msg!r}"

# 还原剪贴板
subprocess.run(["powershell", "-NoProfile", "-Command",
                f"Set-Clipboard -Value '{snap}'"], capture_output=True)
print("PASS: 图片行双击开原图详情（blob 加载实宽>0）、Esc 关闭；文本行双击复制不变（120 回归）")
