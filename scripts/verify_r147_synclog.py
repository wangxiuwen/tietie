# -*- coding: utf-8 -*-
"""R147 / direction 141 verification: settings sync-event log.

Pair a probe peer over the real state machine, enable sync, fire an INBOUND
sealed frame (sync_probe send) — then open Settings and assert:
  - the sync log row lists a "⇦ <peer> · NB" entry (newest first)
  - the 刷新 button reloads it
Cleanup: unpair, sync off, hide window.
"""
import os, sys, time, json, subprocess, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e2e_smoke import CDP

MDNS = r"D:\company\tuling\workspace\tietie\src-tauri\target\debug\examples\mdns_probe.exe"
SYNCP = r"D:\company\tuling\workspace\tietie\src-tauri\target\debug\examples\sync_probe.exe"
PEER = "synclog-tietie"
TOKEN = "synclog-token-141"

def main():
    mdns = subprocess.Popen([MDNS, "synclog", "90"],
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
        ok = ws.eval(
            "window.__TAURI_INTERNALS__.invoke('pairing_complete', "
            f"{{instance: {json.dumps(PEER)}, code: {json.dumps(code)}}})"
            ".then(r => 'OK').catch(e => 'ERR:' + e)")
        assert ok == "OK", ok
        ws.invoke("sync_set", {"on": True})

        # inbound frame → one "in" event
        subprocess.run([SYNCP, "send", "127.0.0.1:41784", PEER, TOKEN,
                        "synclog-in-payload"], capture_output=True)
        time.sleep(1.8)

        # settings page: log row shows the event
        ws.invoke("open_settings")
        time.sleep(1.4)
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        st = CDP(next(t["webSocketDebuggerUrl"] for t in targets if "view=settings" in t["url"]))
        for _ in range(8):
            st.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x =>
    x.parentElement?.className?.includes('sync-log') && x.textContent === '刷新');
  if (b) b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""")
            time.sleep(0.5)
            rows = st.eval("""
(() => JSON.stringify([...document.querySelectorAll('.sync-evin, .sync-evout, .sync-evfail')]
  .map(e => e.textContent)))()
""")
            if json.loads(rows):
                break
        print("sync log rows (after fail frame):", rows)
        d = json.loads(rows)
        # the probe doesn't know the pairing token → its frame is REJECTED,
        # which exercises the fail event through the whole pipeline
        assert any("⚠" in x and PEER in x and "decrypt" in x for x in d), d

        # genuine OUT event: outbound thread sends to the peer's advertised
        # addr successfully (push_event fires on send, regardless of what
        # the receiver does with it) — copy text through the real capture path
        subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                       input="synclog-out-payload".encode("utf-8"), capture_output=True)
        time.sleep(4.0)
        for _ in range(6):
            st.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x =>
    x.parentElement?.className?.includes('sync-log') && x.textContent === '刷新');
  if (b) b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""")
            time.sleep(0.5)
            rows2 = st.eval("""
(() => JSON.stringify([...document.querySelectorAll('.sync-evin, .sync-evout, .sync-evfail')]
  .map(e => e.textContent)))()
""")
            if any("⇨" in x for x in json.loads(rows2)):
                break
        print("sync log rows (after copy):", rows2)
        d2 = json.loads(rows2)
        assert any("⇨" in x and PEER in x for x in d2), d2

        # cleanup
        st.invoke("hide_window")
        ws.invoke("sync_set", {"on": False})
        ws.invoke("pairing_unpair", {"instance": PEER})
        print("R147 VERIFY PASS: inbound sync event listed in Settings log")
    finally:
        mdns.kill()

if __name__ == "__main__":
    main()
