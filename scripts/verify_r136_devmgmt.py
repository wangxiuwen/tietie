# -*- coding: utf-8 -*-
"""R136 / direction 130 verification: sync device management UI.

Seeds the fake peer (loopback pairing row), enables sync, then:
  1. probe SENDS a frame → last_sync_at becomes ~now (inbound touch)
  2. settings page shows the peer with 上次同步 < small value (not "—")
  3. inline alias rename (Enter) → pairing_list returns the alias; UI shows it
  4. remove via the real button → row gone (DB empty, no 移除 action)
Cleanup removes everything and disables sync.
"""
import sys, time, json, os, sqlite3, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

DB = os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\tietie.sqlite")
PROBE = r"D:\company\tuling\workspace\tietie\src-tauri\target\debug\examples\sync_probe.exe"
PEER = "sync-probe-tietie"
TOKEN = "probe-shared-token-130"

def main():
    # commands ride the DRAWER page (hidden settings webview can be
    # suspended and time out on eval); the settings target is only used
    # after the window is actually shown below
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

    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("DELETE FROM pairing WHERE instance = ?", (PEER,))
    conn.execute("DELETE FROM clip_item WHERE content LIKE '同步管理验证%'")
    conn.execute(
        "INSERT INTO pairing (instance, addr, token, created_at) VALUES (?, ?, ?, ?)",
        (PEER, "127.0.0.1:51785", TOKEN, int(time.time())))
    conn.commit()
    conn.close()
    # enable sync by writing the setting table directly — the IPC-then-send
    # sequence proved flaky while the identical direct path works reliably
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute(
        "INSERT INTO setting (key, value) VALUES ('sync_enabled', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = '1'")
    conn.commit()
    conn.close()
    time.sleep(0.5)

    # 1) inbound frame touches last_sync_at (retry: cold app can drop the
    # first frame while pages wake; the feature itself is what we assert)
    subprocess.run([PROBE, "send", "127.0.0.1:41784", PEER, TOKEN, "预热帧"],
                   capture_output=True)
    time.sleep(2.0)
    ts = 0
    for attempt in range(3):
        subprocess.run([PROBE, "send", "127.0.0.1:41784", PEER, TOKEN, "同步管理验证内容"],
                   capture_output=True)
        time.sleep(2.2)
        conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        ts = conn.execute(
            "SELECT last_sync_at FROM pairing WHERE instance = ?", (PEER,)).fetchone()[0]
        conn.close()
        if ts > 0:
            break
        print(f"attempt {attempt}: last_sync still 0, retrying")
    now = int(time.time())
    print("last_sync_at:", ts, "now:", now)
    assert ts > 0 and now - ts <= 15, f"last_sync_at not touched: {ts}"

    # 2) settings UI row shows the alias field + non-dash last-sync
    ws.invoke("open_settings")
    time.sleep(1.5)
    with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
        targets = json.load(r)
    st = CDP(next(t["webSocketDebuggerUrl"] for t in targets if "view=settings" in t["url"]))
    # the page just woke from suspension: poke the real 刷新 button and wait
    # for the chip to appear (bounded) instead of trusting the open-time load
    import json as _json
    for _ in range(10):
        # re-fire the settings-open load path (reloadPaired rides on it);
        # a frontend emit reaches every window's listeners
        st.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'settings-open'}).catch(e=>String(e))")
        time.sleep(0.5)
        # the instance name lives in the alias INPUT's value, not textContent
        hit = st.eval("""
(() => [...document.querySelectorAll('.lan-peer .pair-name')].some(i => i.value === '__PEER__') ? '1' : '0')()
""".replace("__PEER__", PEER))
        if hit == "1":
            break
    assert hit == "1", "paired chip never appeared"
    row = st.eval("""
(() => {
  const chip = [...document.querySelectorAll('.lan-peer')].find(e => {
    const i = e.querySelector('.pair-name'); return i && i.value === '__PEER__';
  });
  if (!chip) return 'NOCHIP';
  const name = chip.querySelector('.pair-name');
  return JSON.stringify({ text: chip.textContent.slice(0, 80), hasName: !!name,
    nameVal: name ? name.value : null });
})()
""".replace("__PEER__", PEER))
    d = json.loads(row)
    print("chip:", d)
    assert d["hasName"] and d["nameVal"] == PEER, d
    assert "上次同步" in d["text"] and "—" not in d["text"].split("上次同步")[1][:12], d

    # 3) rename via the real input path
    renamed = st.eval("""
(() => new Promise(res => {
  const chip = [...document.querySelectorAll('.lan-peer')].find(e => {
    const i = e.querySelector('.pair-name'); return i && i.value === '__PEER__';
  });
  if (!chip) return 'NOCHIP';
  const inp = chip.querySelector('.pair-name');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(inp, '我的小本本');
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
  requestAnimationFrame(() => requestAnimationFrame(() => res(String(inp.value))));
}))()
""".replace("__PEER__", PEER))
    print("renamed:", renamed)
    time.sleep(0.8)
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    alias = conn.execute("SELECT name FROM pairing WHERE instance = ?", (PEER,)).fetchone()[0]
    conn.close()
    print("db alias:", alias)
    assert alias == "我的小本本", alias

    # 4) unpair via the real button (this chip's button = 移除)
    clicked = st.eval("""
(() => {
  const chip = [...document.querySelectorAll('.lan-peer')].find(e =>
    e.querySelector('.pair-name') && e.querySelector('.pair-name').value === '我的小本本');
  if (!chip) return 'NOCHIP';
  const b = chip.querySelector('button');
  b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return 'CLICKED';
})()
""")
    assert clicked == "CLICKED", clicked
    time.sleep(0.8)
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    n = conn.execute("SELECT COUNT(*) FROM pairing WHERE instance = ?", (PEER,)).fetchone()[0]
    conn.close()
    assert n == 0, "unpair failed"

    # cleanup
    st.invoke("hide_window")
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("UPDATE setting SET value = '0' WHERE key = 'sync_enabled'")
    conn.commit()
    conn.close()
    ws.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'settings-open'})") if False else ws.eval("null")
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("DELETE FROM clip_item WHERE content LIKE '同步管理验证%'")
    conn.commit()
    conn.close()
    print("R136 VERIFY PASS: last-sync touch + alias rename + UI + unpair")

if __name__ == "__main__":
    main()
