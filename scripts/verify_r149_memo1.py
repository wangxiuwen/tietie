# -*- coding: utf-8 -*-
"""R149 / direction 145 verification: export one memo as txt.

Hangs a two-line probe memo, opens its detail via the real pointer path,
clicks the real 「存为 txt」 button, then asserts Documents/memo-<id>.txt
exists with BOTH lines verbatim. Cleanup: remove memo + export file.
"""
import sys, time, json, os, glob, urllib.request
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

    ws.eval("""
(() => {
  const d = document.querySelector('.line-detail');
  if (d) d.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    for m in ws.invoke("list_memos"):
        if m["content"].startswith("单张导出验证"):
            ws.invoke("remove_memo", {"id": m["id"]})
    time.sleep(0.3)

    mid = ws.invoke("add_memo_direct",
                    {"content": "单张导出验证第一行\n第二行原样保留", "remindAt": None, "color": None})
    assert isinstance(mid, int)
    time.sleep(0.6)

    opened = ws.eval("""
(() => new Promise(res => {
  const card = document.querySelector('.line-card[data-memo="__MID__"]');
  if (!card) return res('NOCARD');
  const b = card.getBoundingClientRect();
  card.dispatchEvent(new PointerEvent('pointerdown', {
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: b.left + b.width / 2, clientY: b.top + b.height / 2, screenX: 500, screenY: 500 }));
  window.dispatchEvent(new PointerEvent('pointerup', {
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: b.left + b.width / 2, clientY: b.top + b.height / 2, screenX: 500, screenY: 500 }));
  requestAnimationFrame(() => res(String(document.querySelector('.line-detail') != null)));
}))()
""".replace("__MID__", str(mid)))
    assert opened == "true", opened

    # stale file from earlier attempts?
    for f in glob.glob(os.path.expanduser(f"~/Documents/memo-{mid}.txt")):
        os.remove(f)

    clicked = ws.eval("""
(() => new Promise(res => {
  const b = [...document.querySelectorAll('.line-detail-actions button')]
    .find(x => x.textContent === '存为 txt');
  if (!b) return res('NOBTN');
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  requestAnimationFrame(() => res('CLICKED'));
}))()
""")
    assert clicked == "CLICKED", clicked
    time.sleep(1.2)

    path = os.path.expanduser(f"~/Documents/memo-{mid}.txt")
    assert os.path.exists(path), "export file missing"
    txt = open(path, encoding="utf-8").read()
    print("exported:", path, repr(txt[:40]))
    assert txt == "单张导出验证第一行\n第二行原样保留", repr(txt)

    ws.eval("""
(() => {
  document.querySelector('.line-detail')
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    ws.invoke("remove_memo", {"id": mid})
    os.remove(path)
    time.sleep(0.3)
    print("R149 VERIFY PASS: single memo exported with newlines intact")

if __name__ == "__main__":
    main()
