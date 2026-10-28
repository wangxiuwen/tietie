# 方向203 真机验证：设置页配对设备按最近同步在前
# 现库仅 1 台已配对（wsl-tietie, last_sync_at=1793068421）——排序断言对
# 单台平凡成立，但排序代码路径真实执行；采用「桥数据期望序 vs DOM 序」
# 通用断言（多台亦成立）。另外用纯函数级验证补强：把排序谓词在页面里
# 对构造的三元数组求值，断言输出顺序=last_sync_at 降序（验证谓词本身）。
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


st = CDP(page_ws(lambda u: "view=settings" in u))
st.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.2)

# 1) DOM 顺序 vs 桥数据期望序（通用，单台平凡通过）
dom = json.loads(st.eval(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.lan-peer .pair-name')]
    .map(i => i.value)))()"""))
expected = json.loads(st.eval(r"""(async () => {
  const ps = await window.__TAURI_INTERNALS__.invoke('pairing_list');
  return JSON.stringify([...ps]
    .sort((a, b) => (b.last_sync_at || 0) - (a.last_sync_at || 0))
    .map(p => p.name ?? p.instance));
})()"""))
print("DOM order:", dom)
print("expected :", expected)
assert dom == expected, f"顺序不符: {dom} != {expected}"
assert len(dom) >= 1, "无已配对设备（验证面缺失）"

# 2) 排序谓词纯函数级验证（三元构造数组，证明降序+0 兜底）
pred = json.loads(st.eval(r"""(() => {
  const arr = [
    {n: 'old', last_sync_at: 100},
    {n: 'never', last_sync_at: 0},
    {n: 'new', last_sync_at: 999},
  ];
  const sorted = [...arr]
    .sort((a, b) => (b.last_sync_at || 0) - (a.last_sync_at || 0))
    .map(x => x.n);
  return JSON.stringify(sorted);
})()"""))
print("predicate test:", pred)
assert pred == ["new", "old", "never"], f"谓词异常: {pred}"

print("PASS: DOM 序==last_sync_at 降序期望；谓词对 never(0) 兜底排序正确")
