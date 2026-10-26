# -*- coding: utf-8 -*-
"""R116 / direction 110 verification: tray popover dark-mode adaptation.

Uses CDP Emulation.setEmulatedMedia to flip the tray page between light and
dark prefers-color-scheme and reads computed styles of the affected parts:
  - dark: search input bg = white tint, foot bg = white tint, row hover =
    white tint, kind-color text = bright amber
  - light: original black-tint values
"""
import sys, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def set_scheme(ws, scheme):
    ws.seq += 1
    rid = ws.seq
    ws.ws.send(json.dumps({"id": rid, "method": "Emulation.setEmulatedMedia",
                           "params": {"features": [
                               {"name": "prefers-color-scheme", "value": scheme}]}}))
    while True:
        msg = json.loads(ws.ws.recv_text())
        if msg.get("id") != rid:
            continue
        if "error" in msg:
            raise RuntimeError(msg["error"])
        return

def probe(ws):
    return json.loads(ws.eval("""
(() => {
  const inp = document.querySelector('.po-search input');
  const foot = document.querySelector('.po-foot');
  const row = document.querySelector('.po-row');
  const kc = document.querySelector('.kind-color') || document.querySelector('.po-kind');
  const r = {
    inputBg: inp ? getComputedStyle(inp).backgroundColor : null,
    footBg: foot ? getComputedStyle(foot).backgroundColor : null,
    rowHover: row ? getComputedStyle(row).backgroundColor : null,
    kindColor: kc ? getComputedStyle(kc).color : null,
    rootText: getComputedStyle(document.documentElement).getPropertyValue('--text').trim(),
  };
  if (row) {
    row.dispatchEvent(new MouseEvent('mouseenter', { bubbles: false }));
    r.rowHover = getComputedStyle(row).backgroundColor;
  }
  return JSON.stringify(r);
})()
"""))

def main():
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

    set_scheme(ws, "dark")
    time.sleep(0.3)
    d = probe(ws)
    print("dark:", d)
    assert d["inputBg"] == "rgba(255, 255, 255, 0.07)", f"input bg dark: {d['inputBg']}"
    assert d["footBg"] == "rgba(255, 255, 255, 0.03)", f"foot bg dark: {d['footBg']}"
    assert d["kindColor"] == "rgb(255, 214, 10)", f"kind-color dark: {d['kindColor']}"
    assert "255, 255, 255" in d["rootText"], f"root vars did not flip dark: {d['rootText']}"

    set_scheme(ws, "light")
    time.sleep(0.3)
    l = probe(ws)
    print("light:", l)
    assert l["inputBg"] == "rgba(0, 0, 0, 0.05)", f"input bg light: {l['inputBg']}"
    assert l["footBg"] == "rgba(0, 0, 0, 0.02)", f"foot bg light: {l['footBg']}"
    assert "0, 0, 0" in l["rootText"] or l["rootText"] != d["rootText"], "root vars did not flip back"

    print("R116 VERIFY PASS: tray popover adapts to prefers-color-scheme both ways")

if __name__ == "__main__":
    main()
