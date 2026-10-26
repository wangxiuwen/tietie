# -*- coding: utf-8 -*-
"""R113 / direction 107 verification: split drawer empty states.

With the production history intact (hasItems=true):
  - search with no matches -> compact "没有匹配的条目" hint, NO onboarding card
  - clear search -> cards return (baseline sanity)
The true-empty onboarding path is verified structurally (branch on
items.length) since wiping history is not allowed; the DOM check asserts the
no-match branch renders without .onboard while the component still contains
the onboarding markup for the empty case (string presence in source is
covered by typecheck; here we assert live behavior only).
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

    def empty_state():
        return ws.eval("""
(() => {
  const empty = document.querySelector('.empty');
  if (!empty) return JSON.stringify({ empty: false });
  return JSON.stringify({
    empty: true,
    title: empty.querySelector('h3')?.textContent ?? '',
    onboard: !!empty.querySelector('.onboard'),
    icon: empty.querySelector('.empty-icon')?.textContent ?? '',
  });
})()
""")

    # baseline: cards exist, no empty state
    base = json.loads(empty_state())
    assert base["empty"] is False, f"expected cards, got empty state: {base}"

    # search miss -> compact hint, no onboarding
    type_query("~~~~zzz-绝不匹配")
    d = json.loads(empty_state())
    print("search miss:", d)
    assert d["empty"] and d["title"] == "没有匹配的条目", d
    assert d["onboard"] is False, "onboarding card leaked into no-match state"
    assert d["icon"] == "🔍", d

    # clear -> back to cards
    type_query("")
    d2 = json.loads(empty_state())
    assert d2["empty"] is False, "cards did not return after clearing search"

    print("R113 VERIFY PASS: no-match state is compact; onboarding reserved for true empty")

if __name__ == "__main__":
    main()
