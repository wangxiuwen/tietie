# 方向204 真机验证：Library 搜索框 × 清空钮（+ Esc 键孪生）
# 剧本（合成输入 + DOM 断言，结束清查询还原）：
#   空查询 → 无 .lib-clear
#   → 注入查询（产生过滤效果）→ 钮出现
#   → 合成点击 × → 查询清空、钮消失、行数复原
#   → 再注入查询 → Esc → 同样清空（键盘孪生）
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and "view=library" in t["url"])
lib = CDP(ws_url)
lib.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); '
         'await window.__TAURI_INTERNALS__.invoke("plugin:window|set_focus"); })()')
time.sleep(0.8)
lib.eval(r"""(async () => {
  await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 1});
  window.dispatchEvent(new Event('library-open'));
  window.dispatchEvent(new Event('clipboard-changed'));
})()""")
time.sleep(0.6)


def js(code):
    out = lib.eval(code)
    if not isinstance(out, str):
        raise RuntimeError("type")
    return out


def set_query(q):
    got = js(rf"""(() => {{
  const i = document.querySelector('.lib-search');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, {json.dumps(q)});
  i.dispatchEvent(new Event('input', {{bubbles: true}}));
  return i.value;
}})()""")
    assert got == q, got
    time.sleep(0.5)


def state():
    return json.loads(js(r"""(() => JSON.stringify({
  q: document.querySelector('.lib-search').value,
  clear: document.querySelector('.lib-clear') ? 'y' : 'n',
  rows: document.querySelectorAll('tbody tr').length,
}))()"""))


# 开局清场
set_query("")
b0 = state()
print("baseline:", b0)
assert b0["q"] == "" and b0["clear"] == "n" and b0["rows"] > 0

# 注入查询 → 钮出现 + 行数变化（选一个存在的词）
word = json.loads(js(r"""(() => {
  const r0 = document.querySelector('tbody tr .lib-row-text');
  return JSON.stringify(r0 ? r0.textContent.trim().slice(0, 2) : null);
})()"""))
set_query(word)
s1 = state()
print("with query:", s1)
assert s1["clear"] == "y" and s1["q"] == word, "钮未随查询出现"

# 合成点击 ×
n = js(r"""(() => { const b = document.querySelector('.lib-clear'); if (!b) return 'nobtn'; b.click(); return 'ok'; })()""")
assert n == "ok"
time.sleep(0.5)
s2 = state()
print("after ×:", s2)
assert s2["q"] == "" and s2["clear"] == "n" and s2["rows"] == b0["rows"], "× 未清空/未复原"

# Esc 孪生
set_query(word)
s3 = state()
assert s3["clear"] == "y"
lib.eval(r"""(() => {
  const i = document.querySelector('.lib-search');
  i.focus();
  i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}));
})()""")
time.sleep(0.5)
s4 = state()
print("after Esc:", s4)
assert s4["q"] == "" and s4["clear"] == "n", "Esc 未清空"
print("PASS: 查询非空显钮、× 点击清空+行数复原、Esc 键盘孪生，全链实测")
