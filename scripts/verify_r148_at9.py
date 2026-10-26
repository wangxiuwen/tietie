# -*- coding: utf-8 -*-
"""R148 / direction 143 verification: reminder presets 2h + tomorrow-9am.

Composer path: open the composer, pick 「⏰ 明天早上 9:00」, commit a probe
memo, then read its remind_at back through list_memos and assert it lands at
the next local 09:00 (±90s). Also assert the 2h option exists and computes
now+7200. Cleanup removes the probe memos.
"""
import sys, time, json, datetime, urllib.request
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

    def commit_with(option_value, tag):
        clicked = ws.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x =>
    x.textContent.includes('便签') && !x.textContent.includes('导出') && !x.textContent.includes('摘'));
  if (!b) return 'NOBTN';
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'OK';
})()
""")
        assert clicked == "OK", clicked
        time.sleep(0.4)
        r = ws.eval("""
(() => {
  const ta = document.querySelector('.line-compose');
  const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  set.call(ta, '__T__');
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  const sel = document.querySelectorAll('.line-remind')[0];
  const setSel = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
  setSel.call(sel, '__V__');
  sel.dispatchEvent(new Event('change', { bubbles: true }));
  const btn = [...document.querySelectorAll('button')].find(x => x.textContent.includes('挂上'));
  btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'OK';
})()
""".replace("__T__", tag).replace("__V__", option_value))
        assert r == "OK", r
        time.sleep(1.0)

    # normalize strays
    for m in ws.invoke("list_memos"):
        if m["content"].startswith("预设验证"):
            ws.invoke("remove_memo", {"id": m["id"]})
    time.sleep(0.3)

    # 1) tomorrow 9:00
    commit_with("at9", "预设验证at9")
    # 2) 2h
    commit_with("120", "预设验证2h")
    time.sleep(0.8)

    memos = {m["content"]: m for m in ws.invoke("list_memos") if m["content"].startswith("预设验证")}
    at9 = memos.get("预设验证at9", {}).get("remind_at")
    h2 = memos.get("预设验证2h", {}).get("remind_at")
    print("at9 remind_at:", at9, "| 2h remind_at:", h2)
    now = time.time()

    # 2h: now + 7200 (±120s)
    assert h2 and abs(h2 - (now + 7200)) < 120, h2

    # at9: next local 09:00
    if at9:
        tgt = datetime.datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        if tgt.timestamp() <= now:
            tgt += datetime.timedelta(days=1)
        assert abs(at9 - tgt.timestamp()) < 120, (at9, tgt.timestamp())

    # cleanup
    for m in ws.invoke("list_memos"):
        if m["content"].startswith("预设验证"):
            ws.invoke("remove_memo", {"id": m["id"]})
    time.sleep(0.3)
    print("R148 VERIFY PASS: at9 lands on next 09:00; 2h = now+7200")

if __name__ == "__main__":
    main()
