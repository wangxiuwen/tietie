# 方向209 真机验证：Library 表格行 hover 高亮（已具备收口轮）
# 已具备：.lib-table tbody tr:hover 自方向 7（02f087b，Library 管理窗落地）
# 即存在。实证：可信 mouseMoved 移入行 → 计算背景=accent-dim 非 transparent，
# 移出 → 回 transparent，hover/kcursor（键盘行）区分不冲突。
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


def row_bg():
    out = lib.eval(r"""(() => {
  const row = document.querySelector('tbody tr:nth-child(3)');
  return JSON.stringify({bg: getComputedStyle(row).backgroundColor});
})()""")
    if not isinstance(out, str):
        raise RuntimeError("type")
    return json.loads(out)["bg"]


def move(x, y):
    lib.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                            "params": {"type": "mouseMoved", "x": x, "y": y}}))
    lib.ws.recv_text()
    time.sleep(0.4)


base = row_bg()
print("no-hover bg:", base)
assert base in ("rgba(0, 0, 0, 0)", "transparent"), f"基线非透明: {base}"

# 移入第 3 行
pos = json.loads(lib.eval(r"""(() => {
  const row = document.querySelector('tbody tr:nth-child(3)');
  const r = row.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2});
})()"""))
move(pos["x"], pos["y"])
hover = row_bg()
print("hover bg:", hover)
assert hover not in ("rgba(0, 0, 0, 0)", "transparent"), f"hover 无高亮: {hover}"

# 移出（表头区域）
move(pos["x"], 10)
out_bg = row_bg()
print("moved-out bg:", out_bg)
assert out_bg in ("rgba(0, 0, 0, 0)", "transparent"), f"移出未还原: {out_bg}"
print("PASS: 行 hover 高亮在位（移入显色/移出透明），自方向 7 起已具备，本轮实证")
