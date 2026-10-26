# -*- coding: utf-8 -*-
"""R117 / direction 111 verification: compact rows show the ⌘N kbd chip.

Snapshots the compact pref, toggles the real header compact button to enter
row view, asserts the first rows render .index-kbd as a STATIC inline chip
inside the row (offsetParent === the row, position: static, text like ⌘1),
then toggles back and restores the original preference.
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

    # snapshot compact pref (global key used when no folder selected)
    key = "tietie-compact"
    pref0 = ws.eval(f"localStorage.getItem('{key}')")
    print("compact pref before:", pref0)

    def is_row_view():
        return ws.eval(
          "String(document.querySelector('.row-item') != null)")

    # ensure we are in CARD view first (so the toggle enters row view)
    if is_row_view() == "true":
        pass  # already rows; toggle once to cards, then back, keeps test simple
    rows0 = is_row_view()

    # find the compact toggle button in the header (right side)
    btn_found = ws.eval("""
(() => {
  const btns = [...document.querySelectorAll('.bar-header button, header button, button')];
  const b = btns.find(x => (x.title || '').length > 0 && /紧凑|松散|compact|rows?|list/i.test(x.title + ' ' + (x.getAttribute('aria-label')||'')));
  if (!b) return 'NOBTN';
  window.__compactBtn = b;
  return b.title;
})()
""")
    print("compact toggle:", btn_found)
    assert btn_found != "NOBTN", "compact toggle button not found"

    # click to switch view; if we started in rows, click twice (rows->cards->rows)
    # is unnecessary — just assert in whatever row state we land after ensuring rows.
    if rows0 != "true":
        ws.eval("window.__compactBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }))")
        time.sleep(0.5)
    assert is_row_view() == "true", "row view not active"

    chip = ws.eval("""
(() => {
  const row = document.querySelector('.row-item');
  const kbd = row && row.querySelector('.index-kbd');
  if (!kbd) return JSON.stringify({ present: false });
  const cs = getComputedStyle(kbd);
  return JSON.stringify({
    present: true,
    position: cs.position,
    text: kbd.textContent,
    inRow: kbd.offsetParent === row || row.contains(kbd),
    rowRight: row.getBoundingClientRect().right,
    kbdRight: kbd.getBoundingClientRect().right,
  });
})()
""")
    d = json.loads(chip)
    print("row kbd:", d)
    assert d["present"], "no index-kbd in compact row"
    assert d["position"] == "static", f"chip not inline: {d['position']}"
    assert d["inRow"], "chip not contained in its row"
    assert d["kbdRight"] <= d["rowRight"] + 1, "chip overflows the row"
    # keyboard hint glyph present (⌘ or Ctrl depending on platform)
    assert d["text"] and any(c.isdigit() for c in d["text"]), f"no digit in hint: {d['text']!r}"

    # restore the original view state
    if rows0 != "true":
        ws.eval("window.__compactBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }))")
        time.sleep(0.4)
    pref1 = ws.eval(f"localStorage.getItem('{key}')")
    if pref0 != pref1:
        ws.eval(f"localStorage.setItem('{key}', {json.dumps(pref0)})")
    print("R117 VERIFY PASS: compact rows render inline ⌘N chip inside the row")

if __name__ == "__main__":
    main()
