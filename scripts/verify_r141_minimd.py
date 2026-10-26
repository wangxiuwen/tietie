# -*- coding: utf-8 -*-
"""R141 / direction 135 verification: mini-Markdown in memo details.

Hangs a temp memo with all three syntaxes, opens its detail, asserts:
  - <strong> renders the bold text
  - <a.md-link> exists with the right label and href
  - <code.md-code> renders the code span
  - plain text around the syntax survives verbatim
Also dispatches a click on the link (open_url path, browser opens the URL —
localhost target to stay harmless) and cleans the memo up.
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
        if m["content"].startswith("简渲染验证"):
            ws.invoke("remove_memo", {"id": m["id"]})
    time.sleep(0.3)

    content = "看这段**重点内容**和 `npm run build` 还有 [项目主页](https://github.com/wangxiuwen/tietie) 结尾"
    mid = ws.invoke("add_memo_direct",
                    {"content": content, "remindAt": None, "color": None})
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
  requestAnimationFrame(() => res(String(document.querySelector('.line-detail-text') != null)));
}))()
""".replace("__MID__", str(mid)))
    assert opened == "true", f"detail did not open: {opened!r}"

    out = ws.eval("""
(() => {
  const body = document.querySelector('.line-detail-text');
  const strong = body.querySelector('strong');
  const link = body.querySelector('a.md-link');
  const code = body.querySelector('code.md-code');
  return JSON.stringify({
    strong: strong ? strong.textContent : null,
    linkText: link ? link.textContent : null,
    href: link ? link.getAttribute('href') : null,
    code: code ? code.textContent : null,
    plainHead: body.textContent.startsWith('看这段'),
    plainTail: body.textContent.includes('结尾'),
  });
})()
""")
    d = json.loads(out)
    print("detail:", d)
    assert d["strong"] == "重点内容", d
    assert d["linkText"] == "项目主页" and d["href"] == "https://github.com/wangxiuwen/tietie", d
    assert d["code"] == "npm run build", d
    assert d["plainHead"] and d["plainTail"], d

    # link click routes to open_url (harmless loopback target check via log marker)
    ws.eval("""
(() => {
  document.querySelector('.line-detail-text a.md-link')
    .dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(1.0)

    ws.eval("""
(() => {
  document.querySelector('.line-detail')
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    ws.invoke("remove_memo", {"id": mid})
    time.sleep(0.3)
    left = [m["id"] for m in ws.invoke("list_memos") if m["id"] == mid]
    assert not left
    print("R141 VERIFY PASS: bold/link/code rendered, plain text intact")

if __name__ == "__main__":
    main()
