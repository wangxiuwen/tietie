# -*- coding: utf-8 -*-
"""R114 / direction 108 verification: recent pin colors float to the front.

Hangs three temp memos with DISTINCT recent colors (orange, purple, yellow)
plus one default-blue probe, opens the blue probe's detail, asserts the
palette renders those three colors in positions 1-3 (recency order), then
verifies the number-key quick pick follows the SAME order (hover + "1"
selects the newest color). Cleanup removes all temp memos.
"""
import sys, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

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

    # normalize: close any leftover detail overlay, drop stray probes
    ws.eval("""
(() => {
  const d = document.querySelector('.line-detail');
  if (d) d.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.4)
    for m in ws.invoke("list_memos"):
        if m["content"].startswith("最近用色验证"):
            ws.invoke("remove_memo", {"id": m["id"]})
    time.sleep(0.4)

    # hang the blue probe FIRST so its default color is the OLDEST and does
    # not pollute the recents; then orange, purple, yellow. list_memos is
    # oldest-first (sort ASC), recents walk from the end = [yellow, purple, orange]
    probe = ws.invoke("add_memo_direct",
                      {"content": "最近用色验证蓝", "remindAt": None, "color": None})
    seq = [("#ff9500", "橙"), ("#af52de", "紫"), ("#ffcc00", "黄")]
    ids = []
    for color, name in seq:
        mid = ws.invoke("add_memo_direct",
                        {"content": "最近用色验证" + name, "remindAt": None, "color": color})
        ids.append(mid)
    print("probe:", probe, "temp memos:", ids)
    time.sleep(0.8)

    # open the probe's detail via the real pointer path
    opened = ws.eval("""
(() => new Promise(res => {
  const card = document.querySelector('.line-card[data-memo="__MID__"]');
  if (!card) return res('NOCARD');
  const b = card.getBoundingClientRect();
  card.dispatchEvent(new PointerEvent('pointerdown', {
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: b.left + b.width / 2, clientY: b.top + b.height / 2, screenX: 500, screenY: 500 }));
  window.dispatchEvent(new PointerEvent('pointerup', {
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: b.left + b.width / 2, clientY: b.top + b.height / 2, screenX: 500, screenY: 500 }));
  requestAnimationFrame(() => res(String(document.querySelector('.line-palette') != null)));
}))()
""".replace("__MID__", str(probe)))
    assert opened == "true", f"detail did not open: {opened!r}"

    order = ws.eval("""
(() => JSON.stringify([...document.querySelectorAll('.line-palette .pal-dot')]
  .map(d => rgbToHex(getComputedStyle(d).background))))()
""") if False else ws.eval("""
(() => JSON.stringify(
  [...document.querySelectorAll('.line-palette .pal-dot')]
    .slice(0, 4)
    .map((d, i) => d.title + ':' + d.style.background)
))()
""")
    print("palette front:", order)
    got = json.loads(order)
    # titles are 1.. and inline background carries the literal hex
    assert "255, 204, 0" in got[0], f"newest (yellow) not first: {got}"
    assert "175, 82, 222" in got[1], f"purple not second: {got}"
    assert "255, 149, 0" in got[2], f"orange not third: {got}"

    # number keys follow the same order: hover + "1" -> yellow
    rect = json.loads(ws.eval(
      "JSON.stringify(document.querySelector('.line-palette').getBoundingClientRect())"))
    cdp_send(ws, "Input.dispatchMouseEvent",
             {"type": "mouseMoved", "x": rect["x"] + rect["width"] / 2,
              "y": rect["y"] + rect["height"] / 2})
    time.sleep(0.3)
    cdp_send(ws, "Input.dispatchKeyEvent",
             {"type": "keyDown", "key": "1", "code": "Digit1", "windowsVirtualKeyCode": 49})
    cdp_send(ws, "Input.dispatchKeyEvent",
             {"type": "keyUp", "key": "1", "code": "Digit1", "windowsVirtualKeyCode": 49})
    time.sleep(0.6)
    color = next((m["color"] for m in ws.invoke("list_memos") if m["id"] == probe), None)
    print("after hover+1 probe color:", color)
    assert color == "#ffcc00", f"quick pick did not follow palette order: {color}"

    # cleanup
    ws.eval("""
(() => {
  document.querySelector('.line-detail')
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.3)
    for mid in ids + [probe]:
        ws.invoke("remove_memo", {"id": mid})
    time.sleep(0.4)
    left = [m["id"] for m in ws.invoke("list_memos") if m["content"].startswith("最近用色验证")]
    assert not left, f"cleanup failed: {left}"
    print("R114 VERIFY PASS: recents float first, number keys follow same order")

if __name__ == "__main__":
    main()
