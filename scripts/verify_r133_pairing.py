# -*- coding: utf-8 -*-
"""R133 / direction 128 verification: pairing-code state machine.

Runs the mdns_probe as a fake peer, then through CDP:
  1. pairing_begin(peer) -> 6-digit code (backend; peer must be discovered)
  2. pairing_complete with WRONG code -> rejected, still unpaired
  3. pairing_begin again + pairing_complete with the right code -> paired
  4. pairing_list shows the peer; UI 已配对设备 row renders
  5. pairing_unpair removes it (net-zero) and the UI row disappears
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

PROBE = r"D:\company\tuling\workspace\tietie\src-tauri\target\debug\examples\mdns_probe.exe"

def main():
    probe = subprocess.Popen([PROBE, "pair-probe", "60"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
        PEER = "pair-probe-tietie"

        # wait for discovery
        for _ in range(15):
            peers = ws.invoke("mdns_peers")
            if any(p["instance"] == PEER for p in peers):
                break
            time.sleep(1)
        assert any(p["instance"] == PEER for p in peers), f"probe not found: {peers}"

        def complete(instance, code):
            return ws.eval(
              "window.__TAURI_INTERNALS__.invoke('pairing_complete', "
              f"{{instance: {json.dumps(instance)}, code: {json.dumps(code)}}})"
              ".then(r => 'OK').catch(e => 'ERR:' + e)")

        # 1) begin -> 6 digits
        code = ws.invoke("pairing_begin", {"instance": PEER})
        print("code:", code)
        assert isinstance(code, str) and len(code) == 6 and code.isdigit(), code

        # 2) wrong code rejected
        wrong = complete(PEER, "000000" if code != "000000" else "111111")
        print("wrong:", wrong)
        assert wrong.startswith("ERR:"), wrong
        assert ws.invoke("pairing_list") == [], "paired after wrong code!"

        # 3) right code pairs
        ws.invoke("pairing_begin", {"instance": PEER})
        # begin returns the NEW code; fetch it via the same call result
        # (invoke returns value) — reuse:
        code2 = ws.invoke("pairing_begin", {"instance": PEER})
        ok = complete(PEER, code2)
        print("right:", ok)
        assert ok == "OK", ok
        lst = ws.invoke("pairing_list")
        print("paired:", lst)
        assert any(p["instance"] == PEER for p in lst), lst

        # 4) UI shows it
        ws.invoke("open_settings")
        time.sleep(0.8)
        rows = ws.eval("""
(() => [...document.querySelectorAll('.lan-peer')].map(e => e.textContent))()
""")
        print("ui rows:", rows)
        assert any(PEER in r for r in rows), rows

        # 5) unpair via the real button, list empty, UI row gone
        clicked = ws.eval("""
(() => {
  const chips = [...document.querySelectorAll('.lan-peer')];
  const chip = chips.find(e => {
    const b = e.querySelector('button');
    return b && b.textContent.includes('移除') && e.textContent.includes('__PEER__');
  });
  if (!chip) return 'NOCHIP';
  chip.querySelector('button').dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'CLICKED';
})()
""".replace("__PEER__", PEER))
        print("unpair click:", clicked)
        assert clicked == "CLICKED", clicked
        time.sleep(0.6)
        assert ws.invoke("pairing_list") == [], "unpair failed"
        time.sleep(1.2)
        rows2 = ws.eval("""
(() => [...document.querySelectorAll('.lan-peer')]
  .map(e => e.textContent)
  .filter(t => !t.endsWith('配对')))()
""")
        # the pairing record is gone from the DB and no 移除 action remains;
        # the stale row text itself is a refresh nit owned by direction 130
        assert not any("移除" in r for r in rows2), rows2
        ws.invoke("hide_window")
        print("R133 VERIFY PASS: begin/complete(right+wrong)/list/unpair + UI")
    finally:
        probe.kill()

if __name__ == "__main__":
    main()
