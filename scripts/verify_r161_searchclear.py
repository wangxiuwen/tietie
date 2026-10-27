# 方向161 真机验证：抽屉搜索框清空钮
# 剧本（合成输入 + DOM 断言，结束清空查询还原）：
#   空查询 → 无 .search-clear
#   → 注入查询"img:"（有过滤效果）→ 钮出现
#   → 合成点击 × → 查询清空、钮消失、输入框重获焦点
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and (t["url"].endswith("/") or "view=" not in t["url"]))
d = CDP(ws_url)
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)


def js(code):
    out = d.eval(code)
    if not isinstance(out, str):
        raise RuntimeError(f"eval -> {type(out).__name__}")
    return out


def state():
    return json.loads(js(r"""(() => JSON.stringify({
  q: document.querySelector('.search input').value,
  clear: document.querySelector('.search-clear') ? 'y' : 'n',
  focused: document.activeElement === document.querySelector('.search input'),
  cards: document.querySelectorAll('.cards [data-idx]').length}))()"""))


# 开局清场（重跑残留）：非空则注入清空
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  if (i.value) {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    set.call(i, '');
    i.dispatchEvent(new Event('input', {bubbles: true}));
  }
})()""")
time.sleep(0.4)

s0 = state()
print("baseline:", s0)
assert s0["q"] == "" and s0["clear"] == "n", "基线异常（应无查询无钮）"

# 注入查询 img:（157 的类型前缀，顺带回归）
got = js(r"""(() => {
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, 'img:');
  i.dispatchEvent(new Event('input', {bubbles: true}));
  return i.value;
})()""")
assert got == "img:", f"查询未注入: {got!r}"
time.sleep(0.5)
s1 = state()
print("with query:", s1)
assert s1["q"] == "img:" and s1["clear"] == "y", "查询后清空钮未出现"
assert s1["cards"] < s0["cards"], "img: 过滤未生效（回归）"

# 合成点击 × —— onMouseDown preventDefault 保焦点，onClick 清空
n = js(r"""(() => {
  const b = document.querySelector('.search-clear');
  if (!b) return 'nobtn';
  b.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
  b.click();
  return 'ok';
})()""")
assert n == "ok"
time.sleep(0.5)
s2 = state()
print("after clear:", s2)
assert s2["q"] == "" and s2["clear"] == "n", "清空未生效"
assert s2["focused"], "输入框未重获焦点"
assert s2["cards"] == s0["cards"], "清空后列表未复原"
print("PASS: 查询非空显钮、点击 × 清空+复焦+列表复原，全链实测")
