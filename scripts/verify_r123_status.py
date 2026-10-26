# -*- coding: utf-8 -*-
"""R123 / direction 117 verification: drawer footer visible/total status.

  - no search: footer reads 显示 N/N (visible == total)
  - with a search: footer reads 命中 K/N and hit-count accent applies
  - clear search: back to 显示 N/N
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
            if t["url"].startswith("http://tauri.localhost/") and "?" not in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "drawer target not found"
    ws.invoke("show_drawer")
    time.sleep(0.8)

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
        time.sleep(0.4)

    def footer():
        return ws.eval("""
(() => {
  const el = document.querySelector('.bar-foot .hit-count') ||
             [...document.querySelectorAll('.bar-foot span')].find(s => /\\d+\\/\\d+/.test(s.textContent));
  return el ? el.textContent.trim() : 'NONE';
})()
""")

    base = footer()
    print("no search:", base)
    m = re.match(r"^显示 (\d+)/(\d+)$", base)
    assert m, f"unexpected footer: {base!r}"
    n = int(m.group(2))
    assert int(m.group(1)) == n, "visible != total without a search"

    type_query("http")
    hit = footer()
    print("searching:", hit)
    m2 = re.match(r"^命中 (\d+)/(\d+)$", hit)
    assert m2 and int(m2.group(2)) == n, f"unexpected hit footer: {hit!r}"

    type_query("")
    back = footer()
    print("cleared:", back)
    assert back == base, f"did not restore: {back!r}"

    print("R123 VERIFY PASS: footer shows 显示/命中 with visible/total counts")

if __name__ == "__main__":
    main()
