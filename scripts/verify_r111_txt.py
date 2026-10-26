# -*- coding: utf-8 -*-
"""R111 / direction 105 verification: clothesline TXT export.

Hangs one temp multi-line memo (to prove newlines survive the plain-text
dump), clicks the real 导出纯文本 button, asserts:
  - the produced file is notes-<ts>.txt with the plain header
  - the memo's two lines appear verbatim on separate lines
  - the separator line exists between memos (>=2 memos on the line)
Then removes the temp memo and the export file (net-zero).
"""
import sys, time, json, os, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

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

    mid = ws.invoke("add_memo_direct",
                    {"content": "导出验证第一行\n导出验证第二行", "remindAt": None, "color": None})
    mid2 = ws.invoke("add_memo_direct",
                     {"content": "导出验证伴随卡", "remindAt": None, "color": None})
    assert isinstance(mid, int) and isinstance(mid2, int)
    print("temp memos:", mid, mid2)
    time.sleep(0.6)

    # click the real 导出纯文本 button
    clicked = ws.eval("""
(() => new Promise(res => {
  const btns = [...document.querySelectorAll('button')];
  const b = btns.find(x => x.textContent.includes('导出纯文本'));
  if (!b) return res('NOBTN');
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  requestAnimationFrame(() => res('CLICKED'));
}))()
""")
    assert clicked == "CLICKED", f"button: {clicked!r}"
    time.sleep(1.0)

    # locate the newest notes-*.txt in Documents
    import glob
    files = sorted(glob.glob(os.path.expanduser("~/Documents/notes-*.txt")),
                   key=os.path.getmtime)
    assert files, "no notes-*.txt produced"
    path = files[-1]
    print("exported:", path)
    txt = open(path, encoding="utf-8").read()
    assert txt.startswith("贴贴便签（"), f"bad header: {txt[:30]!r}"
    assert "导出验证第一行\n导出验证第二行" in txt, "newlines not preserved"
    assert "────────────────" in txt, "separator missing"
    assert not txt.lstrip().startswith("#"), "markdown leaked into txt"

    # cleanup: temp memos + export file
    ws.invoke("remove_memo", {"id": mid})
    ws.invoke("remove_memo", {"id": mid2})
    os.remove(path)
    time.sleep(0.3)
    left = [m["id"] for m in ws.invoke("list_memos") if m["id"] in (mid, mid2)]
    assert not left and not os.path.exists(path)
    print("R111 VERIFY PASS: TXT export via real button, newlines kept, cleaned up")

if __name__ == "__main__":
    main()
