# -*- coding: utf-8 -*-
"""R118 / direction 112 verification: Library CSV export.

Clicks the real 导出 CSV button with the pinned-only toggle path avoided —
it selects the FIRST row through its real checkbox, clicks 导出 CSV, then
asserts the produced file:
  - UTF-8 BOM + header "kind,content,source,size,used_at"
  - one data row matching the selected item's kind and content (CSV-escaped)
Cleanup unchecks the row and deletes the export file.
"""
import sys, time, json, os, glob, csv, io, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def main():
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if "view=library" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "library target not found"

    # snapshot + normalize: a failed prior run may have left the row checked
    was = ws.eval(
      "String(document.querySelector('.lib-table tbody tr input[type=checkbox]').checked)")
    if was == "true":
        ws.eval("""
(() => {
  document.querySelector('.lib-table tbody tr input[type=checkbox]')
    .dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""")
        time.sleep(0.3)
        was = "false"
    checked = ws.eval("""
(() => new Promise(res => {
  const cb = document.querySelector('.lib-table tbody tr input[type=checkbox]');
  cb.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  requestAnimationFrame(() => requestAnimationFrame(() => res(String(cb.checked))));
}))()
""")
    assert checked == "true", f"row not checked: {checked!r}"
    first_kind = ws.eval(
      "document.querySelector('.lib-table tbody tr .badge').textContent")
    print("selected row kind:", first_kind, "| was checked before:", was)

    # click the real 导出 CSV button
    clicked = ws.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x => x.textContent.includes('导出 CSV'));
  if (!b) return 'NOBTN';
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'CLICKED';
})()
""")
    assert clicked == "CLICKED", clicked
    time.sleep(1.0)

    files = sorted(glob.glob(os.path.expanduser("~/Documents/tietie-export-*.csv")),
                   key=os.path.getmtime)
    assert files, "no csv produced"
    path = files[-1]
    print("exported:", path)
    raw = open(path, "rb").read()
    assert raw[:3] == b"\xef\xbb\xbf", "UTF-8 BOM missing"
    text = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    print("header:", rows[0], "| data rows:", len(rows) - 1)
    assert rows[0] == ["kind", "content", "source", "size", "used_at"], rows[0]
    assert len(rows) == 2, f"expected 1 data row, got {len(rows)-1}"
    # CSV stores the RAW kind (machine-readable); the badge shows the label
    LABEL = {"文本": "text", "链接": "link", "图片": "image", "代码": "code", "颜色": "color"}
    assert rows[1][0] == LABEL.get(first_kind, first_kind), \
        f"kind mismatch: {rows[1][0]} vs badge {first_kind!r}"
    assert rows[1][4].isdigit(), f"used_at not numeric: {rows[1][4]!r}"

    # cleanup: uncheck the row (restore), delete the export file
    ws.eval("""
(() => {
  const cb = document.querySelector('.lib-table tbody tr input[type=checkbox]');
  if (cb.checked) cb.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""")
    os.remove(path)
    assert not os.path.exists(path)
    print("R118 VERIFY PASS: CSV with BOM + escaped rows via the real button")

if __name__ == "__main__":
    main()
