# -*- coding: utf-8 -*-
"""R130 / direction 125 verification: default pin color = OS accent.

Expected #0078d4 (computed from the live DWM ColorizationColor). Hangs a
memo with no explicit color (add_memo_direct path) and hangs a real TEXT
clip item (kind_color fallback path), asserts both memos' color == accent,
then removes both.
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

PS = ["powershell", "-NoProfile", "-Command"]

def main():
    # expected accent straight from the live registry
    raw = subprocess.run(
        PS + ["(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\DWM').ColorizationColor"],
        capture_output=True).stdout.decode().strip()
    expect = "#%06x" % (int(raw) & 0xFFFFFF)
    print("registry accent:", raw, "->", expect)

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

    # normalize strays
    for m in ws.invoke("list_memos"):
        if m["content"].startswith("强调色验证"):
            ws.invoke("remove_memo", {"id": m["id"]})

    # path 1: add_memo_direct default
    mid1 = ws.invoke("add_memo_direct",
                     {"content": "强调色验证A", "remindAt": None, "color": None})
    # path 2: hang a real text item (kind_color fallback)
    items = ws.invoke("list_items", {"limit": 50})
    text_item = next(x for x in items if x["kind"] == "text")
    mid2 = ws.invoke("hang_item", {"id": text_item["id"]})
    time.sleep(0.8)

    memos = {m["id"]: m for m in ws.invoke("list_memos")}
    c1 = memos.get(mid1, {}).get("color")
    c2 = memos.get(mid2, {}).get("color")
    print("direct color:", c1, "| hang color:", c2)
    assert c1 == expect, f"add_memo_direct default {c1!r} != accent {expect}"
    assert c2 == expect, f"hang_item fallback {c2!r} != accent {expect}"

    ws.invoke("remove_memo", {"id": mid1})
    ws.invoke("remove_memo", {"id": mid2})
    time.sleep(0.3)
    left = [m["id"] for m in ws.invoke("list_memos") if m["id"] in (mid1, mid2)]
    assert not left
    print("R130 VERIFY PASS: default pin color follows the OS accent both paths")

if __name__ == "__main__":
    main()
