# 方向176 真机验证：托盘行右键「备注」→ 行内编辑器 → Enter 落库
# 剧本（合成输入 + 桥核对，结束清备注还原）：
#   合成 contextmenu 开行右键菜单 → 断言含「备注…」项
#   → 合成点击该项 → 搜索框下出现 .po-note-edit input（autoFocus）
#   → 原生 setter 注入备注文本 + 合成 Enter → 桥断言 item.note == 文本
#   → set_item_note 清空还原
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and "view=tray" in t["url"])
tray = CDP(ws_url)
tray.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.6)

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    main = CDP(next(t["webSocketDebuggerUrl"] for t in json.load(r)
                    if t["type"] == "page" and (t["url"].endswith("/") or "view=" not in t["url"])))


def inv(cmd, args=None):
    out = main.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} type")
    return json.loads(out)


# 行 0 右键（合成 contextmenu 事件驱动 React onContextMenu）
n = tray.eval(r"""(() => {
  const row = document.querySelector('.po-row[data-idx="0"]');
  if (!row) return 'norow';
  const r = row.getBoundingClientRect();
  row.dispatchEvent(new MouseEvent('contextmenu',
    {bubbles: true, cancelable: true, clientX: r.x + 20, clientY: r.y + 10}));
  return 'ok';
})()""")
assert n == "ok", n
time.sleep(0.5)

items = json.loads(tray.eval(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.ctx-item')].map(e => e.textContent.trim())))()"""))
print("menu items:", items)
assert "备注…" in items, f"备注项缺失: {items}"

target_id = inv("list_items", {"limit": 30})[0]["id"]
assert inv("list_items", {"limit": 30})[0].get("note") in (None, ""), "目标行已有备注，现场不净"

# 点击「备注…」→ 行内编辑器
c = tray.eval(r"""(() => {
  const it = [...document.querySelectorAll('.ctx-item')].find(e => e.textContent.trim() === '备注…');
  if (!it) return 'noitem';
  it.click();
  return 'ok';
})()""")
assert c == "ok", c
time.sleep(0.5)
editor = tray.eval("document.querySelector('.po-note-edit input') ? 'y' : 'n'")
print("editor:", editor)
assert editor == "y", "行内编辑器未出现"

NOTE = "R176托盘备注探针"
got = tray.eval(rf"""(() => {{
  const i = document.querySelector('.po-note-edit input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, {json.dumps(NOTE)});
  i.dispatchEvent(new Event('input', {{bubbles: true}}));
  return i.value;
}})()""")
assert got == NOTE, got
time.sleep(0.2)

# 合成 Enter 保存
tray.eval(r"""(() => {
  const i = document.querySelector('.po-note-edit input');
  i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true}));
})()""")
time.sleep(0.8)

now = inv("list_items", {"limit": 30})[0]
print("item note:", now.get("note"))
assert now["id"] == target_id and now.get("note") == NOTE, f"备注未落库: {now.get('note')!r}"
closed = tray.eval("document.querySelector('.po-note-edit') ? 'n' : 'y'")
assert closed == "y", "保存后编辑器未关闭"

# 还原
inv("set_item_note", {"id": target_id, "note": None})
time.sleep(0.4)
back = inv("list_items", {"limit": 30})[0]
assert back.get("note") in (None, ""), "备注未清"
print("PASS: 右键备注 → 行内编辑 → Enter 落库 → 编辑器关闭 → 清空还原")
