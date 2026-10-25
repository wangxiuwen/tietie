# -*- coding: utf-8 -*-
"""R108 / direction 102 verification: live reminder countdown in detail head.

Hangs a temp memo with a reminder 5 minutes out, opens its detail:
  - the head countdown span shows "⏰ 剩 Xm SSs"
  - reading it again ~3.2s later shows the seconds ticking down
Hangs a second memo already due: countdown reads 已到期 and carries .due.
Cleanup removes both memos.
"""
import sys, time, json, re, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

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

    now = int(time.time())

    # normalize state: close any leftover detail, drop stray probe memos
    ws.eval("""
(() => {
  const d = document.querySelector('.line-detail');
  if (d) d.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.4)
    for m in ws.invoke("list_memos"):
        if m["content"] in ("倒数验证A", "倒数验证B"):
            ws.invoke("remove_memo", {"id": m["id"]})
            print("dropped stray", m["id"])
    time.sleep(0.4)
    mid1 = ws.invoke("add_memo_direct",
                     {"content": "倒数验证A", "remindAt": now + 300, "color": None})
    mid2 = ws.invoke("add_memo_direct",
                     {"content": "倒数验证B", "remindAt": now - 60, "color": None})
    assert isinstance(mid1, int) and isinstance(mid2, int)
    print("temp memos:", mid1, mid2)
    time.sleep(0.8)

    def open_detail(mid):
        r = ws.eval("""
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
  requestAnimationFrame(() => res(String(document.querySelector('.line-due-countdown') != null)));
}))()
""".replace("__MID__", str(mid)))
        return r

    def head():
        return ws.eval("""
(() => {
  const el = document.querySelector('.line-due-countdown');
  return el ? el.textContent + '|' + el.className : 'NONE';
})()
""")

    def close():
        ws.eval("""
(() => {
  document.querySelector('.line-detail')
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
        time.sleep(0.4)

    # memo A: countdown ticks live
    assert open_detail(mid1) == "true", "detail/countdown did not open"
    h1 = head()
    print("A t0:", h1)
    m = re.match(r"⏰ 剩 (\d+)m (\d+)s\|(.*)", h1)
    assert m, f"unexpected countdown text: {h1!r}"
    assert "due" not in m.group(3).split(), "future reminder flagged due"
    time.sleep(3.2)
    h2 = head()
    print("A t+3.2s:", h2)
    m2 = re.match(r"⏰ 剩 (\d+)m (\d+)s\|", h2)
    assert m2, f"unexpected tick text: {h2!r}"
    d = (int(m.group(1)) * 60 + int(m.group(2))) - (int(m2.group(1)) * 60 + int(m2.group(2)))
    assert 2 <= d <= 5, f"countdown did not tick (delta {d}s)"
    close()

    # memo B: already due -> 已到期 + .due class
    assert open_detail(mid2) == "true", "detail B did not open"
    h3 = head()
    print("B:", h3)
    h3t, h3c = h3.split("|", 1)
    assert "已到期" in h3t and "due" in h3c.split(), h3
    close()

    # cleanup
    ws.invoke("remove_memo", {"id": mid1})
    ws.invoke("remove_memo", {"id": mid2})
    time.sleep(0.4)
    left = [m["id"] for m in ws.invoke("list_memos") if m["id"] in (mid1, mid2)]
    assert not left, f"cleanup failed: {left}"
    print("R108 VERIFY PASS: head countdown ticks per second; due state labeled")

if __name__ == "__main__":
    main()
