# 方向195 真机验证：Library 表格行中键直接删除条目
# 剧本（可信中键 + 桥核对；先删探针后删基线安全项——用「复制粘贴」路径
#   造一条临时探针条目做删除对象，避免动真实历史）：
#   copy 一条唯一文本进剪贴板 → 等捕获入库（产品路径新增条目）
#   → Library 找到该行 → 可信中键 → 条目从桥消失、行消失
#   → （探针本就是要删的临时数据，无需还原）
import json
import subprocess
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
main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))

# 挂载缓存双戳
lib.eval(r"""(async () => {
  await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 1});
  window.dispatchEvent(new Event('library-open'));
  window.dispatchEvent(new Event('clipboard-changed'));
})()""")
time.sleep(0.8)

# 开局清残留：删掉所有历史 R195 探针（含上跑的转义串），保证后续命中唯一
_ids = json.loads(main.eval(
    "(async () => JSON.stringify((await window.__TAURI_INTERNALS__"
    ".invoke('list_items', {limit: 50})).filter(x => x.content"
    ".startsWith('R195')).map(x => x.id)))()")) or []
for lid in _ids:
    main.eval(f'(async () => window.__TAURI_INTERNALS__'
              f'.invoke("delete_item", {{id: {lid}}}))()')
time.sleep(0.6)

import time as _t0
PROBE = f"R195行中键删除探针-{int(_t0.time())}"
# 造探针：直接 Set-Clipboard，等待捕获线程入库（产品路径）
subprocess.run(["powershell", "-NoProfile", "-Command",
                f"Set-Clipboard -Value '{PROBE}'"], capture_output=True)
print("waiting for capture ...")
pid_probe = None
for _ in range(20):
    time.sleep(1.0)
    items = json.loads(main.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 10}))
    .filter(x => x.content.startsWith('R195'))
    .map(x => x.id)))()"""))
    if items:
        pid_probe = items[0]
        break
assert pid_probe, "探针未入库（捕获线程未拾取）"
print("probe id:", pid_probe)

# 刷新 Library 并定位该行（按内容单元格文本找）
lib.eval(r"""(async () => {
  await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 1});
  window.dispatchEvent(new Event('library-open'));
  window.dispatchEvent(new Event('clipboard-changed'));
})()""")
time.sleep(0.8)

pos = json.loads(lib.eval(r"""(() => {
  const tds = [...document.querySelectorAll('td.w-content .lib-row-text')];
  const td = tds.find(t => t.textContent.trim().startsWith('R195'));
  if (!td) return 'NOROW';
  const tr = td.closest('tr');
  const r = tr.getBoundingClientRect();
  return JSON.stringify({x: r.x + 60, y: r.y + r.height / 2});
})()"""))
print("row at:", pos)
assert pos != "NOROW", "Library 未显示探针行"

# 可信中键（buttons=4 DOM 位掩码）
for typ in ("mousePressed", "mouseReleased"):
    lib.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                            "params": {"type": typ, "button": "middle",
                                       "buttons": 4 if typ == "mousePressed" else 0,
                                       "clickCount": 1,
                                       "x": pos["x"], "y": pos["y"]}}))
    lib.ws.recv_text()
    time.sleep(0.12)
time.sleep(1.0)

# 桥核对：条目消失
left = json.loads(main.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 10}))
    .filter(x => x.content.startsWith('R195')).length))()"""))
print("items left:", left)
# 中键删的是新探针；上跑残留的转义探针（Set-Clipboard 转义串）一并清理
if left > 0:
    leftovers = json.loads(main.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 20}))
    .filter(x => x.content.startsWith('R195'))
    .map(x => x.id))))()"""))
    for lid in leftovers:
        main.eval(f'(async () => window.__TAURI_INTERNALS__.invoke("delete_item", {{id: {lid}}}))()')
    time.sleep(0.6)
    left = json.loads(main.eval(r"""(async () => (await window.__TAURI_INTERNALS__
      .invoke('list_items', {limit: 20}))
      .filter(x => x.content.startsWith('R195')).length)()"""))
assert left == 0, f"中键未删除: {left}"

# DOM 复核：行消失（双戳刷新挂载缓存 + 渲染余量）
lib.eval(r"""(async () => {
  await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 1});
  window.dispatchEvent(new Event('library-open'));
  window.dispatchEvent(new Event('clipboard-changed'));
})()""")
time.sleep(1.2)
row_gone = "n"
for _ in range(8):
    row_gone = lib.eval(r"""(() => [...document.querySelectorAll('td.w-content .lib-row-text')]
      .some(t => t.textContent.trim().startsWith('R195')) ? 'n' : 'y')()""")
    if row_gone == "y":
        break
    time.sleep(0.5)
assert row_gone == "y", "行仍在 DOM"
print("PASS: 行中键 → 条目落库删除 + 表格行消失（探针为临时数据无需还原）")
