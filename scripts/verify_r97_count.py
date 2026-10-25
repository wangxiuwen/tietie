# -*- coding: utf-8 -*-
"""R97 / direction 91 verification: memo-detail character/line counter.

Flow: hang a temp memo "计数一\n二三行\nx" (7 code points sans newlines, 3 lines)
      open its detail via pointerdown+pointerup (the real open path)
      assert head counter reads "7 字 · 3 行"
      click 编辑, rewrite the draft to "甲乙" via native setter + input event
      assert counter updates live to "2 字 · 1 行"
      cleanup: Esc-close detail, remove the temp memo.
"""
import sys, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def find_target():
    with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
        targets = json.load(r)
    for t in targets:
        if "view=line" in t["url"]:
            return CDP(t["webSocketDebuggerUrl"])
    return None

def main():
    ws = None
    for _ in range(20):
        ws = find_target()
        if ws: break
        time.sleep(1)
    assert ws, "clothesline target not found"

    content = "计数一\n二三行\nx"
    mid = ws.invoke("add_memo_direct", {"content": content, "remindAt": None, "color": None})
    assert isinstance(mid, int), f"add_memo_direct -> {mid!r}"
    print("temp memo id:", mid)
    time.sleep(0.8)

    # open the detail: pointerdown on the card, then pointerup on window
    opened = ws.eval(f"""
(() => new Promise(res => {{
  const card = document.querySelector('.line-card[data-memo="{mid}"]');
  if (!card) return res('NOCARD');
  const r = card.getBoundingClientRect();
  card.dispatchEvent(new PointerEvent('pointerdown', {{
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
    screenX: 500, screenY: 500,
  }}));
  window.dispatchEvent(new PointerEvent('pointerup', {{
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
    screenX: 500, screenY: 500,
  }}));
  requestAnimationFrame(() => res(document.querySelector('.line-detail-count')?.textContent ?? 'NONE'));
}}))()
""".replace("{{", "{").replace("}}", "}"))
    print("view-mode counter:", opened)
    assert opened == "7 字 · 3 行", f"unexpected counter: {opened!r}"

    # enter edit mode through the real 编辑 button, then rewrite the draft
    live = ws.eval("""
(() => new Promise(res => {
  const btns = [...document.querySelectorAll('.line-detail-actions button')];
  const edit = btns.find(b => b.textContent === '编辑');
  if (!edit) return res('NOEDIT');
  edit.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const ta = document.querySelector('.line-detail-edit');
    if (!ta) return res('NOTA');
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    set.call(ta, '甲乙');
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    requestAnimationFrame(() => res(document.querySelector('.line-detail-count')?.textContent ?? 'NONE'));
  }));
}))()
""".replace("{{", "{").replace("}}", "}"))
    print("edit-mode live counter:", live)
    assert live == "2 字 · 1 行", f"unexpected live counter: {live!r}"

    # cleanup: close detail via Esc, then remove the temp memo
    ws.eval("""
(() => {
  const el = document.querySelector('.line-detail');
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.4)
    assert "true" == ws.eval("String(document.querySelector('.line-detail') == null)"), "detail did not close"
    out = ws.invoke("remove_memo", {"id": mid})
    print("remove_memo:", out)
    time.sleep(0.5)
    gone = ws.eval(f"String(document.querySelector('.line-card[data-memo=\"{mid}\"]') == null)")
    assert gone == "true", "temp memo card still on the rope"
    print("R97 VERIFY PASS: detail counter 7字·3行, live edit 2字·1行, cleanup OK")

if __name__ == "__main__":
    main()
