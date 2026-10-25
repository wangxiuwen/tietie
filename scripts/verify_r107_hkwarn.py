# -*- coding: utf-8 -*-
"""R107 / direction 101 verification: hotkey conflict warning.

Opens Settings, enters hotkey recording on the drawer row (trusted click),
then feeds the capture input two combos via keydown events:
  - Alt+F4            -> expect the SYSTEM-conflict warning tag
  - another row's live combo -> expect the DUPLICATE warning tag
Escape cancels both times; no hotkey is actually saved.
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
        return msg.get("result", {})

def trusted_click(ws, x, y):
    for typ in ("mousePressed", "mouseReleased"):
        cdp_send(ws, "Input.dispatchMouseEvent", {
            "type": typ, "x": x, "y": y, "button": "left",
            "buttons": 1 if typ == "mousePressed" else 0, "clickCount": 1,
        })
        time.sleep(0.1)

def send_combo(ws, mods, code):
    ws.eval("""
(() => {
  const el = document.querySelector('.hotkey-capture');
  el.dispatchEvent(new KeyboardEvent('keydown', {
    key: %s, code: %s, bubbles: true, cancelable: true,
    altKey: %s, ctrlKey: %s, metaKey: %s, shiftKey: %s,
  }));
  return true;
})()
""" % (json.dumps(code[-1] if code.startswith("Key") else code),
       json.dumps(code),
       "true" if "Alt" in mods else "false",
       "true" if "Control" in mods else "false",
       "true" if "Meta" in mods else "false",
       "false"))

def warn_text(ws):
    return ws.eval("""
(() => document.querySelector('.settings-tag.warn')?.textContent ?? 'NONE')()
""")

def esc(ws):
    ws.eval("""
(() => new Promise(res => {
  const el = document.querySelector('.hotkey-capture');
  if (!el) return res('GONE');
  el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
  requestAnimationFrame(() => requestAnimationFrame(() => res('SENT')));
}))()
""")
    time.sleep(0.6)

def main():
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

    hks = ws.invoke("get_hotkeys")
    print("hotkeys:", {k: v for k, v in hks.items() if isinstance(v, str) and v})
    dup_combo = hks.get("screenshot") or hks.get("clothesline")
    assert dup_combo, "no other hotkey set"

    def start_recording():
        rect = json.loads(ws.eval("""
(() => {
  const rows = [...document.querySelectorAll('.settings-row')];
  const row = rows.find(r => r.querySelector('.hotkey-badge'));
  const btn = row.querySelector('button.btn.ghost');
  const r = btn.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width/2, y: r.y + r.height/2});
})()
"""))
        trusted_click(ws, rect["x"], rect["y"])
        time.sleep(0.5)
        assert ws.eval("String(document.querySelector('.hotkey-capture') != null)") == "true", "recording not started"

    # 1) system conflict: Alt+F4
    start_recording()
    send_combo(ws, ["Alt"], "F4")
    time.sleep(0.3)
    w1 = warn_text(ws)
    print("Alt+F4 warn:", w1)
    assert "系统" in w1, f"expected system warning, got {w1!r}"
    esc(ws)

    # 2) duplicate of another tietie hotkey
    start_recording()
    parts = dup_combo.split("+")
    mods = parts[:-1]
    code = parts[-1]
    send_combo(ws, mods, code)
    time.sleep(0.3)
    w2 = warn_text(ws)
    print(f"{dup_combo} warn:", w2)
    assert "重复" in w2, f"expected dup warning, got {w2!r}"
    esc(ws); time.sleep(0.3)

    # no recording left, hotkeys unchanged
    assert ws.eval("String(document.querySelector('.hotkey-capture') == null)") == "true"
    after = ws.invoke("get_hotkeys")
    assert after.get("drawer") == hks.get("drawer"), "drawer hotkey changed!"
    ws.invoke("hide_window")
    print("R107 VERIFY PASS: system + duplicate conflict warnings shown, nothing saved")

if __name__ == "__main__":
    main()
