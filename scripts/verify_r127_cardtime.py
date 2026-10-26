# -*- coding: utf-8 -*-
"""R127 / direction 121 verification: card/row relative time carries an
absolute-datetime tooltip matching used_at.

Card view: the .meta time span's title parses as a full local datetime equal
to the first item's used_at. Compact row view: same for .row-meta.
"""
import sys, time, json, re, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

DT = re.compile(r"^\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2}:\d{2}$")

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

    items = ws.invoke("list_items", {"limit": 500})
    first = items[0]

    # card view tooltip
    card = ws.eval("""
(() => {
  const meta = document.querySelector('.card .meta');
  const spans = [...meta.querySelectorAll('span')];
  const t = spans.find(s => DT_RE.test(s.getAttribute('title') || ''));
  return JSON.stringify({ any: !!t, title: t ? t.getAttribute('title') : null,
    text: t ? t.textContent : null });
})()
""".replace("DT_RE", "/" + "^[0-9]{4}\\/[0-9]{1,2}\\/[0-9]{1,2} [0-9]{1,2}:[0-9]{2}:[0-9]{2}$" + "/"))
    d = json.loads(card)
    print("card time:", d)
    assert d["any"] and DT.match(d["title"]), f"card tooltip not datetime: {d}"
    import datetime
    tip = datetime.datetime.strptime(d["title"], "%Y/%m/%d %H:%M:%S").timestamp()
    assert abs(tip - first["used_at"]) < 120, f"card tip {tip} vs used_at {first['used_at']}"

    # switch to compact rows via the real toggle, check row tooltip
    ws.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x => x.title === '紧凑列表' || x.title === '卡片视图');
  if (b) b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""")
    time.sleep(0.5)
    row = ws.eval("""
(() => {
  const m = document.querySelector('.row-item .row-meta');
  return JSON.stringify({ title: m ? m.getAttribute('title') : null });
})()
""")
    r = json.loads(row)
    print("row meta:", r)
    assert r["title"] and DT.match(r["title"]), f"row tooltip not datetime: {r}"
    tip2 = datetime.datetime.strptime(r["title"], "%Y/%m/%d %H:%M:%S").timestamp()
    assert abs(tip2 - first["used_at"]) < 120, f"row tip {tip2} vs used_at {first['used_at']}"

    # restore card view
    ws.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x => x.title === '紧凑列表' || x.title === '卡片视图');
  if (b) b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""")
    time.sleep(0.3)
    print("R127 VERIFY PASS: card + compact row times carry absolute tooltips")

if __name__ == "__main__":
    main()
