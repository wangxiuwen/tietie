# -*- coding: utf-8 -*-
"""tietie E2E smoke (direction 44): the CDP method used across iteration
rounds, frozen into one script.

Chains verified (command-level via window.__TAURI_INTERNALS__.invoke, plus
Win32 window ground truth and a read-only sqlite cross-check):
  1. open_drawer   -> drawer window visible (EnumWindows/IsWindowVisible)
  2. hang_items    -> memo appears in list_memos
  3. remove_memo   -> memo gone
  4. sqlite        -> clip_item count unchanged (net-zero), memo count restored

Safety: only round-trips an EXISTING clip item (hang then take off), so the
database ends exactly as it started. If the app is not running with CDP, a
temporary debug instance is launched and killed at the end — relaunch the
app normally afterwards.

Usage: py -3 scripts/e2e_smoke.py
"""
import base64
import ctypes
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request

CDP_PORT = 9223
EXE = os.path.join(os.environ["LOCALAPPDATA"], "Tietie", "tietie.exe")
DB = os.path.join(
    os.environ["LOCALAPPDATA"], "com.wangxiuwen.tietie", "tietie.sqlite"
)


# ---------------------------------------------------------------- CDP / WS
class WS:
    """Minimal RFC6455 client — enough for CDP text frames, stdlib only."""

    def __init__(self, host, port, path):
        self.sock = socket.create_connection((host, port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        assert b"101" in buf.split(b"\r\n", 1)[0], buf[:120]

    def send(self, text):
        data = text.encode()
        mask = os.urandom(4)
        head = bytearray([0x81])  # FIN + text
        n = len(data)
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        head += mask
        self.sock.sendall(bytes(head) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv_text(self):
        def rd(n):
            b = b""
            while len(b) < n:
                chunk = self.sock.recv(n - len(b))
                if not chunk:
                    raise ConnectionError("ws closed")
                b += chunk
            return b

        while True:
            b1, b2 = rd(2)
            op = b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                (n,) = struct.unpack(">H", rd(2))
            elif n == 127:
                (n,) = struct.unpack(">Q", rd(8))
            if b2 & 0x80:  # server frames are unmasked per spec
                rd(4)
            payload = rd(n)
            if op == 1:
                return payload.decode("utf-8", "replace")
            if op in (8, 9):  # close/ping: ignore (CDP does not ping us)
                continue


class CDP:
    def __init__(self, url):
        # http://127.0.0.1:PORT/json — take the ws url of a page target
        host, path = url.split("/devtools/page/")
        ws_host, ws_port = host.split("//")[1].split(":")
        self.ws = WS(ws_host, int(ws_port), "/devtools/page/" + path)
        self.seq = 0

    def eval(self, expr):
        """Evaluate an expression, await promises, return the JS value."""
        self.seq += 1
        rid = self.seq
        self.ws.send(json.dumps({
            "id": rid,
            "method": "Runtime.evaluate",
            "params": {"expression": expr, "awaitPromise": True,
                       "returnByValue": True},
        }))
        while True:
            msg = json.loads(self.ws.recv_text())
            if msg.get("id") != rid:
                continue  # events (clipboard-changed etc.)
            if "error" in msg:
                raise RuntimeError(msg["error"])
            res = msg["result"]
            if res.get("exceptionDetails"):
                raise RuntimeError(res["exceptionDetails"]["text"])
            return res["result"].get("value")

    def invoke(self, cmd, args=None):
        """Call a Tauri command on the page's backend bridge."""
        payload = json.dumps(args or {})
        out = self.eval(
            f"window.__TAURI_INTERNALS__.invoke('{cmd}', {payload})"
            ".then(r => JSON.stringify(r)).catch(e => 'ERR:' + e)"
        )
        assert not str(out).startswith("ERR:"), f"{cmd} failed: {out}"
        return json.loads(out) if out else None


def cdp_targets():
    with urllib.request.urlopen(
        f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=5
    ) as r:
        return json.load(r)


def drawer_page_ws():
    for t in cdp_targets():
        if t["url"] == "http://tauri.localhost/":  # drawer is the bare origin
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("drawer target not found")


# ---------------------------------------------------------------- Win32
def drawer_visible(pid):
    """True when a visible top-level window titled 贴贴 belongs to pid."""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )
    def on_hwnd(hwnd, _):
        wpid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value != pid:
            return True
        buf = ctypes.create_unicode_buffer(64)
        user32.GetWindowTextW(hwnd, buf, 64)
        if buf.value == "贴贴":  # drawer; others carry suffixes
            found.append(bool(user32.IsWindowVisible(hwnd)))
        return True

    user32.EnumWindows(on_hwnd, 0)
    return any(found) if found else False


def app_pid_with_cdp():
    """pid of the tietie instance answering on the CDP port, else None."""
    try:
        targets = cdp_targets()
    except Exception:
        return None
    # the process owning the port is found via netstat (WebView2 child of exe)
    out = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"], capture_output=True
    ).stdout.decode("utf-8", "replace")  # zh-CN netstat is GBK; we only need ASCII parts
    for line in out.splitlines():
        if f"127.0.0.1:{CDP_PORT}" in line and "LISTENING" in line:
            pid = int(line.split()[-1])
            # walk up: the WebView2 process's parent chain contains tietie.exe
            return (pid, targets)
    return None


def sqlite_ro(sql, args=()):
    import sqlite3

    conn = sqlite3.connect("file:" + DB.replace("\\", "/") + "?mode=ro", uri=True)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------- main
def main():
    launched = False
    info = app_pid_with_cdp()
    if info is None:
        print("no CDP instance; launching debug instance …")
        env = dict(
            os.environ,
            WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=f"--remote-debugging-port={CDP_PORT}",
        )
        subprocess.Popen([EXE], env=env)
        launched = True
        for _ in range(40):
            time.sleep(0.5)
            info = app_pid_with_cdp()
            if info:
                break
    assert info, "debug instance did not come up"

    # single-instance plugin guarantees exactly one tietie.exe
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-Process tietie -ErrorAction SilentlyContinue).Id"],
        capture_output=True, text=True,
    ).stdout.split()
    assert len(out) == 1, f"expected exactly one tietie.exe, got {out}"
    app_pid = int(out[0])
    print(f"app pid={app_pid}, cdp targets live")

    cdp = CDP(drawer_page_ws())
    results = []

    def step(name, ok, detail=""):
        results.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")

    # pick an existing text item (round-trip target — no new data seeded)
    items = cdp.invoke("list_items", {"limit": 50})
    cand = next((i for i in items if i.get("kind") == "text"), None)
    assert cand, "no text item to round-trip"
    item_id = cand["id"]
    clip0, memo0 = sqlite_ro("SELECT COUNT(*) FROM clip_item")[0][0], \
        sqlite_ro("SELECT COUNT(*) FROM memo")[0][0]

    # 1. open drawer -> Win32 visible (IPC command is show_drawer; it calls
    # the unconditional open path internally)
    cdp.invoke("show_drawer")
    time.sleep(0.4)
    step("open drawer -> drawer visible", drawer_visible(app_pid))

    # 2. hang the item -> memo appears
    hung = cdp.invoke("hang_items", {"ids": [item_id]})
    memos = cdp.invoke("list_memos")
    memo = next((m for m in memos if m.get("sourceItemId") == item_id or
                 m.get("source_item_id") == item_id), None)
    step("hang_items -> memo listed", hung == 1 and memo is not None,
         f"(item {item_id}, memo {memo and memo.get('id')})")

    # 3. take it off -> memo gone, counts restored
    cdp.invoke("remove_memo", {"id": memo["id"]})
    memos = cdp.invoke("list_memos")
    gone = not any(m.get("sourceItemId") == item_id or
                   m.get("source_item_id") == item_id for m in memos)
    clip1, memo1 = sqlite_ro("SELECT COUNT(*) FROM clip_item")[0][0], \
        sqlite_ro("SELECT COUNT(*) FROM memo")[0][0]
    step("remove_memo -> memo gone", gone and memo1 == memo0)

    # 4. net-zero db proof
    step("db net-zero", clip0 == clip1,
         f"(clip {clip0}->{clip1}, memo {memo0}->{memo1})")

    if launched:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process tietie -ErrorAction SilentlyContinue | Stop-Process -Force"]
        )
        print("debug instance killed — relaunch the app for normal use")

    ok = all(results)
    print("SMOKE:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
