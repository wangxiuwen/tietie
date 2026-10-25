# -*- coding: utf-8 -*-
"""R102 / direction 96 verification: click version number -> copy.

Synthetic DOM clicks carry isTrusted=false and do NOT grant the user
activation navigator.clipboard needs — so this drives a TRUSTED click via the
CDP Input domain (mousePressed+mouseReleased at the button's real position)
after showing the settings window, then checks the OS clipboard via
PowerShell. The user's prior clipboard content is restored afterwards.
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
    prior_img = subprocess.run(
        PS + ["(Get-Clipboard -Format Image) -ne $null"], capture_output=True
    ).stdout.decode(errors="replace").strip()
    prior_txt = clip_text()
    print("prior clipboard:", repr(prior_txt[:30]), "image:", prior_img)

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

    ws.invoke("open_settings")
    time.sleep(0.8)

    ver = ws.eval("document.querySelector('.ver-copy')?.textContent ?? 'NOBTN'")
    assert ver and ver not in ("NOBTN", "...", ""), f"version button: {ver!r}"
    ver_clean = ver.replace(" ✓", "").strip()
    print("version shown:", ver_clean)

    rect = json.loads(ws.eval(
      "JSON.stringify(document.querySelector('.ver-copy').getBoundingClientRect())"))
    x, y = rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2
    trusted_click(ws, x, y)
    time.sleep(0.8)

    after = ws.eval("document.querySelector('.ver-copy')?.textContent ?? '?'")
    print("after click:", after)
    assert after.endswith("✓"), f"no copy feedback: {after!r}"

    got = clip_text()
    print("clipboard now:", got)
    assert got == ver_clean, f"clipboard mismatch: {got!r} != {ver_clean!r}"

    # restore prior clipboard and hide the settings window again
    if prior_img == "True":
        subprocess.run(PS + ["Get-Clipboard -Format Image | Set-Clipboard"], capture_output=True)
    else:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
            input=prior_txt.encode("utf-8"), capture_output=True)
    ws.invoke("hide_window")
    print("R102 VERIFY PASS: trusted click copies exact version, ✓ feedback shown")

if __name__ == "__main__":
    main()
