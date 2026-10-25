# -*- coding: utf-8 -*-
"""R105 / direction 99 verification: palette number-key quick pick.

Hangs a temp memo, opens its detail, then:
  - trusted mouse move onto the palette + keydown "3" -> pin color becomes
    MEMO_COLORS[2] (#ff9500), active dot index 2
  - mouse moved away + keydown "5" -> color unchanged (keys inert off-hover)
Cleanup closes the detail and removes the temp memo.
"""
import sys, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

COLORS = ["#007aff", "#34c759", "#ff9500", "#ff2d55", "#af52de",
          "#5856d6", "#8e8e93", "#ffcc00"]

def cdp_send(ws, method, params):
    ws.seq += 1
    rid = ws.seq
    ws.ws.send(json.dumps({"id": rid, "method": method, "params": params}))
    while True:
        msg = json.loads(ws.ws.recv_text())
        if msg.get("id") != rid:
            continue
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg.get("result", {})

def mouse_move(ws, x, y):
    cdp_send(ws, "Input.dispatchMouseEvent",
             {"type": "mouseMoved", "x": x, "y": y})

def key(ws, k):
    cdp_send(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": k,
             "code": "Digit" + k, "windowsVirtualKeyCode": ord(k)})
    cdp_send(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": k,
             "code": "Digit" + k, "windowsVirtualKeyCode": ord(k)})

def main():
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if "view=line" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "clothesline target not found"

    mid = ws.invoke("add_memo_direct",
                    {"content": "调色板数字键快选验证", "remindAt": None, "color": None})
    assert isinstance(mid, int), f"add_memo_direct -> {mid!r}"
    print("temp memo:", mid)
    time.sleep(0.8)

    opened = ws.eval("""
(() => new Promise(res => {
  const card = document.querySelector('.line-card[data-memo="__MID__"]');
  if (!card) return res('NOCARD');
  const r = card.getBoundingClientRect();
  card.dispatchEvent(new PointerEvent('pointerdown', {
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, screenX: 500, screenY: 500 }));
  window.dispatchEvent(new PointerEvent('pointerup', {
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, screenX: 500, screenY: 500 }));
  requestAnimationFrame(() => res(String(document.querySelector('.line-palette') != null)));
}))()
""".replace("__MID__", str(mid)))
    assert opened == "true", f"detail did not open: {opened!r}"

    def active_idx():
        return ws.eval("""
(() => {
  const dots = [...document.querySelectorAll('.line-palette .pal-dot')];
  return String(dots.findIndex(d => d.classList.contains('active')));
})()
""")

    assert active_idx() == "0", f"initial color not default blue: {active_idx()}"

    # trusted hover onto the palette, then press 3
    rect = json.loads(ws.eval(
      "JSON.stringify(document.querySelector('.line-palette').getBoundingClientRect())"))
    px, py = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2
    mouse_move(ws, px, py)
    time.sleep(0.3)
    key(ws, "3")
    time.sleep(0.6)
    idx = active_idx()
    memos = ws.invoke("list_memos")
    color = next((m["color"] for m in memos if m["id"] == mid), None)
    print("after hover+3: active idx", idx, "| db color", color)
    assert idx == "2" and color == COLORS[2], f"quick pick failed: {idx}, {color}"

    # move away, press 5 -> nothing changes
    mouse_move(ws, 8, rect["y"] + rect["height"] + 200)
    time.sleep(0.3)
    key(ws, "5")
    time.sleep(0.6)
    idx2 = active_idx()
    color2 = next((m["color"] for m in ws.invoke("list_memos") if m["id"] == mid), None)
    print("after leave+5: active idx", idx2, "| db color", color2)
    assert idx2 == "2" and color2 == COLORS[2], f"keys active without hover: {idx2}, {color2}"

    # cleanup
    ws.eval("""
(() => {
  document.querySelector('.line-detail')
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.3)
    ws.invoke("remove_memo", {"id": mid})
    time.sleep(0.4)
    left = next((m["id"] for m in ws.invoke("list_memos") if m["id"] == mid), None)
    assert left is None, "temp memo not removed"
    print("R105 VERIFY PASS: hover+digit picks color, off-hover keys inert")

if __name__ == "__main__":
    main()
