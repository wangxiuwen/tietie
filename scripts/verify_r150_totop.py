# -*- coding: utf-8 -*-
"""R150 / direction 146 verification: tray back-to-top button.

  1. scrollTop <= 80 → no .po-top button
  2. scroll the real container to 300 (dispatch scroll) → button appears
  3. click it → scrollTop back to 0 and selection reset to the first row
"""
import sys, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def main():
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if "view=tray" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "tray target not found"
    ws.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'show-tray'}).catch(e=>String(e))")
    time.sleep(1.0)

    pre = ws.eval("""
(() => {
  const el = document.querySelector('.po-scroll');
  return JSON.stringify({ top: el.scrollTop, btn: !!document.querySelector('.po-top') });
})()
""")
    print("initial:", pre)
    d = json.loads(pre)
    assert d["btn"] is False, f"button visible without scroll: {d}"

    ws.eval("""
(() => {
  const el = document.querySelector('.po-scroll');
  el.scrollTop = 300;
  el.dispatchEvent(new Event('scroll', { bubbles: true }));
  return true;
})()
""")
    time.sleep(0.4)
    mid = ws.eval("""
(() => JSON.stringify({
  top: document.querySelector('.po-scroll').scrollTop,
  btn: !!document.querySelector('.po-top'),
}))()
""")
    print("scrolled:", mid)
    m = json.loads(mid)
    assert m["top"] >= 200 and m["btn"] is True, m

    clicked = ws.eval("""
(() => new Promise(res => {
  const b = document.querySelector('.po-top');
  if (!b) return res('NOBTN');
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  requestAnimationFrame(() => requestAnimationFrame(() => res(
    JSON.stringify({ top: document.querySelector('.po-scroll').scrollTop,
                     sel: document.querySelector('.po-row.active')?.getAttribute('data-idx') ?? null })
  )));
}))()
""")
    print("after click:", clicked)
    a = json.loads(clicked)
    assert a["top"] == 0, a
    assert a["sel"] == "0", a
    print("R150 VERIFY PASS: hidden at top, appears on scroll, click resets scroll+sel")

if __name__ == "__main__":
    main()
