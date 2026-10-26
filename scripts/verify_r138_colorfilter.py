# -*- coding: utf-8 -*-
"""R138 / direction 132 verification: filter clothesline by pin color.

Hangs one orange memo + one default-accent memo, opens the clothesline:
  - filter chips render (all-dot + 8 colors), none active
  - click the orange chip -> only the orange memo remains on the rope;
    the all-chip gets active on click -> both return
  - a color with zero memos -> empty-color message
Cleanup removes both memos.
"""
import sys, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

ORANGE = "#ff9500"

def main():
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if "view=line" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "clothesline target not found"

    # normalize: close detail, drop strays
    ws.eval("""
(() => {
  const d = document.querySelector('.line-detail');
  if (d) d.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    for m in ws.invoke("list_memos"):
        if m["content"].startswith("颜色筛选验证"):
            ws.invoke("remove_memo", {"id": m["id"]})
    time.sleep(0.3)

    m_orange = ws.invoke("add_memo_direct",
                         {"content": "颜色筛选验证橙", "remindAt": None, "color": ORANGE})
    m_other = ws.invoke("add_memo_direct",
                        {"content": "颜色筛选验证他", "remindAt": None, "color": None})
    assert isinstance(m_orange, int) and isinstance(m_other, int)
    time.sleep(0.8)

    def rope():
        return ws.eval("""
(() => JSON.stringify(
  [...document.querySelectorAll('.line-card')].map(c => c.getAttribute('data-memo'))
))()
""")

    chips = ws.eval("""
(() => JSON.stringify({
  dots: document.querySelectorAll('.cfilter-dot').length,
  active: document.querySelector('.cfilter-dot.active')?.className ?? null,
}))()
""")
    d = json.loads(chips)
    print("chips:", d)
    assert d["dots"] == 9, d  # all + 8 colors
    assert "all" in (d["active"] or ""), f"all-chip should start active: {d}"

    base = json.loads(rope())
    assert len(base) >= 2, f"need >=2 memos, got {len(base)}"

    # click the orange chip (5th color = index 4 among color dots)
    ws.eval("""
(() => {
  const dots = [...document.querySelectorAll('.cfilter-dot')].slice(1); // skip all
  const orange = dots.find(d => (d.getAttribute('style') || '').includes('255, 149, 0'));
  orange.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""".replace("__C__", ORANGE))
    time.sleep(0.5)
    filtered = json.loads(rope())
    print("orange only:", filtered)
    assert filtered == [str(m_orange)], filtered

    # empty color: pick a MEMO_COLORS entry with no memos (green index 1)
    ws.eval("""
(() => {
  const dots = [...document.querySelectorAll('.cfilter-dot')].slice(1);
  dots[1].dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""")
    time.sleep(0.5)
    empty = json.loads(rope())
    msg = ws.eval("String(document.querySelector('.line-empty')?.textContent ?? '')")
    print("empty color:", empty, "| msg:", msg)
    assert empty == [] and "这个颜色" in msg, (empty, msg)

    # all chip restores everything
    ws.eval("""
(() => {
  document.querySelector('.cfilter-dot').dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""")
    time.sleep(0.5)
    restored = json.loads(rope())
    assert sorted(restored) == sorted(base), "all-filter did not restore"

    ws.invoke("remove_memo", {"id": m_orange})
    ws.invoke("remove_memo", {"id": m_other})
    time.sleep(0.3)
    left = [m["id"] for m in ws.invoke("list_memos") if m["id"] in (m_orange, m_other)]
    assert not left
    print("R138 VERIFY PASS: color filter narrows, empty color hints, all restores")

if __name__ == "__main__":
    main()
