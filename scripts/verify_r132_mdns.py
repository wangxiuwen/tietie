# -*- coding: utf-8 -*-
"""R132 / direction 127 verification: mDNS device discovery.

Launches the repo's mdns_probe example (a SECOND _tietie-sync._tcp
advertiser on this machine), then checks:
  - the mdns_peers command resolves the probe (instance + addr)
  - the Settings LAN section lists it after a refresh click
Cleanup kills the probe; the peer eventually ages out (not asserted).
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

PROBE = r"D:\company\tuling\workspace\tietie\src-tauri\target\debug\examples\mdns_probe.exe"

def main():
    probe = subprocess.Popen([PROBE, "verify-probe", "40"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print("probe pid:", probe.pid)
    time.sleep(2)

    try:
        ws = None
        for _ in range(20):
            with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
                targets = json.load(r)
            for t in targets:
                if "view=settings" in t["url"]:
                    ws = CDP(t["webSocketDebuggerUrl"]); break
            if ws: break
            time.sleep(1)
        assert ws, "settings target not found"

        # 1) backend: peers resolves the probe within a poll window
        peers = None
        for _ in range(15):
            peers = ws.invoke("mdns_peers")
            if any(p["instance"] == "verify-probe-tietie" for p in peers):
                break
            time.sleep(1)
        print("peers:", peers)
        hit = next((p for p in peers if p["instance"] == "verify-probe-tietie"), None)
        assert hit, f"probe not discovered: {peers}"
        assert ":41784" in hit["addr"], f"bad addr: {hit['addr']}"
        assert hit["hostname"].startswith("verify-probe"), hit["hostname"]

        # 2) UI: settings LAN section lists it after refresh
        ws.invoke("open_settings")
        time.sleep(0.8)
        clicked = ws.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x => x.textContent === '刷新');
  if (!b) return 'NOBTN';
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'CLICKED';
})()
""")
        assert clicked == "CLICKED", clicked
        time.sleep(0.6)
        listed = ws.eval("""
(() => [...document.querySelectorAll('.lan-peer')].map(e => e.textContent))()
""")
        print("lan rows:", listed)
        assert any("verify-probe-tietie" in x for x in listed), listed
        ws.invoke("hide_window")
        print("R132 VERIFY PASS: mDNS probe discovered by command and shown in Settings")
    finally:
        probe.kill()

if __name__ == "__main__":
    main()
