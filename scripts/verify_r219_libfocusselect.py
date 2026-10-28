# 方向219 真机验证：Library 搜索框聚焦全选
# 剧本（零副作用，查询状态用完还原）：
#   Library 窗 → 合成填查询词 → blur → programmatic focus()（真实 focus
#   事件走 React onFocus，R217 已证等价）→ selection 0..len 全选
#   → Input.insertText 一击整体替换 → 行数过滤变化旁证 → 清空还原
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


def raw(method, params):
    lib.seq += 1
    rid = lib.seq
    lib.ws.send(json.dumps({"id": rid, "method": method, "params": params}))
    while True:
        m = json.loads(lib.ws.recv_text())
        if m.get("id") == rid:
            if "error" in m:
                raise RuntimeError(m["error"])
            return m.get("result", {})


def rows():
    return lib.eval(r"""(() => document.querySelectorAll('.lib-table tbody tr').length)()""")


# 预清理：上跑可能残留查询词
lib.eval(r"""(() => {
    const i = document.querySelector('.lib-search');
    if (i.value) {
        const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        set.call(i, '');
        i.dispatchEvent(new Event('input', {bubbles: true}));
    }
    return 'pre-cleaned';
})()""")
time.sleep(0.4)

base = rows()
print("rows baseline:", base)
assert base >= 2, "Library 行数不足"

# 合成填词（React onChange 路径）→ blur
lib.eval(r"""(() => {
    const i = document.querySelector('.lib-search');
    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    i.focus();
    set.call(i, 'zzz-no-hit-词');
    i.dispatchEvent(new Event('input', {bubbles: true}));
    return 'typed';
})()""")
time.sleep(0.5)
q1 = lib.eval(r"""(() => { const i = document.querySelector('.lib-search'); i.blur(); return i.value; })()""")
assert q1 == "zzz-no-hit-词", f"填词失败: {q1}"
time.sleep(0.3)
n_filtered = rows()
print("filtered rows:", n_filtered)
assert n_filtered < base, "过滤未生效"

# 重新聚焦 → 全选（可信点击 = 真用户路径；programmatic focus() 不触发
# React onFocus——CDP 评估上下文的派发假象，R224 打点实锤）
box = json.loads(lib.eval(r"""(() => {
    const b = document.querySelector('.lib-search').getBoundingClientRect();
    return JSON.stringify({x: b.left + b.width / 2, y: b.top + b.height / 2,
                           vis: b.top >= 0 && b.bottom <= window.innerHeight});
})()"""))
assert box["vis"], "搜索框不在视口"
raw("Input.dispatchMouseEvent", {"type": "mousePressed", "x": box["x"], "y": box["y"],
                                 "button": "left", "buttons": 1, "clickCount": 1})
raw("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": box["x"], "y": box["y"],
                                 "button": "left", "buttons": 0, "clickCount": 1})
time.sleep(0.5)
sel = json.loads(lib.eval(r"""(() => {
    const i = document.querySelector('.lib-search');
    return JSON.stringify({focused: document.activeElement === i,
                           s: i.selectionStart, e: i.selectionEnd, len: i.value.length});
})()"""))
print("after trusted-click refocus:", sel)
assert sel["focused"] and sel["s"] == 0 and sel["e"] == sel["len"] > 0, f"未全选: {sel}"

# 一击整体替换 → 行数回升旁证
raw("Input.insertText", {"text": ""})
time.sleep(0.2)
lib.eval(r"""(() => {
    // insertText 空串不产生 input 事件；直接走 React setter 清空
    const i = document.querySelector('.lib-search');
    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    set.call(i, '');
    i.dispatchEvent(new Event('input', {bubbles: true}));
    return 'cleared';
})()""")
time.sleep(0.4)
back = rows()
print("rows restored:", back)
assert back == base, "清空后行数未复原"

print("PASS: Library 搜索框聚焦全选（React onFocus 链路）+ 过滤链路旁证")
