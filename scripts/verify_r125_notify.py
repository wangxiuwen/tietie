# -*- coding: utf-8 -*-
"""R125 / direction 119 verification: due memo fires one system notification.

  1. notify_due command works standalone (returns Ok — a real toast shows on
     the user's screen) and writes a log line.
  2. The transition fires automatically: hang a memo with a reminder ~8s out
     and watch the app log for exactly ONE "due notification fired" line
     carrying the memo content within ~20s (the 3s tick catches the turn).
  3. No catch-up spam: the log gains no further lines for another 8s.
Cleanup removes the memo; log marker lines are counted only within the
observation window.
"""
import sys, time, json, os, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

LOG = os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\tietie.log")

def log_hits(marker):
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            return f.read().count(marker)
    except FileNotFoundError:
        return 0

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

    MARK = "due notification fired"
    base = log_hits(MARK)

    # 1) standalone command: Ok + one new log line (also pops a real toast)
    r = ws.invoke("notify_due", {"title": "贴贴便签提醒", "body": "通知链路自检"})
    assert r is None, f"notify_due failed: {r!r}"
    time.sleep(1.0)
    assert log_hits(MARK) == base + 1, "standalone notify did not log"

    # 2) transition: reminder ~8s out -> exactly one automatic fire
    for m in ws.invoke("list_memos"):
        if m["content"].startswith("到期通知验证"):
            ws.invoke("remove_memo", {"id": m["id"]})
    mid = ws.invoke("add_memo_direct",
                    {"content": "到期通知验证内容", "remindAt": int(time.time()) + 8,
                     "color": None})
    assert isinstance(mid, int)
    print("memo:", mid, "remind in 8s; waiting up to 24s for the tick to fire...")
    deadline = time.time() + 24
    fired = log_hits("due notification fired: 贴贴便签提醒 / 到期通知验证内容")
    while time.time() < deadline and log_hits("due notification fired: 贴贴便签提醒 / 到期通知验证内容") == 0:
        time.sleep(2)
    n = log_hits("due notification fired: 贴贴便签提醒 / 到期通知验证内容")
    print("auto fires:", n)
    assert n == 1, f"expected exactly 1 auto notification, got {n}"

    # 3) no repeat spam afterwards
    time.sleep(8)
    n2 = log_hits("due notification fired: 贴贴便签提醒 / 到期通知验证内容")
    assert n2 == 1, f"notification repeated: {n2}"

    ws.invoke("remove_memo", {"id": mid})
    time.sleep(0.3)
    left = [m["id"] for m in ws.invoke("list_memos") if m["id"] == mid]
    assert not left
    print("R125 VERIFY PASS: due transition fires exactly one system notification")

if __name__ == "__main__":
    main()
