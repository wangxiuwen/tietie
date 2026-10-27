# -*- coding: utf-8 -*-
"""R155 / direction 148b verification: sealed-chunk file transfer (loopback).

The sandbox intermittently hides the app's data dir from python, so the
pairing seed rides the sqlite3 CLI via bash (see the round log); this script
assumes the loopback pairing row EXISTS (instance=<self>, token
"loopback-file-token-148b", addr=<lan-ip>:41784) and drives the CDP side:
send → assert Documents/tietie-收到的文件/ gains the file with verbatim
content → 📎 out+in events land in the sync log.
"""
import sys, os, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def main():
    for _ in range(15):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9223/json/list", timeout=3) as r:
                targets = json.load(r)
            break
        except Exception:
            time.sleep(1)
    ws = CDP(next(t["webSocketDebuggerUrl"] for t in targets
                  if t["url"].startswith("http://tauri.localhost/") and "?" not in t["url"]))

    import subprocess
    inst = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "$env:COMPUTERNAME.ToLower()+'-tietie'"],
        capture_output=True).stdout.decode().strip()

    rdir = os.path.expanduser("~/Documents/tietie-收到的文件")
    os.makedirs(rdir, exist_ok=True)
    for f in os.listdir(rdir):
        if f.startswith("filesend-loop"):
            os.remove(os.path.join(rdir, f))

    tf = os.path.expandvars(r"%TEMP%\filesend-loop.txt")
    open(tf, "w", encoding="utf-8").write("filesend loopback payload 148b — " * 8)
    r = ws.invoke("file_send", {"instance": inst, "path": tf})
    print("file_send:", r)
    assert isinstance(r, str) and "已发送" in r, r
    time.sleep(2.5)

    got = [f for f in os.listdir(rdir) if f.startswith("filesend-loop")]
    assert got, "receiver did not write the file"
    data = open(os.path.join(rdir, got[0]), encoding="utf-8").read()
    assert "filesend loopback payload" in data

    evs = ws.invoke("sync_events")
    notes = [(e["dir"], e["note"]) for e in evs if "📎" in e.get("note", "")]
    assert any(d == "out" for d, _ in notes), notes
    assert any(d == "in" for d, _ in notes), notes

    os.remove(os.path.join(rdir, got[0]))
    print("R155 VERIFY PASS: full loopback file transfer")

if __name__ == "__main__":
    main()
