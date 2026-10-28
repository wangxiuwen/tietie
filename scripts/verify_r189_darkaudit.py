# 方向189 真机验证：托盘 po-* 暗色适配查漏（真机系统暗色直证 + 模拟亮色对照）
# 剧本：
#   注入 .po-note-edit 元素（纯 DOM，不落库）
#   → 读系统当前 scheme；真机此刻为 dark → 直接断言：
#     noteInput=白味 rgba(255,255,255,0.07)、searchInput 白味（110 项）、
#     po-top 阴影深黑
#   → Emulation 强制 light → 断言翻回黑味 rgba(0,0,0,...)（对照两侧都有值）
#   → 清除模拟
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and "view=tray" in t["url"])
st = CDP(ws_url)

inj = "noroot"
for _ in range(10):
    inj = st.eval(r"""(() => {
    const root = document.querySelector('.popover');
    if (!root) return 'noroot';
    if (document.querySelector('.po-note-edit input')) return 'exists';
    const div = document.createElement('div');
    div.className = 'po-note-edit';
    div.appendChild(document.createElement('input'));
    root.insertBefore(div, root.firstChild);
    return 'injected';
  })()""")
    if inj in ("injected", "exists"):
        break
    time.sleep(0.4)
assert inj in ("injected", "exists"), "托盘根节点未就绪"
# po-top 仅在滚动后渲染——补一个同 class 元素供阴影断言
st.eval(r"""(() => {
  if (document.querySelector('.po-top')) return 'exists';
  const b = document.createElement('button');
  b.className = 'po-top';
  document.querySelector('.popover').appendChild(b);
  return 'injected';
})()""")
time.sleep(0.3)


def styles():
    out = st.eval(r"""(() => JSON.stringify({
  scheme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
  noteInput: getComputedStyle(document.querySelector('.po-note-edit input')).backgroundColor,
  searchInput: getComputedStyle(document.querySelector('.po-search input')).backgroundColor,
  topShadow: (() => { const t = document.querySelector('.po-top');
    return t ? getComputedStyle(t).boxShadow : 'none'; })(),
}))()""")
    if not isinstance(out, str):
        raise RuntimeError("type")
    return json.loads(out)


def emulate(scheme):
    st.ws.send(json.dumps({"id": 8801, "method": "Emulation.setEmulatedMedia",
                           "params": {"features": [
                               {"name": "prefers-color-scheme", "value": scheme}]}}))
    st.ws.recv_text()
    time.sleep(0.6)


cur = styles()
print("system now:", cur)
assert cur["scheme"] == "dark", f"真机当前非暗色（{cur['scheme']}），改用模拟"
assert cur["noteInput"] == "rgba(255, 255, 255, 0.07)", f"备注输入暗色未翻: {cur['noteInput']}"
assert cur["searchInput"].startswith("rgba(255, 255, 255"), f"110 项回归: {cur['searchInput']}"
assert "rgba(0, 0, 0, 0.5)" in cur["topShadow"], f"回顶钮阴影未加深: {cur['topShadow']}"

emulate("light")
light = styles()
print("forced light:", light)
assert light["noteInput"] == "rgba(0, 0, 0, 0.04)", f"亮色对照失败: {light['noteInput']}"
assert light["searchInput"].startswith("rgba(0, 0, 0"), "亮色 search 对照失败"

# 清模拟（恢复系统暗色原态）
emulate("dark")
print("PASS: 真机暗色下 note-edit 翻白味/search 110 项在/po-top 阴影加深，模拟亮色对照翻转正确")
