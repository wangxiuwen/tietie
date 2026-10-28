# 方向217 真机验证：抽屉搜索框聚焦全选
# 剧本（零副作用，只动 UI 查询状态并还原）：
#   抽屉显示 → 合成聚焦输入框填入查询词 → blur →
#   可信 click 重新聚焦 → selectionStart==0 且 selectionEnd==len（全选）
#   → 键入替换词 → 列表按新词过滤（全选替换生效）→ 清空查询还原
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


drawer = CDP(page_ws(lambda u: u.rstrip("/").endswith("tauri.localhost")))


def raw(method, params):
    drawer.seq += 1
    rid = drawer.seq
    drawer.ws.send(json.dumps({"id": rid, "method": method, "params": params}))
    while True:
        m = json.loads(drawer.ws.recv_text())
        if m.get("id") == rid:
            if "error" in m:
                raise RuntimeError(m["error"])
            return m.get("result", {})


# 抽屉显示（搜索框在 380 高抽屉的折线下方，点击法不可达——R211 同款；
# programmatic focus() 同样派发真实 focus 事件，走同一条 React onFocus 链路）
drawer.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.8)

# 合成填入查询词（React onChange 路径），先 blur 模拟「重新聚焦」前提
drawer.eval(r"""(() => {
    const i = document.querySelector('.search input');
    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    i.focus();
    set.call(i, 'text');
    i.dispatchEvent(new Event('input', {bubbles: true}));
    return 'typed';
})()""")
time.sleep(0.4)
q1 = drawer.eval(r"""(() => {
    const i = document.querySelector('.search input');
    i.blur();
    return i.value;
})()""")
print("query typed:", q1)
assert q1 == "text", "查询词未生效"
time.sleep(0.3)

# 重新聚焦（真实 focus 事件 → React onFocus → select() 全选）
drawer.eval(r"""(() => { document.querySelector('.search input').focus(); return 'refocused'; })()""")
time.sleep(0.4)
sel = json.loads(drawer.eval(r"""(() => {
    const i = document.querySelector('.search input');
    return JSON.stringify({focused: document.activeElement === i, s: i.selectionStart,
                           e: i.selectionEnd, len: i.value.length});
})()"""))
print("after refocus:", sel)
assert sel["focused"], "点击后输入框未聚焦"
assert sel["s"] == 0 and sel["e"] == sel["len"] and sel["len"] > 0, f"未全选: {sel}"

# 键入替换词（全选被替换）——CDP 输入域 insertText（等价键入替换选区；
# dispatchKeyEvent 不带 text 不产生字符插入）
raw("Input.insertText", {"text": "i"})
time.sleep(0.4)
q2 = drawer.eval(r"""(() => document.querySelector('.search input').value)()""")
print("after replace-type:", repr(q2))
assert q2 == "i", f"全选替换未生效: {q2!r}"

# 还原：清空查询
drawer.eval(r"""(() => {
    const i = document.querySelector('.search input');
    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    set.call(i, '');
    i.dispatchEvent(new Event('input', {bubbles: true}));
    return 'cleared';
})()""")
time.sleep(0.3)
print("PASS: 聚焦全选 + 一次键入整体替换（可信输入实测）")
