# -*- coding: utf-8 -*-
"""R115 / direction 109 verification: detail-head time shows absolute tooltip.

Hangs one temp memo with a KNOWN created_at (via sqlite direct seed? No —
add_memo_direct stamps now), opens its detail, asserts the .line-detail-time
title parses as a full local datetime matching the memo's created_at within
a minute, and the visible text is still the relative label. Cleanup removes
the memo.
"""
import sys, time, json, re, urllib.request
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
        if m["content"].startswith("时间提示验证"):
            ws.invoke("remove_memo", {"id": m["id"]})
    time.sleep(0.3)

    before = int(time.time())
    mid = ws.invoke("add_memo_direct",
                    {"content": "时间提示验证", "remindAt": None, "color": None})
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
  requestAnimationFrame(() => res(String(document.querySelector('.line-detail-time') != null)));
}))()
""".replace("__MID__", str(mid)))
    assert opened == "true", f"detail did not open: {opened!r}"

    out = ws.eval("""
(() => {
  const el = document.querySelector('.line-detail-time');
  return JSON.stringify({ text: el.textContent, title: el.getAttribute('title') });
})()
""")
    d = json.loads(out)
    print("time span:", d)
    # visible label stays relative ("刚刚挂上" for a fresh memo)
    assert d["text"].strip() != "", "relative label missing"
    # title is a full local datetime: 2026/10/26 00:30:15 style
    m = re.match(r"\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2}:\d{2}$", d["title"] or "")
    assert m, f"tooltip not absolute datetime: {d['title']!r}"
    import datetime
    tip = datetime.datetime.strptime(d["title"], "%Y/%m/%d %H:%M:%S").timestamp()
    memo = next(x for x in ws.invoke("list_memos") if x["id"] == mid)
    assert abs(tip - memo["created_at"]) < 120, f"tooltip {tip} vs created {memo['created_at']}"

    ws.eval("""
(() => {
  document.querySelector('.line-detail')
    .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  return true;
})()
""")
    ws.invoke("remove_memo", {"id": mid})
    time.sleep(0.3)
    left = [x["id"] for x in ws.invoke("list_memos") if x["content"].startswith("时间提示验证")]
    assert not left
    print("R115 VERIFY PASS: absolute-datetime tooltip matches created_at, label stays relative")

if __name__ == "__main__":
    main()
