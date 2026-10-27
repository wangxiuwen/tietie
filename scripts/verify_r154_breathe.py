# -*- coding: utf-8 -*-
"""R154 / direction 148 verification: selected-card breathing animation.

Show the drawer, assert the .selected card carries
animation card-breathe 2.2s infinite, and the keyframes rule exists.
Also assert the reduced-motion media query kills it under emulation.
"""
import sys, time, json, urllib.request
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
        return

def probe(ws):
    return ws.eval("""
(() => {
  const card = document.querySelector('.card.selected');
  if (!card) return JSON.stringify({ found: false });
  const cs = getComputedStyle(card);
  let hasKf = false;
  for (const sheet of document.styleSheets) {
    try {
      for (const rule of sheet.cssRules) {
        if (rule instanceof CSSKeyframesRule && rule.name === 'card-breathe') hasKf = true;
        if (rule.media) {
          for (const inner of rule.cssRules) {
            for (const r2 of inner.cssRules || []) {
              if (r2.media || r2.cssRules) continue;
            }
          }
        }
      }
    } catch (e) {}
  }
  return JSON.stringify({
    found: true,
    animName: cs.animationName,
    dur: cs.animationDuration,
    iter: cs.animationIterationCount,
    kf: hasKf,
  });
})()
""")

def main():
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
    ws.invoke("show_drawer")
    time.sleep(0.8)

    d = json.loads(probe(ws))
    print("normal:", d)
    assert d["found"], "no selected card"
    assert d["animName"] == "card-breathe", d
    assert d["dur"] == "2.2s" and d["iter"] == "infinite", d
    assert d["kf"] is True, d

    # reduced-motion emulation must kill it
    cdp_send(ws, "Emulation.setEmulatedMedia",
             {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]})
    time.sleep(0.3)
    d2 = json.loads(probe(ws))
    print("reduced:", d2)
    assert d2["animName"] == "none", d2
    cdp_send(ws, "Emulation.setEmulatedMedia",
             {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
    print("R154 VERIFY PASS: breathe anim on, keyframes present, reduced-motion off")

if __name__ == "__main__":
    main()
