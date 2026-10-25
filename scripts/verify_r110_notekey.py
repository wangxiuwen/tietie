# -*- coding: utf-8 -*-
"""R110 / direction 104 verification: press N to open the note editor.

Shows the drawer, then on the REAL search input (it holds focus):
  - plain "n" types into the box (no overlay, guard works)
  - Ctrl+N opens the note overlay with its textarea focused
Also dispatches plain "n" on window (focus outside fields) -> overlay opens.
Esc closes the overlay each time; no data is written.
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
            if t["url"].startswith("http://tauri.localhost/") and "?" not in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "drawer target not found"
    ws.invoke("show_drawer")
    time.sleep(0.8)

    def overlay_open():
        return ws.eval("""
(() => String(document.querySelector('textarea.note-edit') != null))()
""")

    def close_overlay():
        ws.eval("""
(() => {
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
        time.sleep(0.3)

    # clear search, focus stays in the input (autoFocus)
    ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, '');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.focus();
  return true;
})()
""")
    time.sleep(0.3)
    assert ws.eval(
      "String(document.activeElement === document.querySelector('.bar-header .search input'))"
    ) == "true", "focus not in search box"

    # 1) plain n with focus in the input -> types, no overlay
    typed = ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'n', bubbles: true, cancelable: true }));
  return 'sent';
})()
""")
    time.sleep(0.4)
    val = ws.eval("document.querySelector('.bar-header .search input').value")
    print("plain n in search -> value:", repr(val), "| overlay:", overlay_open())
    # capture handler preventDefaults only when it acts; typing isn't modeled
    # by synthetic keydown (no text insertion), so assert no overlay + the
    # guard path by Ctrl+N contrast below
    assert overlay_open() == "false", "plain n should not open overlay from a field"

    # 2) Ctrl+N from the input -> overlay opens with textarea focused
    ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'n', ctrlKey: true, bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.4)
    opened = ws.eval("""
(() => String(
  document.querySelector('textarea.note-edit') != null &&
  document.activeElement === document.querySelector('textarea.note-edit')
))()
""")
    print("ctrl+n overlay + focus:", opened)
    assert opened == "true", "Ctrl+N did not open focused note editor"
    close_overlay()

    # 3) plain n with focus on window (blur the input first)
    ws.eval("""
(() => {
  document.querySelector('.bar-header .search input').blur();
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'n', bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.4)
    opened2 = ws.eval("""
(() => String(document.querySelector('textarea.note-edit') != null))()
""")
    print("plain n on window -> overlay:", opened2)
    assert opened2 == "true", "plain N did not open overlay outside fields"
    close_overlay()

    # cleanup: clear the search box (n may have been "typed" as value? no —
    # synthetic keydown inserts nothing; value still '')
    ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, '');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""")
    print("R110 VERIFY PASS: N opens note editor, guarded while typing, Ctrl+N always works")

if __name__ == "__main__":
    main()
