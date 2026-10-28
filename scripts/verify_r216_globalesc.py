# 方向216 真机验证：托盘面板 Esc 全局隐藏（焦点任意处）
# 剧本（零副作用）：
#   显示面板 → blur 搜索框（body 焦点）→ 可信 Esc → isVisible=false（新行为）
#   → 重新 show → 可信右键首行弹 .ctx-menu → 可信 Esc → 菜单关且面板仍可见（分层守卫）
#   → 再 Esc → 面板隐藏（收尾即常态休眠位）
import ctypes
import json
import subprocess
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


tray = CDP(page_ws(lambda u: "view=tray" in u))


def app_pid():
    """tietie.exe main pid — the netstat CDP listener's parent chain lands on
    a WebView2 child, not the app, so ask the process list directly."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process tietie -ErrorAction SilentlyContinue).Id | ConvertTo-Json"],
        capture_output=True).stdout.decode("utf-8", "replace")
    raw = json.loads(out)
    pids = [int(x) for x in (raw if isinstance(raw, list) else [raw])]
    assert len(pids) == 1, f"expected one tietie.exe, got {pids}"
    return pids[0]


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


def tray_visible(pid):
    """True when the small 贴贴 window (the tray panel, <800px wide — the
    drawer is the full-width one and rests hidden) is visible."""
    user32 = ctypes.windll.user32
    vis = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def on_hwnd(hwnd, _):
        wpid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value != pid:
            return True
        buf = ctypes.create_unicode_buffer(64)
        user32.GetWindowTextW(hwnd, buf, 64)
        if buf.value == "贴贴":
            rc = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rc))
            if rc.r - rc.l < 800:  # panel-sized, not the 1920px drawer
                vis.append(bool(user32.IsWindowVisible(hwnd)))
        return True

    user32.EnumWindows(on_hwnd, 0)
    return vis[0] if vis else False


def raw(method, params):
    tray.seq += 1
    rid = tray.seq
    tray.ws.send(json.dumps({"id": rid, "method": method, "params": params}))
    while True:
        msg = json.loads(tray.ws.recv_text())
        if msg.get("id") == rid:
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return msg.get("result", {})


def esc():
    raw("Input.dispatchKeyEvent",
        {"type": "rawKeyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    raw("Input.dispatchKeyEvent",
        {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})


def visible():
    # plugin isVisible isn't in capabilities; infer via win32 — the drawer
    # window is always visible, so 2 visible 贴贴 windows means tray is up.
    return tray_visible(PID)


def show():
    # bare show keeps the panel alive (R212 precedent): no focus event fires,
    # so the hide-on-focus-loss handler stays quiet. set_focus from a
    # background process gets denied foreground and trips the handler.
    tray.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')


PID = app_pid()

# ── Case 1: body 焦点 Esc 隐藏（新行为）──
show()
time.sleep(0.8)
assert visible(), "前置：面板应可见"
tray.eval("(() => { document.activeElement && document.activeElement.blur(); return true; })()")
time.sleep(0.2)
esc()
time.sleep(0.6)
v = visible()
print("after body-Esc visible:", v)
assert not v, "body 焦点 Esc 未隐藏面板"

# ── Case 2: 右键菜单打开时 Esc 只关菜单不关面板（分层守卫）──
show()
time.sleep(0.8)
r = tray.eval(r"""(() => {
    const row = document.querySelector('.po-list .po-row, .po-row');
    if (!row) return 'NOROW';
    const b = row.getBoundingClientRect();
    return JSON.stringify({x: b.left + b.width / 2, y: b.top + b.height / 2});
})()""")
assert r != "NOROW", "托盘无行"
pos = json.loads(r)
raw("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pos["x"], "y": pos["y"],
                                 "button": "right", "buttons": 2, "clickCount": 1})
raw("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pos["x"], "y": pos["y"],
                                 "button": "right", "buttons": 0, "clickCount": 1})
time.sleep(0.5)
menu = tray.eval(r"""(() => !!document.querySelector('.ctx-menu'))()""")
print("ctx menu open:", menu)
assert menu, "右键未弹出菜单"
esc()
time.sleep(0.5)
menu_gone = tray.eval(r"""(() => !document.querySelector('.ctx-menu'))()""")
still = visible()
print("after menu-Esc: menu gone =", menu_gone, "| panel visible =", still)
assert menu_gone, "Esc 未关闭菜单"
assert still, "菜单打开时 Esc 不应隐藏面板（分层守卫失效）"

# ── Case 3: 菜单关掉后再 Esc 才隐藏 ──
esc()
time.sleep(0.6)
v = visible()
print("after final-Esc visible:", v)
assert not v, "菜单关闭后 Esc 应隐藏面板"

print("PASS: body 焦点 Esc 隐藏面板 / 菜单层 Esc 只剥一层 / 再 Esc 才隐藏")
