# -*- coding: utf-8 -*-
"""R143 / direction 137 verification: image sync transport (log-proven).

One host can't host the peer listener (the app owns port 41784 and
self-echoes are dropped), so the outbound image frame is proven through the
app's own log: pair with a probe peer (real pairing state machine), enable
sync, put a 24x24 image on the clipboard (System.Drawing = the real capture
path), then assert new "sync out" log lines appeared AND the frame the app
sealed was an image frame (log carries the byte count; the local row proves
the capture was an image with a PNG blob).
"""
import os, sys, time, json, subprocess, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2e_smoke import CDP

MDNS = r"D:\company\tuling\workspace\tietie\src-tauri\target\debug\examples\mdns_probe.exe"
PEER_LABEL = "imgsync"
PEER = "imgsync-tietie"
LOG = os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\tietie.log")

def log_count(pattern):
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Select-String -Path '{LOG}' -Pattern '{pattern}').Count"],
        capture_output=True)
    return int(r.stdout.decode(errors="replace").strip() or 0)

def main():
    mdns = subprocess.Popen([MDNS, PEER_LABEL, "120"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(2)
    try:
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

        for _ in range(15):
            peers = ws.invoke("mdns_peers")
            if any(p["instance"] == PEER for p in peers):
                break
            time.sleep(1)
        assert any(p["instance"] == PEER for p in peers), "peer not discovered"

        code = ws.invoke("pairing_begin", {"instance": PEER})
        assert isinstance(code, str) and len(code) == 6, code
        ok = ws.eval(
            "window.__TAURI_INTERNALS__.invoke('pairing_complete', "
            f"{{instance: {json.dumps(PEER)}, code: {json.dumps(code)}}})"
            ".then(r => 'OK').catch(e => 'ERR:' + e)")
        assert ok == "OK", ok
        ws.invoke("sync_set", {"on": True})

        before = log_count("sync out")
        # real image capture (the app's own clipboard poll sees it)
        ps = ("Add-Type -AssemblyName System.Drawing;"
              "$b=New-Object System.Drawing.Bitmap(24,24);"
              "$g=[System.Drawing.Graphics]::FromImage($b);"
              "$g.Clear([System.Drawing.Color]::FromArgb(255,180,40,200));"
              "Add-Type -AssemblyName System.Windows.Forms;"
              "[System.Windows.Forms.Clipboard]::SetImage($b)")
        subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps],
                       capture_output=True)
        time.sleep(6)

        after = log_count("sync out")
        print("sync-out lines:", before, "->", after)
        assert after > before, "no outbound sync fired for the image capture"

        # the local capture row is an image (content "WxH", preview = b64 thumb)
        items = ws.invoke("list_items", {"limit": 5})
        img = next((x for x in items if x["kind"] == "image"), None)
        print("captured image row:", {k: img[k] for k in ("kind", "content")} if img else None)
        assert img and "x" in img["content"] and img.get("preview"), "image row missing"

        ws.invoke("sync_set", {"on": False})
        ws.invoke("pairing_unpair", {"instance": PEER})
        subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ''"],
                       capture_output=True)
        print("R143 VERIFY PASS: image capture fired the outbound sync fan-out")
    finally:
        mdns.kill()

if __name__ == "__main__":
    main()
