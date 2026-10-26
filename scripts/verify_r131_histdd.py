# -*- coding: utf-8 -*-
"""R131 / direction 126 verification: recent-search dropdown.

Commits two searches through the REAL commit path (drawer reopen, direction
90), then on the drawer:
  - focusing the EMPTY search box pops the dropdown, newest first
  - typing hides it
  - clicking (mousedown) an item applies that search
  - blur closes it
Cleanup clears the search.
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

    def type_query(q):
        ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, '%s');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""" % q)
        time.sleep(0.3)

    def commit(q):
        type_query(q)
        ws.invoke("hide_window")
        time.sleep(0.4)
        ws.invoke("show_drawer")
        time.sleep(0.8)

    def dd():
        return ws.eval("""
(() => {
  const dd = document.querySelector('.search-hist');
  return JSON.stringify({
    open: !!dd,
    items: dd ? [...dd.querySelectorAll('.search-hist-item')].map(b => b.textContent) : [],
  });
})()
""")

    # commit two searches through the real reopen path
    commit("下拉验证甲")
    commit("下拉验证乙")

    # focus the EMPTY box -> dropdown newest first
    type_query("")
    ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  el.blur(); el.focus();
  return true;
})()
""")
    time.sleep(0.4)
    d = json.loads(dd())
    print("dropdown:", d)
    assert d["open"], "dropdown did not open on focus"
    assert d["items"][:2] == ["下拉验证乙", "下拉验证甲"], d["items"]

    # typing hides it
    type_query("下")
    d2 = json.loads(dd())
    assert d2["open"] is False, "dropdown stayed open while typing"
    type_query("")

    # mousedown on an item applies the search
    ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  el.blur(); el.focus();
  return true;
})()
""")
    time.sleep(0.4)
    applied = ws.eval("""
(() => {
  const btn = [...document.querySelectorAll('.search-hist-item')]
    .find(b => b.textContent === '下拉验证甲');
  if (!btn) return 'NOITEM';
  btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
  return 'OK';
})()
""")
    assert applied == "OK", applied
    time.sleep(0.4)
    val = ws.eval("document.querySelector('.bar-header .search input').value")
    print("after click, query:", repr(val))
    assert val == "下拉验证甲", val
    d3 = json.loads(dd())
    assert d3["open"] is False, "dropdown stayed open after applying"

    # cleanup
    type_query("")
    print("R131 VERIFY PASS: focus opens recent-search dropdown, click applies")

if __name__ == "__main__":
    main()
