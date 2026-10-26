# -*- coding: utf-8 -*-
"""R120 / direction 114 verification: context-menu 备注 opens the detail
with the note input focused.

Hangs a temp memo, right-clicks it via real contextmenu event, clicks the
菜单里的「📝 添加备注…」item, asserts the detail opened in VIEW mode (not
edit) with focus inside .line-note-input, then types a note through the
input's real onKeyDown Enter path — wait: Enter saves via invoke; use the
input event + Enter keydown to persist, verify set_memo_note landed via
list_memos, then remove the memo (note goes with it).
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

    # normalize leftovers
    ws.eval("""
(() => {
  const d = document.querySelector('.line-detail');
  if (d) d.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    for m in ws.invoke("list_memos"):
        if m["content"].startswith("右键备注验证"):
            ws.invoke("remove_memo", {"id": m["id"]})
    time.sleep(0.3)

    mid = ws.invoke("add_memo_direct",
                    {"content": "右键备注验证", "remindAt": None, "color": None})
    assert isinstance(mid, int)
    time.sleep(0.6)

    # open the context menu on the card via the real onContextMenu path
    ws.eval("""
(() => {
  const card = document.querySelector('.line-card[data-memo="__MID__"]');
  card.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 200, clientY: 200 }));
  return true;
})()
""".replace("__MID__", str(mid)))
    time.sleep(0.4)
    items = ws.eval("""
(() => JSON.stringify([...document.querySelectorAll('.ctx-item, [class*=ctx] .menu-item, [class*=menu] button, [class*=menu] [role=menuitem], [class*=ctx] li')]
  .map(el => el.textContent).filter(Boolean)))()
""")
    print("menu items:", items)
    # find the note item generically: any menu entry mentioning 备注
    clicked = ws.eval("""
(() => {
  const cands = [...document.querySelectorAll('button, [role=menuitem], li, .menu-item')]
    .filter(el => el.textContent.includes('备注'));
  if (!cands.length) return 'NOITEM';
  cands[0].dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'CLICKED:' + cands[0].textContent;
})()
""")
    print("note item:", clicked)
    assert clicked.startswith("CLICKED"), f"context note item missing: {items}"
    time.sleep(0.5)

    state = ws.eval("""
(() => {
  const note = document.querySelector('.line-note-input');
  return JSON.stringify({
    detail: !!document.querySelector('.line-detail'),
    editing: !!document.querySelector('.line-detail-edit'),
    noteFocused: note ? document.activeElement === note : false,
  });
})()
""")
    d = json.loads(state)
    print("detail state:", d)
    assert d["detail"] and not d["editing"], "detail not open in view mode"
    assert d["noteFocused"], "note input not focused"

    # type a note and press Enter through the real input path
    ws.eval("""
(() => {
  const el = document.querySelector('.line-note-input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, '右键写的备注');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.6)
    memo = next(m for m in ws.invoke("list_memos") if m["id"] == mid)
    print("note saved:", memo.get("note"))
    assert memo.get("note") == "右键写的备注", f"note not persisted: {memo.get('note')!r}"

    # cleanup
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
    print("R120 VERIFY PASS: ctx-menu 备注 opens detail with note input focused + Enter saves")

if __name__ == "__main__":
    main()
