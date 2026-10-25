# -*- coding: utf-8 -*-
"""R101 / direction 95 verification: image hanging-card placeholder.

Seeds one temp memo row (kind=image, EMPTY preview, content='1234x567')
directly in sqlite — the session-established temp-data method — plus hangs a
real image clip item for the positive control; asserts:
  - no-preview image card renders .line-img.empty with the placeholder glyph,
    never the dimension text
  - with-preview image card still renders the thumbnail background
Cleanup removes both rows.
"""
import sys, time, json, sqlite3, os, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

DB = os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\tietie.sqlite")

def main():
    conn = sqlite3.connect(DB, timeout=10)
    now = int(time.time())
    cur = conn.execute(
        "INSERT INTO memo (kind, content, preview, color, source_item_id, created_at, sort) "
        "VALUES ('image', '1234x567', '', '#007aff', NULL, ?, "
        "(SELECT COALESCE(MAX(sort), -1) + 1 FROM memo))", (now,))
    seeded = cur.lastrowid
    conn.commit()
    print("seeded image memo (no preview):", seeded)

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

    # the direct sqlite seed does not emit memos-changed — hanging the control
    # item does, and its reload picks up both rows
    hung = ws.invoke("hang_item", {"id": 14})
    print("hang_item(14) ->", hung)
    time.sleep(1.0)

    # 1) seeded no-preview card -> placeholder, not dimension text
    a = ws.eval("""
(() => {
  const card = document.querySelector('.line-card[data-memo="{ID}"]');
  if (!card) return 'NOCARD';
  const ph = card.querySelector('.line-img.empty');
  return JSON.stringify({
    hasEmpty: !!ph,
    glyph: ph ? ph.textContent : null,
    dimTextShown: !!card.querySelector('.line-text'),
    bodyText: card.textContent.includes('1234x567'),
  });
})()
""".replace("{ID}", str(seeded)))
    d = json.loads(a)
    print("no-preview card:", d)
    assert d["hasEmpty"] and d["glyph"].strip() == "🖼️", f"placeholder missing: {d}"
    assert not d["dimTextShown"] and not d["bodyText"], f"dimension text leaked: {d}"

    # 2) positive control: the hung real image item renders its thumbnail
    b = ws.eval("""
(() => {
  const card = document.querySelector('.line-card[data-memo="{ID}"]');
  if (!card) return 'NOCARD';
  const img = card.querySelector('.line-img');
  return JSON.stringify({ has: !!img, empty: img ? img.classList.contains('empty') : null,
    bg: img ? getComputedStyle(img).backgroundImage.slice(0, 30) : null });
})()
""".replace("{ID}", str(hung)))
    d2 = json.loads(b)
    print("with-preview card:", d2)
    assert d2["has"] and d2["empty"] is False and "data:image/png" in d2["bg"], d2

    # cleanup both rows through the real command
    ws.invoke("remove_memo", {"id": seeded})
    ws.invoke("remove_memo", {"id": hung})
    time.sleep(0.5)
    left = conn.execute("SELECT count(*) FROM memo WHERE id IN (?, ?)", (seeded, hung)).fetchone()[0]
    conn.close()
    assert left == 0, f"cleanup failed, {left} rows left"
    print("R101 VERIFY PASS: placeholder for preview-less image memo, thumbnail intact")

if __name__ == "__main__":
    main()
