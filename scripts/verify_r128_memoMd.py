# -*- coding: utf-8 -*-
"""R128 / direction 122 verification: link memos export as [label](url).

Hangs a temp link memo (sqlite seed: kind=link, content=github URL — then a
hang of a real item triggers the reload), clicks the real 导出便签 button,
asserts the md contains `- [github.com/…](full-url)`, then cleans the memo
and the export file.
"""
import sys, time, json, os, glob, re, sqlite3, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

DB = os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\tietie.sqlite")
URL = "https://github.com/wangxiuwen/tietie/issues/42"

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
        if m["content"].startswith("https://github.com/wangxiuwen/tietie/issues"):
            ws.invoke("remove_memo", {"id": m["id"]})

    # seed a link memo (direct sqlite), then hang a real item to refresh
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute(
        "INSERT INTO memo (kind, content, preview, color, source_item_id, created_at, sort) "
        "VALUES ('link', ?, '', '#007aff', NULL, ?, "
        "(SELECT COALESCE(MAX(sort), -1) + 1 FROM memo))",
        (URL, int(time.time())))
    conn.commit()
    seeded = conn.execute(
        "SELECT id FROM memo WHERE content = ? ORDER BY id DESC LIMIT 1", (URL,)).fetchone()[0]
    conn.close()
    print("seeded link memo:", seeded)
    control = ws.invoke("add_memo_direct",
                        {"content": "链接导出对照卡", "remindAt": None, "color": None})
    time.sleep(0.8)

    clicked = ws.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x => x.textContent.includes('导出便签'));
  if (!b) return 'NOBTN';
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'CLICKED';
})()
""")
    assert clicked == "CLICKED", clicked
    time.sleep(1.0)

    files = sorted(glob.glob(os.path.expanduser("~/Documents/notes-*.md")),
                   key=os.path.getmtime)
    assert files, "no notes md produced"
    md = open(files[-1], encoding="utf-8").read()
    print("exported:", files[-1])
    m = re.search(r"^- \[([^\]]+)\]\((https://github\.com/wangxiuwen/tietie/issues/42)\)$", md, re.M)
    assert m, f"link memo line not markdownified:\n{md[:300]}"
    label, target = m.group(1), m.group(2)
    assert target == URL and label.startswith("github.com/") and "://" not in label, \
        f"bad label/target: {label!r} {target!r}"

    # cleanup
    ws.invoke("remove_memo", {"id": seeded})
    ws.invoke("remove_memo", {"id": control})
    os.remove(files[-1])
    time.sleep(0.3)
    left = [x["id"] for x in ws.invoke("list_memos") if x["id"] in (seeded, control)]
    assert not left and not os.path.exists(files[-1])
    print("R128 VERIFY PASS: link memo exports as [github.com/…](full-url)")

if __name__ == "__main__":
    main()
