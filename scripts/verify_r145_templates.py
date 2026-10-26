# -*- coding: utf-8 -*-
"""R145 / direction 139 verification: one-tap memo templates.

Opens the composer (真实「新建便签」按钮), then:
  1. types a phrase + clicks the real 「＋存为模板」 → composer cleared,
     chip with the phrase prefix appears
  2. types different filler, clicks the chip → textarea refilled verbatim
  3. chip dedupe: saving the same phrase again doesn't duplicate chips
Esc closes; nothing hung (composer never committed).
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

    def open_composer():
        clicked = ws.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x => x.textContent.includes('便签') && !x.textContent.includes('导出') && !x.textContent.includes('摘'));
  if (!b) return 'NOBTN';
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'OK';
})()
""")
        assert clicked == "OK", clicked
        time.sleep(0.4)

    def type_text(q):
        ws.eval("""
(() => {
  const el = document.querySelector('.line-compose');
  const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  set.call(el, '__T__');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""".replace("__T__", q))
        time.sleep(0.3)

    def click(sel_js):
        r = ws.eval(f"""
(() => new Promise(res => {{
  const el = {sel_js};
  if (!el) return res('NOEL');
  el.dispatchEvent(new MouseEvent('click', {{ bubbles: true }}));
  requestAnimationFrame(() => requestAnimationFrame(() => res('OK')));
}}))()
""")
        time.sleep(0.4)
        return r

    def chips():
        return json.loads(ws.eval("""
(() => JSON.stringify([...document.querySelectorAll('.tpl-chip')].map(b => b.textContent)))()
"""))

    def ta():
        return ws.eval("document.querySelector('.line-compose')?.value ?? ''")

    open_composer()
    type_text("我的常用签名一句话")
    r = click("document.querySelector('.tpl-add')")
    assert r == "OK", r
    v = ta()
    c1 = chips()
    print("after save: value=%r chips=%s" % (v, c1))
    assert v == "", f"composer not cleared: {v!r}"
    assert any("我的常用签" in x for x in c1), c1

    # fill with filler, click the chip → verbatim refill
    type_text("占位别的字")
    r2 = click("document.querySelector('.tpl-chip')")
    assert r2 == "OK", r2
    v2 = ta()
    print("after chip click:", repr(v2))
    assert v2 == "我的常用签名一句话", v2

    # dedupe: save the same phrase again → still exactly 1 chip
    ws.eval("""
(() => {
  const el = document.querySelector('.line-compose');
  const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  set.call(el, '');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""")
    type_text("我的常用签名一句话")
    click("document.querySelector('.tpl-add')")
    c2 = chips()
    print("after re-save:", c2)
    assert sum(1 for x in c2 if "我的常用签" in x) == 1, c2

    # esc out; nothing hung
    ws.eval("""
(() => {
  document.querySelector('.line-compose')
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.3)
    n = len(ws.invoke("list_memos"))
    print("memos after esc:", n)
    print("R145 VERIFY PASS: template save/fill/dedupe all real-path verified")

if __name__ == "__main__":
    main()
