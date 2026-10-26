# -*- coding: utf-8 -*-
"""R112 / direction 106 verification: Ctrl+click opens link rows in browser.

  1. open_url rejects a non-http(s) scheme (no OS spawn)
  2. open_url accepts a valid URL and spawns the opener — use a localhost
     no-service URL so the default browser opens a harmless error tab
  3. UI wiring: trusted Ctrl+click on the real link row does NOT toggle its
     selection checkbox (the open branch ran instead) — the row's own URL
     (github.com) opens once in the default browser, which is the feature.
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def cdp_send(ws, method, params):
    ws.seq += 1
    rid = ws.seq
    ws.ws.send(json.dumps({"id": rid, "method": method, "params": params}))
    while True:
        msg = json.loads(ws.ws.recv_text())
        if msg.get("id") != rid:
            continue
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return msg.get("result", {})

def trusted_ctrl_click(ws, x, y):
    for typ in ("mousePressed", "mouseReleased"):
        cdp_send(ws, "Input.dispatchMouseEvent", {
            "type": typ, "x": x, "y": y, "button": "left",
            "buttons": 1 if typ == "mousePressed" else 0, "clickCount": 1,
            "modifiers": 2,  # Ctrl
        })
        time.sleep(0.1)

def main():
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if "view=library" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "library target not found"

    # 1) validation rejects non-http(s)
    r1 = ws.eval(
      "window.__TAURI_INTERNALS__.invoke('open_url', {url: 'ftp://example.com/x'})"
      ".then(() => 'OK').catch(e => 'ERR:' + e)"
    )
    print("ftp ->", r1)
    assert str(r1).startswith("ERR:") and "http" in str(r1), f"expected rejection, got {r1!r}"

    # 2) valid URL spawns the opener (localhost:9 = no service, error tab)
    r2 = ws.invoke("open_url", {"url": "http://127.0.0.1:9/"})
    print("http://127.0.0.1:9/ ->", r2)
    assert r2 is None, f"open failed: {r2!r}"

    # 3) wiring: Ctrl+click on the link row must NOT toggle selection
    info = ws.eval("""
(() => {
  const rows = [...document.querySelectorAll('.lib-table tbody tr')];
  const row = rows.find(tr => tr.querySelector('.badge.link') != null);
  if (!row) return 'NOLINK';
  const cb = row.querySelector('input[type=checkbox]');
  const r = row.getBoundingClientRect();
  return JSON.stringify({ checked: cb.checked, x: r.x + r.width / 2, y: r.y + r.height / 2 });
})()
""")
    assert info != "NOLINK", "no link row rendered"
    d = json.loads(info)
    print("link row before:", d)

    trusted_ctrl_click(ws, d["x"], d["y"])
    time.sleep(1.0)
    after = ws.eval("""
(() => {
  const rows = [...document.querySelectorAll('.lib-table tbody tr')];
  const row = rows.find(tr => tr.querySelector('.badge.link') != null);
  return String(row.querySelector('input[type=checkbox]').checked);
})()
""")
    print("checked after ctrl+click:", after)
    assert after == str(d["checked"]).lower(), "ctrl+click toggled selection instead of opening"

    print("R112 VERIFY PASS: scheme guard + opener spawn + ctrl-click wiring")

if __name__ == "__main__":
    main()
