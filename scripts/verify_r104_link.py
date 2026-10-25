# -*- coding: utf-8 -*-
"""R104 / direction 98 verification: link-card inline 🔗 copy.

Shows the drawer, surfaces link cards (search "http"), asserts the 🔗 button
renders inside the link title, then drives a TRUSTED CDP Input click on it
and checks the OS clipboard received the exact URL. Prior clipboard restored.
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

PS = ["powershell", "-NoProfile", "-Command"]

def clip_text():
    r = subprocess.run(PS + ["Get-Clipboard"], capture_output=True)
    return r.stdout.decode("utf-8", errors="replace").strip()

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

def trusted_click(ws, x, y):
    for typ in ("mousePressed", "mouseReleased"):
        cdp_send(ws, "Input.dispatchMouseEvent", {
            "type": typ, "x": x, "y": y, "button": "left",
            "buttons": 1 if typ == "mousePressed" else 0, "clickCount": 1,
        })
        time.sleep(0.1)

def main():
    prior_txt = clip_text()

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

    # surface link cards through the real search input
    ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, 'http');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""")
    time.sleep(0.5)

    info = ws.eval("""
(() => {
  const card = [...document.querySelectorAll('.card')].find(c => c.querySelector('.link-copy'));
  if (!card) return 'NOBTN';
  const btn = card.querySelector('.link-copy');
  const r = btn.getBoundingClientRect();
  return JSON.stringify({
    glyph: btn.textContent, url: card.querySelector('.link-url').textContent.trim(),
    x: r.x + r.width / 2, y: r.y + r.height / 2,
    cards: document.querySelectorAll('.card').length,
  });
})()
""")
    assert info != "NOBTN", "no link card with inline copy button rendered"
    d = json.loads(info)
    print("link card:", d["glyph"], "|", d["url"][:50], "| cards:", d["cards"])
    assert d["glyph"].strip() == "🔗"

    trusted_click(ws, d["x"], d["y"])
    time.sleep(0.8)
    got = clip_text()
    print("clipboard now:", got[:60])
    assert got == d["url"], f"clipboard {got!r} != url {d['url']!r}"

    # restore + clear search
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=prior_txt.encode("utf-8"), capture_output=True)
    ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, '');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""")
    print("R104 VERIFY PASS: inline 🔗 on link card, trusted click copies exact URL")

if __name__ == "__main__":
    main()
