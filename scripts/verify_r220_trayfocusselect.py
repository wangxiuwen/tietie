# 方向220 真机验证：托盘搜索框聚焦全选（可信点击路径）
# R224 教训全程遵守：programmatic focus() 不触发 React onFocus，必须可信点击。
# 剧本（零副作用，查询用完还原）：
#   托盘面板 show（裸 show 存活，R216 法）→ 合成填词 → blur →
#   可信点击搜索框 → onFocus → 延迟 select → 断言 selection 0..len → 清空还原
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


tray = CDP(page_ws(lambda u: "view=tray" in u))


def raw(method, params):
    tray.seq += 1
    rid = tray.seq
    tray.ws.send(json.dumps({"id": rid, "method": method, "params": params}))
    while True:
        m = json.loads(tray.ws.recv_text())
        if m.get("id") == rid:
            if "error" in m:
                raise RuntimeError(m["error"])
            return m.get("result", {})


# 面板显示 + 预清残留查询
tray.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.8)
tray.eval(r"""(() => {
    const i = document.querySelector('.po-search-box input');
    if (i.value) {
        const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        set.call(i, '');
        i.dispatchEvent(new Event('input', {bubbles: true}));
    }
    return 'pre-cleaned';
})()""")
time.sleep(0.3)

# 合成填词（React onChange 路径）→ blur
tray.eval(r"""(() => {
    const i = document.querySelector('.po-search-box input');
    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    set.call(i, 'zzz-no-hit');
    i.dispatchEvent(new Event('input', {bubbles: true}));
    return 'typed';
})()""")
time.sleep(0.4)
q1 = tray.eval(r"""(() => {
    const i = document.querySelector('.po-search-box input');
    i.blur();
    return i.value;
})()""")
print("query typed:", q1)
assert q1 == "zzz-no-hit", f"填词失败: {q1}"
time.sleep(0.3)

# 可信点击搜索框 → 全选
box = json.loads(tray.eval(r"""(() => {
    const b = document.querySelector('.po-search-box input').getBoundingClientRect();
    return JSON.stringify({x: b.left + b.width / 2, y: b.top + b.height / 2,
                           vis: b.top >= 0 && b.bottom <= window.innerHeight});
})()"""))
assert box["vis"], f"搜索框不在视口: {box}"
raw("Input.dispatchMouseEvent", {"type": "mousePressed", "x": box["x"], "y": box["y"],
                                 "button": "left", "buttons": 1, "clickCount": 1})
raw("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": box["x"], "y": box["y"],
                                 "button": "left", "buttons": 0, "clickCount": 1})
time.sleep(0.5)
sel = json.loads(tray.eval(r"""(() => {
    const i = document.querySelector('.po-search-box input');
    return JSON.stringify({focused: document.activeElement === i,
                           s: i.selectionStart, e: i.selectionEnd, len: i.value.length});
})()"""))
print("after trusted click:", sel)
assert sel["focused"] and sel["s"] == 0 and sel["e"] == sel["len"] > 0, f"未全选: {sel}"

# 清空还原
tray.eval(r"""(() => {
    const i = document.querySelector('.po-search-box input');
    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    set.call(i, '');
    i.dispatchEvent(new Event('input', {bubbles: true}));
    return 'cleared';
})()""")
time.sleep(0.3)
# 面板收回常态
tray.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|hide"); })()')
time.sleep(0.3)
print("PASS: 托盘搜索框可信点击聚焦 → 全选（onFocus 延迟 select 链路）")
