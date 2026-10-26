# -*- coding: utf-8 -*-
"""R119 / direction 113 verification: sensitive card masked by default.

Picks the newest text item (id captured up front), temporarily marks it
sensitive (set_item_sensitive — restored afterwards), searches it to the
front, and asserts on the REAL drawer UI:
  - body renders masked dots + reveal hint, aria-label is 🔒
  - clicking the masked body reveals the true content WITHOUT selecting
  - after ~5.5s the body re-masks automatically
Restore: sensitive flag off, search cleared.
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
            if t["url"].startswith("http://tauri.localhost/") and "?" not in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "drawer target not found"

    items = ws.invoke("list_items", {"limit": 100})
    target = next(x for x in items if x["kind"] == "text" and not x["sensitive"])
    tid, content = target["id"], target["content"]
    probe = content[:6]
    print("target:", tid, repr(content[:20]))
    assert not ws.invoke("set_item_sensitive", {"id": tid, "on": True}), "mark failed"
    time.sleep(0.5)

    ws.invoke("show_drawer")
    time.sleep(0.8)

    def type_query(q):
        ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, '%s');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""" % q)
        time.sleep(0.4)

    type_query(probe)
    state = ws.eval("""
(() => {
  const card = document.querySelector('.card[role="option"]');
  if (!card) return JSON.stringify({ card: false });
  return JSON.stringify({
    card: true,
    masked: !!card.querySelector('.body.masked'),
    text: card.querySelector('.body')?.textContent ?? '',
    aria: card.getAttribute('aria-label'),
    selected: card.classList.contains('selected'),
  });
})()
""")
    d = json.loads(state)
    print("masked state:", d)
    assert d["card"], "card not rendered"
    assert d["masked"] and "••••" in d["text"] and "点击显示" in d["text"], d
    assert d["aria"].endswith("🔒"), f"aria leaked content: {d['aria']!r}"

    # click the masked body -> reveals, does NOT select
    reveal = ws.eval("""
(() => new Promise(res => {
  const card = document.querySelector('.card[role="option"]');
  const body = card.querySelector('.body.masked');
  body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  requestAnimationFrame(() => requestAnimationFrame(() => res(JSON.stringify({
    masked: !!card.querySelector('.body.masked'),
    text: card.querySelector('.body')?.textContent ?? '',
    selected: card.classList.contains('selected'),
  }))));
}))()
""")
    r = json.loads(reveal)
    print("after click:", r)
    assert r["masked"] is False, "did not reveal"
    assert probe in r["text"], f"revealed text mismatch: {r['text'][:40]!r}"

    # auto re-mask after ~5s
    time.sleep(5.6)
    again = ws.eval("""
(() => {
  const card = document.querySelector('.card[role="option"]');
  return JSON.stringify({
    masked: !!card.querySelector('.body.masked'),
    aria: card.getAttribute('aria-label'),
  });
})()
""")
    a = json.loads(again)
    print("after 5.6s:", a)
    assert a["masked"] is True, "did not re-mask"
    assert a["aria"].endswith("🔒"), "aria not re-masked"

    # restore
    type_query("")
    ws.invoke("set_item_sensitive", {"id": tid, "on": False})
    time.sleep(0.4)
    back = next(x for x in ws.invoke("list_items", {"limit": 100}) if x["id"] == tid)
    assert back["sensitive"] is False, "sensitive flag not restored"
    print("R119 VERIFY PASS: masked default, click-reveal w/o select, 5s auto re-mask")

if __name__ == "__main__":
    main()
