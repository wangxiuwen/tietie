# -*- coding: utf-8 -*-
"""R96 / direction 90 verification: session search history.

Flow: set query "alpha" -> hide_window -> show_drawer (commits "alpha")
      set query "beta"  -> hide_window -> show_drawer (commits "beta")
      clear the box, then ArrowUp x2 / ArrowDown x2 on the search input
      must cycle beta -> alpha -> beta -> "".
"""
import sys, time, json
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

SET_VAL = """
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, %s);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return el.value;
})()
"""

KEY = """
(() => new Promise(res => {
  const el = document.querySelector('.bar-header .search input');
  el.focus();
  el.dispatchEvent(new KeyboardEvent('keydown', {
    key: %s, code: 'ArrowUp', bubbles: true, cancelable: true
  }));
  requestAnimationFrame(() => res(el.value));
}))()
"""

def main():
    ws = None
    for _ in range(20):
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if t["url"].startswith("http://tauri.localhost/") and "?" not in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "drawer target not found"

    def ev(expr):
        return ws.eval(expr)

    inp = ".bar-header .search input"
    assert ev(f"!!document.querySelector('{inp}')"), "search input missing"

    # --- commit "alpha" ---
    assert ev(SET_VAL % json.dumps("alpha历史A")) == "alpha历史A"
    ev('window.__TAURI_INTERNALS__.invoke("hide_window")')
    time.sleep(0.5)
    ev('window.__TAURI_INTERNALS__.invoke("show_drawer")')
    time.sleep(0.8)

    # --- commit "beta" ---
    assert ev(SET_VAL % json.dumps("beta历史B")) == "beta历史B"
    ev('window.__TAURI_INTERNALS__.invoke("hide_window")')
    time.sleep(0.5)
    ev('window.__TAURI_INTERNALS__.invoke("show_drawer")')
    time.sleep(0.8)

    # --- clear the box, then cycle history ---
    assert ev(SET_VAL % json.dumps("")) == ""
    got = []
    for _ in range(2):
        got.append(ev(KEY % json.dumps("ArrowUp")))
    for _ in range(2):
        got.append(ev(KEY % json.dumps("ArrowDown")))
    print("cycle:", got)
    exp = ["beta历史B", "alpha历史A", "beta历史B", ""]
    assert got == exp, f"history cycle mismatch: {got} != {exp}"

    # --- typing resets the cursor: edit then ArrowUp jumps to newest again ---
    assert ev(SET_VAL % json.dumps("bet")) == "bet"
    v = ev(KEY % json.dumps("ArrowUp"))
    assert v == "beta历史B", f"after edit, ArrowUp gave {v!r}"

    # --- net-zero cleanup: leave the box empty ---
    ev(SET_VAL % json.dumps(""))
    assert ev(f"document.querySelector('{inp}').value") == ""
    print("R96 VERIFY PASS: commit-on-reopen + ArrowUp/Down cycling OK")

if __name__ == "__main__":
    main()
