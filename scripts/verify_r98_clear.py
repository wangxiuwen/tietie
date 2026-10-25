# -*- coding: utf-8 -*-
"""R98 / direction 92 verification: tray-panel search clear button.

Flow: type a query into the tray search box (native setter + input event)
      assert the × button appears
      click it (real MouseEvent on the button)
      assert the box is emptied and the button disappears again.
"""
import sys, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def find_target():
    with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
        targets = json.load(r)
    for t in targets:
        if "view=tray" in t["url"]:
            return CDP(t["webSocketDebuggerUrl"])
    return None

def main():
    ws = None
    for _ in range(20):
        ws = find_target()
        if ws: break
        time.sleep(1)
    assert ws, "tray target not found"

    # normalize state first: a previous failed run may have left a query
    ws.eval("""
(() => {
  const el = document.querySelector('.po-search-box input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, '');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""")
    time.sleep(0.3)

    # no query -> no clear button
    pre = ws.eval("String(document.querySelector('.po-clear') == null)")
    assert pre == "true", f"clear button visible without query: {pre!r}"

    # type a query through the React onChange path
    typed = ws.eval("""
(() => {
  const el = document.querySelector('.po-search-box input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, 'zzq无匹配词');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return el.value;
})()
""")
    assert typed == "zzq无匹配词", f"typing failed: {typed!r}"
    time.sleep(0.3)
    has_btn = ws.eval("String(document.querySelector('.po-clear') != null)")
    assert has_btn == "true", "clear button missing with a query present"

    # click the × through its real onClick wiring
    cleared = ws.eval("""
(() => new Promise(res => {
  const btn = document.querySelector('.po-clear');
  btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  requestAnimationFrame(() => requestAnimationFrame(() => res(
    String(document.querySelector('.po-search-box input').value) + '|' +
    String(document.querySelector('.po-clear') == null)
  )));
}))()
""")
    print("after click (value|btnGone):", cleared)
    assert cleared == "|true", f"clear click outcome: {cleared!r}"

    # focus returned to the search input
    focused = ws.eval(
      "String(document.activeElement === document.querySelector('.po-search-box input'))")
    assert focused == "true", f"focus not returned to search input: {focused!r}"

    print("R98 VERIFY PASS: × appears with query, click clears + hides + refocuses")

if __name__ == "__main__":
    main()
