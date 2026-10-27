# -*- coding: utf-8 -*-
"""R156 / direction 150 verification: memo right-click "copy plain".

Hangs a memo carrying all three Markdown syntaxes, right-clicks it, clicks
「复制（去格式）」 through the real menu path, then reads the OS clipboard
(trusted input not required — clipboard.writeText from a synthetic click is
granted only with user activation... this click is synthetic, so we ALSO
verify via the plain 复制 fallback? No: navigator.clipboard needs activation.
Workaround per R102: CDP trusted Input click on the menu item.)
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

PS = ["powershell", "-NoProfile", "-Command"]

def clip():
    r = subprocess.run(PS + ["Get-Clipboard"], capture_output=True)
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

def main():
    prior = clip()
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if "view=line" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "clothesline target not found"

    # capture + grow the strip so the menu fits on-screen (the clothesline
    # is a short window; its context menu otherwise clips above y=0)
    orig = json.loads(ws.eval(
      "JSON.stringify({w: window.innerWidth, h: window.innerHeight})"))
    r0 = ws.eval(
      "window.__TAURI_INTERNALS__.invoke('plugin:window|set_size', "
      "{ value: { Logical: { width: " + str(max(orig["w"], 1400)) + ", height: 620 } } })"
      ".then(() => 'OK').catch(e => 'ERR:' + e)")
    assert r0 == "OK", r0
    time.sleep(0.6)

    for m in ws.invoke("list_memos"):
        if "粗" in m["content"] or m["content"].startswith("去格式"):
            ws.invoke("remove_memo", {"id": m["id"]})
    time.sleep(0.3)

    mid = ws.invoke("add_memo_direct",
                    {"content": "前缀**加粗**中段 `代码片段` 尾部 [标签](https://example.com/x) 结束",
                     "remindAt": None, "color": None})
    assert isinstance(mid, int)
    time.sleep(0.6)

    ws.eval("""
(() => {
  const card = document.querySelector('.line-card[data-memo="__MID__"]');
  const r = card.getBoundingClientRect();
  card.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true,
    clientX: 220, clientY: r.y + r.height - 6 }));
  return true;
})()
""".replace("__MID__", str(mid)))
    time.sleep(0.4)
    info = ws.eval("""
(() => {
  const cands = [...document.querySelectorAll('button, [role=menuitem], li, .menu-item')]
    .filter(e => e.textContent.trim() === '复制（去格式）');
  if (!cands.length) return 'NOITEM';
  const r = cands[0].getBoundingClientRect();
  return JSON.stringify({ x: r.x + r.width / 2, y: r.y + r.height / 2 });
})()
""")
    assert info != "NOITEM", "menu item missing"
    d = json.loads(info)
    for typ in ("mousePressed", "mouseReleased"):
        cdp_send(ws, "Input.dispatchMouseEvent", {
            "type": typ, "x": d["x"], "y": d["y"], "button": "left",
            "buttons": 1 if typ == "mousePressed" else 0, "clickCount": 1})
        time.sleep(0.12)
    time.sleep(1.2)

    got = clip()
    print("clipboard:", got)
    assert got == "前缀加粗中段 代码片段 尾部 https://example.com/x 结束", repr(got)

    # restore strip + clipboard, drop the probe
    ws.eval(
      "window.__TAURI_INTERNALS__.invoke('plugin:window|set_size', "
      f"{{ value: {{ Logical: {{ width: {orig['w']}, height: {orig['h']} }} }} }})"
      ".catch(e => String(e))")
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=prior.encode("utf-8"), capture_output=True)
    ws.invoke("remove_memo", {"id": mid})
    print("R156 VERIFY PASS: markers stripped, URL survives verbatim")

