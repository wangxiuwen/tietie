# -*- coding: utf-8 -*-
"""R124 / direction 118 verification: link card shows a domain badge.

Searches "http" to surface link cards, asserts the link card's URL row has a
.link-domain badge whose text equals the URL's hostname minus "www.".
Clears the search afterwards.
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

    ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, 'http');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""")
    time.sleep(0.5)

    out = ws.eval("""
(() => {
  const card = [...document.querySelectorAll('.card')].find(c => c.querySelector('.link-domain'));
  if (!card) return JSON.stringify({ found: false });
  const badge = card.querySelector('.link-domain');
  const url = card.querySelector('.link-url')?.textContent ?? '';
  return JSON.stringify({
    found: true,
    badge: badge.textContent,
    urlHead: url.slice(0, 60),
    badgeColor: getComputedStyle(badge).color,
  });
})()
""")
    d = json.loads(out)
    print("link card:", d)
    assert d["found"], "no link card with domain badge rendered"
    # expected host = hostname of the URL shown after the badge, minus www.
    import re as _re
    m = _re.search(r"https?://([^/\s]+)", d["urlHead"])
    assert m, f"no URL in row text: {d['urlHead']!r}"
    expect = m.group(1).split(":")[0].removeprefix("www.")
    assert d["badge"] == expect, f"badge {d['badge']!r} != host {expect!r}"
    assert d["badgeColor"] != "rgba(0, 0, 0, 0)" and "0, 122, 255" in d["badgeColor"], \
        f"badge not accent-colored: {d['badgeColor']}"

    # cleanup: clear search
    ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, '');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""")
    print("R124 VERIFY PASS: link card carries github.com domain badge")

if __name__ == "__main__":
    main()
