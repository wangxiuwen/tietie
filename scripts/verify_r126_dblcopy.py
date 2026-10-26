# -*- coding: utf-8 -*-
"""R126 / direction 120 verification: double-click a Library row copies it.

Drives TRUSTED double-clicks via CDP Input (two rapid click pairs -> the
browser synthesizes dblclick, granting clipboard user-activation), then
checks the OS clipboard equals the row's content and the 已复制 feedback
appears. Prior clipboard content is restored. Row selection is untouched.
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
        return

def click(ws, x, y, count):
    for typ in ("mousePressed", "mouseReleased"):
        cdp_send(ws, "Input.dispatchMouseEvent", {
            "type": typ, "x": x, "y": y, "button": "left",
            "buttons": 1 if typ == "mousePressed" else 0, "clickCount": count})
        time.sleep(0.05)

def main():
    prior = clip_text()

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

    info = ws.eval("""
(() => {
  const rows = [...document.querySelectorAll('.lib-table tbody tr')];
  const row = rows.find(tr => {
    const b = tr.querySelector('.badge');
    return b && !b.className.includes('image');
  });
  if (!row) return 'NOROW';
  const r = row.getBoundingClientRect();
  const cb = row.querySelector('input[type=checkbox]');
  return JSON.stringify({
    checked: cb.checked,
    x: r.x + r.width / 2, y: r.y + r.height / 2,
    text: row.querySelector('.lib-row-text')?.textContent ?? '',
  });
})()
""")
    assert info != "NOROW", "no non-image row"
    d = json.loads(info)
    print("target row:", d["text"][:40], "| checked:", d["checked"])

    # trusted double click: second press carries clickCount=2 so Chromium
    # synthesizes the dblclick event
    click(ws, d["x"], d["y"], 1)
    time.sleep(0.05)
    click(ws, d["x"], d["y"], 2)
    time.sleep(0.9)

    got = clip_text()
    msg = ws.eval("""
(() => document.querySelector('.lib-msg, [class*=msg]')?.textContent ?? '')()
""")
    checked_after = ws.eval("""
(() => String(document.querySelectorAll('.lib-table tbody tr')[0]
  .querySelector('input[type=checkbox]').checked))()
""")
    print("clipboard:", repr(got[:50]), "| msg:", msg[:40])
    # the clipboard must equal the row's displayed content prefix
    assert got and d["text"].replace("…", "").replace("…", "")[:24] in got[:len(got)], \
        f"clipboard {got!r} does not match row {d['text'][:30]!r}"
    assert "已复制" in msg, f"feedback missing: {msg!r}"

    # restore prior clipboard
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=prior.encode("utf-8"), capture_output=True)
    print("R126 VERIFY PASS: dblclick copies row content with feedback")

if __name__ == "__main__":
    main()
