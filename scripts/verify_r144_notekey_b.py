# -*- coding: utf-8 -*-
"""R144 / direction 138 verification: B opens the note overlay.

Mirror of the direction-104 checks, for B:
  - plain "b" with focus OUTSIDE fields opens the note editor
  - plain "b" typed in the search box stays a search (no overlay)
  - ⌘N still works from the field (regression guard for direction 104)
Esc closes each time; no data written.
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

    def overlay():
        return ws.eval("String(document.querySelector('textarea.note-edit') != null)")

    def key(k, target_sel, mod=False):
        ws.eval("""
(() => {
  const el = document.querySelector('__SEL__');
  if (!el) { window.dispatchEvent(new KeyboardEvent('keydown', {
    key: '__K__', ctrlKey: __M__, bubbles: true, cancelable: true })); return 'WIN'; }
  el.dispatchEvent(new KeyboardEvent('keydown', {
    key: '__K__', ctrlKey: __M__, bubbles: true, cancelable: true }));
  return 'EL';
})()
""".replace("__SEL__", target_sel).replace("__K__", k)
   .replace("__M__", "true" if mod else "false"))

    def esc():
        ws.eval("""
(() => {
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
        time.sleep(0.35)

    INP = ".bar-header .search input"

    # 1) plain b outside fields → overlay opens
    r = key("b", ".no-such-element")
    print("dispatch:", r)
    time.sleep(0.4)
    o1 = overlay()
    print("plain b on window:", o1)
    assert o1 == "true", "plain B did not open the note overlay"
    esc()

    # 2) plain b inside the search box → no overlay (types instead)
    ws.eval(f"document.querySelector('{INP}').focus()")
    time.sleep(0.2)
    key("b", INP)
    time.sleep(0.4)
    o2 = overlay()
    print("plain b in search:", o2)
    assert o2 == "false", "plain B hijacked typing in the search box"

    # 3) Ctrl+N from the field still opens (direction 104 regression)
    key("n", INP, mod=True)
    time.sleep(0.4)
    o3 = overlay()
    print("ctrl+n in search:", o3)
    assert o3 == "true", "Ctrl+N regression"
    esc()
    print("R144 VERIFY PASS: B alias opens notes, guarded in fields, Ctrl+N intact")

if __name__ == "__main__":
    main()
