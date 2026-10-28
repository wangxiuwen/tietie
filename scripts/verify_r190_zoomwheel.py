# 方向190 真机验证：抽屉大图浮层滚轮缩放
# 剧本（合成点击开大图 + 可信滚轮事件 + 计算样式断言，结束 Esc 关层）：
#   点第一张图片卡开 zoom 层 → 基线 transform scale(1)
#   → 可信滚轮下滚×3（缩小）→ transform 含 scale(<1)（0.25 极限内）
#   → 上滚×5（放大）→ scale(>1)（≤4 极限内）
#   → 极限压力：连滚 20 下确认夹在 [0.25, 4]
#   → Esc 关层，字段无残留
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


def img_transform():
    out = d.eval(r"""(() => {
  const i = document.querySelector('.zoom-img');
  return i ? getComputedStyle(i).transform : 'NOZOOM';
})()""")
    if not isinstance(out, str):
        raise RuntimeError("type")
    return out


# 注入查询 img: 定位第一张图片卡的安全点击区，可信单击开大图
# 开局清场：关残留浮层（window 级 Esc 只关 zoom，不会把抽屉藏掉——
# 抽屉 Esc 藏窗逻辑在 App 根 handler，zoom 开着时优先关 zoom）
d.eval(r"""(() => {
  const z = document.querySelector('.zoom-overlay');
  if (z) window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
  return z ? 'closed' : 'none';
})()""")
time.sleep(0.3)
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
time.sleep(0.4)
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
assert pos != "NOCARD", "无图片卡"
for typ in ("mousePressed", "mouseReleased"):
    d.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                          "params": {"type": typ, "button": "left",
                                     "buttons": 1 if typ == "mousePressed" else 0,
                                     "clickCount": 1, "x": pos["x"], "y": pos["y"]}}))
    d.ws.recv_text()
    time.sleep(0.12)
time.sleep(1.0)
base = img_transform()
print("baseline transform:", base)
assert base != "NOZOOM" and base in ("none", "matrix(1, 0, 0, 1, 0, 0)"), \
    f"zoom 层未开或初值异常: {base}"


def wheel(dy, n):
    # 滚轮必须落在大图本体上（overlay 中心），卡坐标会被遮罩吃掉
    c = json.loads(d.eval(r"""(() => {
  const i = document.querySelector('.zoom-img');
  if (!i) return 'NOIMG';
  const r = i.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2});
})()"""))
    assert c != "NOIMG", "大图不在"
    for _ in range(n):
        d.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchMouseEvent",
                              "params": {"type": "mouseWheel", "x": c["x"], "y": c["y"],
                                         "deltaX": 0, "deltaY": dy}}))
        d.ws.recv_text()
        time.sleep(0.06)
    time.sleep(0.4)


def scale_of(tr):
    if tr == "none":
        return 1.0
    m = tr.replace("matrix(", "").replace(")", "").split(",")
    return round(float(m[0]), 3)


wheel(120, 3)  # 下滚缩小
s1 = scale_of(img_transform())
print("after 3 down-wheels:", s1)
assert s1 < 1.0, f"缩小未生效: {s1}"

wheel(-120, 6)  # 上滚放大
s2 = scale_of(img_transform())
print("after 6 up-wheels:", s2)
assert s2 > 1.0, f"放大未生效: {s2}"

wheel(-120, 30)  # 极限压力
s3 = scale_of(img_transform())
print("after 30 more up-wheels:", s3)
assert abs(s3 - 4.0) < 0.35, f"上限未夹紧 4: {s3}"

wheel(120, 60)  # 反向极限
s4 = scale_of(img_transform())
print("after 60 down-wheels:", s4)
assert abs(s4 - 0.25) < 0.15, f"下限未夹紧 0.25: {s4}"

# Esc 关层
for typ in ("keyDown", "keyUp"):
    d.ws.send(json.dumps({"id": 9903, "method": "Input.dispatchKeyEvent",
                          "params": {"type": typ, "key": "Escape", "code": "Escape",
                                     "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27}}))
    d.ws.recv_text()
    time.sleep(0.1)
time.sleep(0.4)
closed = d.eval("document.querySelector('.zoom-overlay') ? 'n' : 'y'")
assert closed == "y", "zoom 层未关"
# 清查询
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
print("PASS: 滚轮缩放双向生效、上下限夹紧 [0.25,4]、Esc 关层、查询还原")
