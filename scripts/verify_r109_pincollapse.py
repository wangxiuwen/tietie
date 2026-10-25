# -*- coding: utf-8 -*-
"""R109 / direction 103 verification: tray pinned-section collapse.

Temporarily pins 6 real non-sensitive text items (all items currently
unpinned — verified before), shows the tray panel, asserts:
  - pinned section header "📌 置顶 · 6", exactly 5 rows rendered, expand
    link "展开 +1" present
  - clicking expand renders all 6 rows
  - keyboard ↓ stays in sync (selection walks rendered rows)
Then unpins all 6 (state fully restored to 0 pins) and verifies cleanup.
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
            if "view=tray" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "tray target not found"

    items = ws.invoke("list_items", {"limit": 100})
    # sanity: nothing pinned yet (must match the read-only sqlite check)
    assert not [x for x in items if x["pinned"]], "precondition broken: pins exist"
    to_pin = [x for x in items if x["kind"] == "text" and not x["sensitive"]][:6]
    assert len(to_pin) == 6, f"need 6 pinnable items, got {len(to_pin)}"
    ids = [x["id"] for x in to_pin]
    print("pinning:", ids)
    for i in ids:
        ws.invoke("toggle_pin", {"id": i})

    ws.invoke("open_tray") if False else None
    # refresh the popover via the same event the tray toggle uses
    ws.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'show-tray'}).catch(e=>String(e))")
    time.sleep(1.2)

    state = ws.eval("""
(() => {
  const secs = [...document.querySelectorAll('.po-section')];
  const pin = secs[0];
  return JSON.stringify({
    title: pin?.querySelector('.po-title span')?.textContent ?? 'NOSEC',
    rows: pin ? pin.querySelectorAll('.po-row').length : -1,
    expand: pin?.querySelector('.po-link')?.textContent ?? null,
  });
})()
""")
    d = json.loads(state)
    print("collapsed:", d)
    assert d["title"].startswith("📌 置顶 · 6"), f"pinned header wrong: {d['title']!r}"
    assert d["rows"] == 5, f"expected 5 collapsed rows, got {d['rows']}"
    assert d["expand"] and "+1" in d["expand"], f"expand link wrong: {d['expand']!r}"

    # click expand through its real onClick
    after = ws.eval("""
(() => new Promise(res => {
  const btn = document.querySelectorAll('.po-section')[0].querySelector('.po-link');
  btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const pin = document.querySelectorAll('.po-section')[0];
    res(JSON.stringify({
      rows: pin.querySelectorAll('.po-row').length,
      expandGone: !pin.querySelector('.po-link') || pin.querySelector('.po-link').textContent.includes('全部'),
    }));
  }));
}))()
""")
    d2 = json.loads(after)
    print("expanded:", d2)
    assert d2["rows"] == 6, f"expected all 6 after expand, got {d2['rows']}"

    # ↓ selection stays within rendered rows
    sel = ws.eval("""
(() => new Promise(res => {
  const el = document.querySelector('.po-search-box input');
  el.focus();
  for (let i = 0; i < 8; i++) {
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true }));
  }
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const total = document.querySelectorAll('.po-row').length;
    const act = document.querySelector('.po-row.active');
    const idx = act ? act.getAttribute('data-idx') : null;
    res(JSON.stringify({ total, idx }));
  }));
}))()
""")
    d3 = json.loads(sel)
    print("after 8x ↓:", d3)
    assert d3["idx"] is not None and int(d3["idx"]) < d3["total"], f"selection out of range: {d3}"

    # restore: unpin all 6, refresh, assert no pinned section remains
    for i in ids:
        ws.invoke("toggle_pin", {"id": i})
    ws.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'show-tray'}).catch(e=>String(e))")
    time.sleep(1.0)
    final = ws.eval("""
(() => JSON.stringify({
  pinSec: [...document.querySelectorAll('.po-section')]
    .some(s => (s.querySelector('.po-title span')?.textContent ?? '').includes('置顶')),
}))()
""")
    assert json.loads(final)["pinSec"] is False, "pinned section still shown after unpin"
    items2 = ws.invoke("list_items", {"limit": 100})
    left = [x["id"] for x in items2 if x["pinned"]]
    assert not left, f"pins not restored: {left}"
    print("R109 VERIFY PASS: pinned >5 collapses to 5 + expand link; expand shows all; pins restored")

if __name__ == "__main__":
    main()
