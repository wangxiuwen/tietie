# -*- coding: utf-8 -*-
"""R134 / direction 129 verification: encrypted sync transport.

Setup (temp data, all reverted): sqlite seeds a pairing row for a fake peer
"sync-probe-tietie" @ 127.0.0.1:51784 with a known token; sync enabled via
command. Then:
  1. INBOUND: sync_probe send → app's server on 41784 decrypts with the
     pairing token, inserts the content (source_app = sender).
  2. REJECT: a frame sealed with a WRONG token is refused (no row, log line).
  3. OUTBOUND: sync_probe listen 51784 → Set-Clipboard new text → app pushes
     the sealed frame; probe decrypts and prints the content.
  4. ECHO SUPPRESSION: re-copying the exact inbound content does NOT push.
Cleanup: unpair, sync off, clipboard restored, sqlite leftovers removed.
"""
import sys, time, json, os, sqlite3, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

DB = os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\tietie.sqlite")
PROBE = r"D:\company\tuling\workspace\tietie\src-tauri\target\debug\examples\sync_probe.exe"
PEER = "sync-probe-tietie"
TOKEN = "probe-shared-token-129"
PS = ["powershell", "-NoProfile", "-Command"]

def clip_text():
    r = subprocess.run(PS + ["Get-Clipboard"], capture_output=True)
    return r.stdout.decode("gbk", errors="replace").strip()

def main():
    prior = clip_text()
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

    # normalize + seed pairing row
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("DELETE FROM pairing WHERE instance = ?", (PEER,))
    conn.execute(
        "INSERT INTO pairing (instance, addr, token, created_at) VALUES (?, ?, ?, ?)",
        (PEER, "127.0.0.1:51784", TOKEN, int(time.time())))
    conn.commit()
    conn.close()
    assert ws.invoke("sync_set", {"on": True}) is None, "enable failed"
    time.sleep(0.5)

    # 1) inbound
    out = subprocess.run([PROBE, "send", "127.0.0.1:41784", PEER, TOKEN,
                          "同步入站验证内容129"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    print("probe send:", out.stdout.strip(), out.stderr.strip()[:80])
    time.sleep(1.5)
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    row = conn.execute(
        "SELECT content, source_app FROM clip_item WHERE content = ? ORDER BY id DESC LIMIT 1",
        ("同步入站验证内容129",)).fetchone()
    conn.close()
    print("inbound row:", row)
    assert row and row[1] == PEER, f"inbound not recorded: {row}"

    # 2) wrong-token frame refused
    subprocess.run([PROBE, "send", "127.0.0.1:41784", PEER, "wrong-token-129",
                    "不应入库的密文"], capture_output=True)
    time.sleep(1.0)
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    bad = conn.execute("SELECT COUNT(*) FROM clip_item WHERE content = ?",
                       ("不应入库的密文",)).fetchone()[0]
    conn.close()
    assert bad == 0, "wrong-token frame was accepted!"

    # 3) outbound: probe listens, we copy something new
    listener = subprocess.Popen([PROBE, "listen", "51784", PEER, TOKEN],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
    time.sleep(1.0)
    subprocess.run(PS + ["Set-Clipboard -Value '同步出站验证内容129'"],
                   capture_output=True)
    deadline = time.time() + 15
    line = ""
    while time.time() < deadline:
        if listener.poll() is not None:
            line = listener.stdout.read()
            break
        time.sleep(0.5)
    if listener.poll() is None:
        listener.kill()
        line = listener.stdout.read()
    print("listener:", line.strip()[:200])
    assert "RECEIVED" in line and "同步出站验证内容129" in line, line

    # 4) echo suppression: copy the INBOUND content verbatim → no push
    listener2 = subprocess.Popen([PROBE, "listen", "51784", PEER, TOKEN],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace")
    time.sleep(1.0)
    subprocess.run(PS + ["Set-Clipboard -Value '同步入站验证内容129'"], capture_output=True)
    time.sleep(4)
    echo_pushed = listener2.poll() is not None  # accepted a frame => pushed
    listener2.kill()
    assert not echo_pushed, "echo suppression failed: inbound content was pushed back out"

    # cleanup: sync off, pairing row removed, probe rows pruned, clipboard restored
    ws.invoke("sync_set", {"on": False})
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("DELETE FROM pairing WHERE instance = ?", (PEER,))
    conn.execute("DELETE FROM clip_item WHERE content IN ('同步入站验证内容129','同步出站验证内容129')")
    conn.commit()
    conn.close()
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=prior.encode("utf-8"), capture_output=True)
    print("R134 VERIFY PASS: inbound sealed frame + wrong-token reject + outbound push + echo suppression")

if __name__ == "__main__":
    main()
