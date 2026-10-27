# -*- coding: utf-8 -*-
"""R152 / direction 144 verification: image-card fade-in.

The drawer must show at least one image card; assert its .img element
carries animation img-fade-in (0.28s ease-out) and the keyframes exist.
Also confirm a freshly-hung image card (screenshot-free clipboard image
via System.Drawing) animates the same way.
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

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

    items = ws.invoke("list_items", {"limit": 500})
    if not any(x["kind"] == "image" for x in items):
        # put an image on the clipboard through the REAL capture path
        ps = ("Add-Type -AssemblyName System.Drawing;"
              "$b=New-Object System.Drawing.Bitmap(48,32);"
              "$g=[System.Drawing.Graphics]::FromImage($b);"
              "$g.Clear([System.Drawing.Color]::FromArgb(255,10,120,220));"
              "Add-Type -AssemblyName System.Windows.Forms;"
              "[System.Windows.Forms.Clipboard]::SetImage($b)")
        subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps],
                       capture_output=True)
        time.sleep(4)

    ws.invoke("show_drawer")
    time.sleep(1.0)
    out = ws.eval("""
(() => {
  const cards = [...document.querySelectorAll('.card')];
  const imgCard = cards.find(c => c.querySelector('.img'));
  if (!imgCard) return JSON.stringify({ found: false, cards: cards.length });
  const img = imgCard.querySelector('.img');
  const cs = getComputedStyle(img);
  // confirm the keyframes rule exists in the stylesheet
  let hasKf = false;
  for (const sheet of document.styleSheets) {
    try {
      for (const rule of sheet.cssRules) {
        if (rule instanceof CSSKeyframesRule && rule.name === 'img-fade-in') {
          hasKf = true; break;
        }
      }
    } catch (e) { /* cross-origin sheet */ }
    if (hasKf) break;
  }
  return JSON.stringify({
    found: true,
    animName: cs.animationName,
    animDuration: cs.animationDuration,
    animTiming: cs.animationTimingFunction,
    keyframes: hasKf,
  });
})()
""")
    print(out)
    d = json.loads(out)
    assert d["found"], d
    assert d["animName"] == "img-fade-in", d
    assert d["animDuration"] == "0.28s", d
    assert d["animTiming"].startswith("ease-out"), d
    assert d["keyframes"] is True, d
    print("R152 VERIFY PASS: image cards animate img-fade-in 0.28s ease-out")

if __name__ == "__main__":
    main()
