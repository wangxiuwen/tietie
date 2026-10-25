# -*- coding: utf-8 -*-
"""R103 / direction 97 verification: search exclusion syntax in the drawer.

Real-UI wiring (typing through the React search input):
  1. read card texts, pick a distinctive word W from a text card
  2. query "W"      -> that card is visible (positive works)
  3. query "W -W"   -> logically always empty; assert zero cards
  4. query "-qqzzqx" (matches nothing) -> count equals the unfiltered count
  5. clear the box
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

    def card_texts():
        # aria-label is the clean item content ("文本：…"); textContent also
        # carries UI chrome like the "Ctrl1↵ 粘贴" hover hint
        return ws.eval("""
(() => JSON.stringify(
  [...document.querySelectorAll('.card')].map(c => c.getAttribute('aria-label') || '')
))()
""")

    # normalize: empty query
    type_query("")
    texts = json.loads(card_texts())
    assert len(texts) >= 3, f"need >=3 cards, got {len(texts)}"

    # pick a distinctive ascii word (>=5 chars) appearing in exactly one card
    import re
    W = None
    for t in texts:
        for w in re.findall(r"[A-Za-z][A-Za-z0-9-]{4,}", t):
            wl = w.lower()
            if sum(wl in x.lower() for x in texts) == 1:
                W = wl; break
        if W: break
    assert W, f"no distinctive word across {len(texts)} cards"
    print("pick W =", W, "| baseline cards:", len(texts))

    # positive: the card containing W is visible
    type_query(W)
    pos = json.loads(card_texts())
    print("query W ->", len(pos), "cards")
    assert any(W in t.lower() for t in pos), "positive match lost the card"

    # W AND NOT W -> always empty
    type_query(W + " -" + W)
    neg = json.loads(card_texts())
    print("query 'W -W' ->", len(neg), "cards")
    assert len(neg) == 0, f"'W -W' should match nothing, got {len(neg)}"

    # a negation of a term nothing can match changes nothing: pure symbols
    # avoid the letter-subsequence path that can hit long hex/URL content
    type_query("")
    base = len(json.loads(card_texts()))
    type_query("-~~~~zzz")
    neg2 = json.loads(card_texts())
    print("query '-~~~~zzz' ->", len(neg2), "cards (base", base, ")")
    assert len(neg2) == base, f"no-op negation changed count: {len(neg2)} != {base}"

    # cleanup
    type_query("")
    print("R103 VERIFY PASS: exclusion syntax works through the drawer search UI")

if __name__ == "__main__":
    main()
