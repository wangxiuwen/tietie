# -*- coding: utf-8 -*-
"""R140 / direction 134 verification: diagnostics export.

First ensure the log contains a redaction-marker line (fire notify_due with
a recognizable body), then click the real 导出诊断包 button and assert the
produced Documents/diagnostics-<ts>.txt:
  - header with version + os
  - [settings] / [counts] / [hotkeys] sections present
  - the notify body text does NOT appear; its log line shows [redacted]
  - opened url lines are redacted too
Cleanup deletes the export.
"""
import sys, time, json, os, glob, subprocess, urllib.request
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

    SECRET = "绝密诊断内容XYZ"
    ws.invoke("notify_due", {"title": "贴贴便签提醒", "body": SECRET})
    # seed an opened-url log line too (harmless unreachable target)
    ws.invoke("open_url", {"url": "http://127.0.0.1:9/diag"})
    time.sleep(1.5)

    ws.invoke("open_settings")
    time.sleep(1.2)
    with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
        targets = json.load(r)
    st = CDP(next(t["webSocketDebuggerUrl"] for t in targets if "view=settings" in t["url"]))
    clicked = st.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x => x.textContent === '导出诊断包');
  if (!b) return 'NOBTN';
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'CLICKED';
})()
""")
    assert clicked == "CLICKED", clicked
    time.sleep(1.2)

    files = sorted(glob.glob(os.path.expanduser("~/Documents/diagnostics-*.txt")),
                   key=os.path.getmtime)
    assert files, "no diagnostics file produced"
    path = files[-1]
    print("exported:", path)
    txt = open(path, encoding="utf-8").read()
    assert txt.startswith("贴贴诊断包"), txt[:30]
    assert "version: 0.1.31" in txt, "version missing"
    assert "os: windows" in txt, "os missing"
    for sec in ("[settings]", "[counts]", "[hotkeys]", "[log tail x200"):
        assert sec in txt, f"{sec} missing"
    assert SECRET not in txt, "secret body leaked!"
    assert "due notification fired: [redacted]" in txt, "redaction marker missing"
    assert "opened url: [redacted]" in txt, "url redaction missing"
    msg = st.eval("""
(() => [...document.querySelectorAll('.settings-tag.ok')].map(e => e.textContent).join('|'))()
""")
    print("ui msg:", msg[:60])
    assert "已导出" in msg, msg

    st.invoke("hide_window")
    os.remove(path)
    print("R140 VERIFY PASS: diagnostics bundle exported with redactions")

if __name__ == "__main__":
    main()
