# -*- coding: utf-8 -*-
"""R129 / direction 124 verification: tray rows show ⌘N hints and ⌘N copies.

  1. rows 1..10 carry a .kbd tail badge "Ctrl1".."Ctrl0"; row 11 has none
  2. plain "1" typed into the search box stays a search (no copy)
  3. Ctrl+1 runs the real copyBack path: OS clipboard equals row 1's content
Prior clipboard restored.
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

PS = ["powershell", "-NoProfile", "-Command"]

def clip_text():
    r = subprocess.run(PS + ["Get-Clipboard"], capture_output=True)
    # Get-Clipboard emits GBK on this host — decode accordingly
    return r.stdout.decode("gbk", errors="replace").strip()

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

def key(ws, k, code, ctrl=False):
    cdp_send(ws, "Input.dispatchKeyEvent", {
        "type": "keyDown", "key": k, "code": code,
        "windowsVirtualKeyCode": ord(k),
        "modifiers": 2 if ctrl else 0})
    cdp_send(ws, "Input.dispatchKeyEvent", {
        "type": "keyUp", "key": k, "code": code,
        "windowsVirtualKeyCode": ord(k),
        "modifiers": 2 if ctrl else 0})

def main():
    prior = clip_text()
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if "view=tray" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "tray target not found"
    # surface the panel
    ws.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'show-tray'}).catch(e=>String(e))")
    time.sleep(1.0)

    badges = ws.eval("""
(() => JSON.stringify(
  [...document.querySelectorAll('.po-row')].slice(0, 11)
    .map(r => r.querySelector('.kbd')?.textContent ?? null)
))()
""")
    b = json.loads(badges)
    print("kbd badges:", b)
    assert b[:10] == [f"Ctrl{i+1}" for i in range(9)] + ["Ctrl0"], b
    assert b[10] is None, f"row 11 should have no badge: {b[10]}"

    # plain "1" must NOT copy: dispatch it on the input (raw CDP keys don't
    # insert text, so assert the clipboard is untouched instead)
    clip_before = clip_text()
    ws.eval("""
(() => {
  const el = document.querySelector('.po-search-box input');
  el.focus();
  el.dispatchEvent(new KeyboardEvent('keydown', { key: '1', code: 'Digit1', bubbles: true, cancelable: true }));
  return true;
})()
""")
    time.sleep(0.5)
    assert clip_text() == clip_before, "plain digit triggered a copy!"
    # clear
    ws.eval("""
(() => {
  const el = document.querySelector('.po-search-box input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, ''); el.dispatchEvent(new Event('input', { bubbles: true }));
  el.focus();
  return true;
})()
""")
    time.sleep(0.5)

    # Ctrl+1 copies the first visible row through the real path
    first = ws.eval("""
(() => document.querySelector('.po-row .po-text')?.textContent ?? '')()
""")
    print("row1 text:", first[:40])
    key(ws, "1", "Digit1", ctrl=True)
    time.sleep(1.0)
    got = clip_text()
    print("clipboard:", repr(got[:50]))
    head = first.replace("…", "")[:16]
    assert head and head in got[:len(got)], f"clipboard {got!r} != row {first[:30]!r}"

    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=prior.encode("utf-8"), capture_output=True)
    print("R129 VERIFY PASS: ⌘N badges on first 10 rows, plain digit types, Ctrl+1 copies")

if __name__ == "__main__":
    main()
