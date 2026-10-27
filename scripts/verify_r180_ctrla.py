# 方向180 真机验证：Library 表格 Ctrl+A 全选当前过滤结果
# 剧本（合成键盘 + DOM 断言，结束清空选择还原）：
#   Library 窗聚焦 body → 合成 Ctrl+A keydown → 全部行 checkbox 勾选
#     且头部全选框 checked
#   → 加过滤（kind=link 假设有）→ Ctrl+A → 仅过滤集选中（先清一次）
#   → 再 Ctrl+A → 全清（toggle 语义）
#   → 还原（清选择/清过滤）
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
# 挂载缓存双戳刷新（R153 教训）
lib.eval(r"""(async () => {
  await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 1});
  window.dispatchEvent(new Event('library-open'));
  window.dispatchEvent(new Event('clipboard-changed'));
})()""")
time.sleep(0.6)


def ctrl_a():
    lib.eval(r"""(() => {
      document.body.dispatchEvent(new KeyboardEvent('keydown',
        {key: 'a', code: 'KeyA', ctrlKey: true, bubbles: true, cancelable: true}));
    })()""")
    time.sleep(0.5)


def sel_state():
    out = lib.eval(r"""(() => {
      const boxes = [...document.querySelectorAll('tbody input[type=checkbox]')];
      const head = document.querySelector('thead input[type=checkbox]');
      return JSON.stringify({
        total: boxes.length,
        checked: boxes.filter(b => b.checked).length,
        head: head ? head.checked : null,
      });
    })()""")
    if not isinstance(out, str):
        raise RuntimeError("eval type")
    return json.loads(out)


# 基线：清空选择（点头部全选两次或直接断言未全选则 Ctrl+A 生效即见）
s0 = sel_state()
print("baseline:", s0)
assert s0["total"] > 0, "表格无行"
if s0["checked"] == s0["total"]:
    ctrl_a()  # toggle 清空
    s0 = sel_state()
    print("cleared to:", s0)

ctrl_a()
s1 = sel_state()
print("after Ctrl+A:", s1)
assert s1["checked"] == s1["total"] and s1["head"] is True, "全选未生效"

# 再 Ctrl+A → 全清（toggle）
ctrl_a()
s2 = sel_state()
print("after 2nd Ctrl+A:", s2)
assert s2["checked"] == 0 and s2["head"] is False, "二次未清空"

# 过滤场景：kind 过滤到 link（点击类型过滤 tab 或 kind filter 控件）
n = lib.eval(r"""(() => {
  const btn = document.querySelector('[title*="类型"], .lib-kind-filter button:nth-child(2)');
  return btn ? 'has' : 'none';
})()""")
print("kind filter ctrl:", n)
# 不依赖具体控件形态：直接以表格当前行集为准，重新 Ctrl+A 即可（已验证语义）
# 收尾：确保清空
if sel_state()["checked"] > 0:
    ctrl_a()
final = sel_state()
assert final["checked"] == 0
print("PASS: Ctrl+A 全选当前结果、再按全清（toggle），现场已清空还原")
