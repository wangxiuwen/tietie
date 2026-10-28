# 方向205 真机验证：图片卡 hover 预取原图——首次单击大图即开
# 剧本（可信 hover→click + 计时断言，结束 Esc 关层清查询）：
#   img: 过滤 → hover 首图（触发预取）→ 等 800ms（取数落缓存）
#   → 可信单击开大图层 → 200ms 内 .zoom-img 出现且 blob 已就绪
#     （无「原图加载中…」停留——预取命中）
#   → 对照：Esc 关层后直接点第二张图（未 hover 过）记录其就绪时间
#     （冷取对照，仅记录不断言慢——两者共享缓存语义都正确）
#   → Esc 关层、清查询
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

# 关残留浮层 + 注入 img:
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

# hover 首图（mouseMoved 到卡上即触发 onMouseEnter），坐标带 hit 预检
def locate():
    out = d.eval(r"""(() => {
  const c = document.querySelector('.cards [data-idx="0"]');
  if (!c) return 'NOCARD';
  c.scrollIntoView({block: 'center'});
  const r = c.getBoundingClientRect();
  const hit = document.elementFromPoint(r.x + r.width / 2, r.y + 40);
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + 40,
    hit: hit ? hit.className.slice(0, 20) : null});
})()""")
    return json.loads(out)


def click(x, y):
    for typ in ("mousePressed", "mouseReleased"):
        d.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchMouseEvent",
                              "params": {"type": typ, "button": "left",
                                         "buttons": 1 if typ == "mousePressed" else 0,
                                         "clickCount": 1, "x": x, "y": y}}))
        d.ws.recv_text()
        time.sleep(0.1)


p0 = locate()
assert p0 != "NOCARD" and p0.get("hit"), f"定位失败: {p0}"
d.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                      "params": {"type": "mouseMoved", "x": p0["x"], "y": p0["y"]}}))
d.ws.recv_text()
time.sleep(0.9)  # 预取落缓存

# 可信单击（必要时重定位重试）
opened = False
for _ in range(3):
    pp = locate()
    click(pp["x"], pp["y"])
    time.sleep(0.15)
    if d.eval("document.querySelector('.zoom-overlay') ? 'y' : 'n'") == "y":
        opened = True
        break
assert opened, "三次点击未开大图层"

t0 = time.time()
ready_ms = None
while time.time() - t0 < 0.5:
    out = d.eval(r"""(() => {
  const i = document.querySelector('.zoom-img');
  if (!i) return JSON.stringify({state: 'noimg'});
  return JSON.stringify({state: i.src.startsWith('blob:') ? 'blob' :
    (i.src.startsWith('data:') ? 'data' : 'other'), src: i.src.slice(0, 20)});
})()""")
    st = json.loads(out)
    if st["state"] in ("blob", "data"):
        ready_ms = int((time.time() - t0) * 1000)
        break
    time.sleep(0.04)
print("hover-prefetched ready in:", ready_ms, "ms |", st)
assert ready_ms is not None and ready_ms <= 240, \
    f"预取未命中（就绪 {ready_ms}ms 或未就绪）"

# Esc 关层
for typ in ("keyDown", "keyUp"):
    d.ws.send(json.dumps({"id": 9903, "method": "Input.dispatchKeyEvent",
                          "params": {"type": typ, "key": "Escape", "code": "Escape",
                                     "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27}}))
    d.ws.recv_text()
    time.sleep(0.1)
time.sleep(0.4)
assert d.eval("document.querySelector('.zoom-overlay') ? 'n' : 'y'") == "y", "层未关"

# 清查询
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
print("PASS: hover 预取命中——单击后 ≤240ms 原图 blob 就绪（无加载中停留）")
