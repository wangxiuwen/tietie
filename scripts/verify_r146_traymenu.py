# -*- coding: utf-8 -*-
"""R146 / direction 140 verification: tray row context menu.

  1. right-click the first row (real contextmenu path) → menu opens with
     复制并粘贴回去 / 置顶 / 删除 entries
  2. click 置顶 on a probe row → item becomes pinned (list refreshes,
     pinned section gains a chip) — then unpin via the menu again
  3. click 删除 on a throwaway item → row disappears from the panel
Clipboard restored; no production rows harmed (probe only).
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

PS = ["powershell", "-NoProfile", "-Command"]

def clip():
    r = subprocess.run(PS + ["Get-Clipboard"], capture_output=True)
    return r.stdout.decode("gbk", errors="replace").strip()

def main():
    prior = clip()
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

    # put a probe item on the clipboard (real capture path)
    MARK = "tray-menu-probe-" + str(int(time.time()))
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=MARK.encode("utf-8"), capture_output=True)
    time.sleep(2.5)
    ws.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'show-tray'}).catch(e=>String(e))")
    time.sleep(1.2)

    def row_for(mark):
        return ws.eval(f"""
(() => {{
  const rows = [...document.querySelectorAll('.po-row')];
  const r = rows.find(x => x.textContent.includes('{mark}'));
  return r ? JSON.stringify({{ found: true, text: r.textContent.slice(0, 40) }}) : JSON.stringify({{ found: false }});
}})()
""")

    # 1) context menu opens with the three entries
    opened = ws.eval(f"""
(() => new Promise(res => {{
  const row = [...document.querySelectorAll('.po-row')].find(x => x.textContent.includes('{MARK}'));
  if (!row) return res('NOROW');
  row.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true, cancelable: true, clientX: 200, clientY: 200 }}));
  requestAnimationFrame(() => {{
    const items = [...document.querySelectorAll('.ctx-menu .ctx-item, [class*=ctx] [class*=item], .menu-item, [class*=ctx] li')]
      .map(e => e.textContent).filter(Boolean);
    res(JSON.stringify(items));
  }});
}}))()
""")
    print("menu items:", opened)
    items = json.loads(opened) if opened.startswith("[") else []
    assert any("复制" in x for x in items), items
    assert any("置顶" in x for x in items), items
    assert any("删除" in x for x in items), items

    # 2) pin via the real menu click
    pinned = ws.eval(f"""
(() => {{
  const cands = [...document.querySelectorAll('button, [role=menuitem], li, .menu-item')]
    .filter(e => e.textContent === '置顶');
  if (!cands.length) return 'NOITEM';
  cands[0].dispatchEvent(new MouseEvent('click', {{ bubbles: true }}));
  return 'CLICKED';
}})()
""")
    assert pinned == "CLICKED", pinned
    time.sleep(1.2)
    state = ws.eval(f"""
(() => {{
  const chips = [...document.querySelectorAll('.po-row')].filter(x => x.textContent.includes('{MARK}'));
  return JSON.stringify({{ count: chips.length }});
}})()
""")
    print("after pin, rows containing mark:", state)
    # pinned section shows it once, recent hides it → exactly 1 visible
    assert json.loads(state)["count"] == 1, state

    # unpin again via menu (same row, now in pinned section)
    ws.eval(f"""
(() => {{
  const row = [...document.querySelectorAll('.po-row')].find(x => x.textContent.includes('{MARK}'));
  row.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true, cancelable: true, clientX: 200, clientY: 200 }}));
  return true;
}})()
""")
    time.sleep(0.4)
    unpinned = ws.eval("""
(() => {
  const cands = [...document.querySelectorAll('button, [role=menuitem], li, .menu-item')]
    .filter(e => e.textContent === '取消置顶');
  if (!cands.length) return 'NOITEM';
  cands[0].dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'CLICKED';
})()
""")
    assert unpinned == "CLICKED", unpinned
    time.sleep(1.2)

    # 3) delete via the menu
    ws.eval(f"""
(() => {{
  const row = [...document.querySelectorAll('.po-row')].find(x => x.textContent.includes('{MARK}'));
  row.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true, cancelable: true, clientX: 200, clientY: 200 }}));
  return true;
}})()
""")
    time.sleep(0.4)
    deleted = ws.eval("""
(() => {
  const cands = [...document.querySelectorAll('button, [role=menuitem], li, .menu-item')]
    .filter(e => e.textContent === '删除');
  if (!cands.length) return 'NOITEM';
  cands[0].dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'CLICKED';
})()
""")
    assert deleted == "CLICKED", deleted
    time.sleep(1.2)
    gone = json.loads(row_for(MARK))
    print("after delete:", gone)
    assert gone["found"] is False, "probe row still visible after delete"

    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=prior.encode("utf-8"), capture_output=True)
    print("R146 VERIFY PASS: menu opens; pin/unpin; delete removes the row")

if __name__ == "__main__":
    main()
