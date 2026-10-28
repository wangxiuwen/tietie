# 方向214 真机验证：Library 键盘 Home/End 跳首行/末行
# 剧本（零副作用：只移键盘光标行，不删不复制）：
#   Library 表格视图 blur 输入框 → 可信 Home → .kcursor 落第 1 行
#   → 可信 End → .kcursor 落最后一行且该行滚入可视区（scrollIntoView 生效）
import json
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


lib = CDP(page_ws(lambda u: "view=library" in u))


def raw(page, method, params):
    page.seq += 1
    rid = page.seq
    page.ws.send(json.dumps({"id": rid, "method": method, "params": params}))
    while True:
        msg = json.loads(page.ws.recv_text())
        if msg.get("id") == rid:
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return msg.get("result", {})


def key(k, vk):
    raw(lib, "Input.dispatchKeyEvent",
        {"type": "rawKeyDown", "key": k, "code": k, "windowsVirtualKeyCode": vk})
    raw(lib, "Input.dispatchKeyEvent",
        {"type": "keyUp", "key": k, "code": k, "windowsVirtualKeyCode": vk})


# 前置：表格视图、行数、焦点离开输入框
info = lib.eval(r"""(() => {
    document.activeElement && document.activeElement.blur();
    const rows = [...document.querySelectorAll('.lib-table tbody tr')];
    return rows.length;
})()""")
print("table rows:", info)
assert info and info >= 2, "Library 非表格视图或行数不足"


def cursor_state():
    return lib.eval(r"""(() => {
        const rows = [...document.querySelectorAll('.lib-table tbody tr')];
        const idx = rows.findIndex(r => r.classList.contains('kcursor'));
        const last = rows[rows.length - 1];
        const rect = last.getBoundingClientRect();
        const visible = rect.bottom > 0 && rect.top < window.innerHeight;
        return JSON.stringify({n: rows.length, idx: idx, lastVisible: visible});
    })()""")


# Home → 首行
key("Home", 36)
time.sleep(0.4)
st = json.loads(cursor_state())
print("after Home:", st)
assert st["idx"] == 0, f"Home 后光标不在首行: {st}"

# End → 末行 + 滚入视口
key("End", 35)
time.sleep(0.6)
st = json.loads(cursor_state())
print("after End:", st)
assert st["idx"] == st["n"] - 1, f"End 后光标不在末行: {st}"
assert st["lastVisible"], "末行未滚入可视区"

# 再 Home 回首行确认往返
key("Home", 36)
time.sleep(0.4)
st = json.loads(cursor_state())
print("after Home again:", st)
assert st["idx"] == 0, f"再次 Home 不回首行: {st}"

print("PASS: Home/End 首末行跳转 + 末行 scrollIntoView 滚入视口")
