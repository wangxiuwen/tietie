# 方向173 真机验证：文件夹折叠 + 拖卡到已折叠文件夹即收入
# 剧本（产品命令造夹 + 合成双击折叠 + 可信指针拖放，结束全还原）：
#   create_folder → chip 出现 → 合成 dblclick 折叠（swatch-only，title=名）
#   → 可信拖拽：卡片 press → move 至折叠 chip → release
#   → 断言条目 folder_id == 夹 id（桥）且折叠 chip drop-hot 曾点亮（不强求）
#   → 还原：set_item_folder null、dblchip 展开、delete_folder
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


def invoke(cmd, args=None):
    out = d.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} -> {type(out).__name__}")
    return json.loads(out)


def mouse(typ, x, y, btn="left", btns=None, mods=0):
    d.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent", "params": {
        "type": typ, "button": btn,
        "buttons": btns if btns is not None else (1 if typ == "mousePressed" and btn == "left" else 0),
        "clickCount": 1 if typ in ("mousePressed", "mouseReleased") else 0,
        "modifiers": mods, "x": x, "y": y}}))
    d.ws.recv_text()
    time.sleep(0.1)


# 1) 造夹（product path）
fid = invoke("create_folder", {"name": "R173折叠夹", "color": "#34c759"})
print("folder id:", fid)
# 抽屉的 folders 只在 show-drawer 监听里重载——造夹后戳一下
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)

chip = json.loads(d.eval(rf"""(() => {{
  const c = document.querySelector('[data-folder-id="{fid}"]');
  const r = c.getBoundingClientRect();
  return JSON.stringify({{x: r.x + r.width / 2, y: r.y + r.height / 2,
    name: c.textContent.trim()}});
}})()"""))
print("chip:", chip)
assert "R173折叠夹" in chip["name"]

# 2) 合成双击折叠
d.eval(rf"""(() => {{
  const c = document.querySelector('[data-folder-id="{fid}"]');
  c.dispatchEvent(new MouseEvent('dblclick', {{bubbles: true, cancelable: true}}));
}})()""")
time.sleep(0.5)
folded = json.loads(d.eval(rf"""(() => {{
  const c = document.querySelector('[data-folder-id="{fid}"]');
  const r = c.getBoundingClientRect();
  return JSON.stringify({{foldedCls: c.className.includes('folded'),
    text: c.textContent.trim(), title: c.title, w: Math.round(r.width),
    x: r.x + r.width / 2, y: r.y + r.height / 2}});
}})()"""))
print("folded:", folded)
assert folded["foldedCls"] and folded["text"] == "" and folded["title"] == "R173折叠夹", \
    f"折叠态异常: {folded}"
assert folded["w"] < 24, "折叠后宽度未收窄"

# 3) 可信拖拽：卡片 → 折叠 chip
item0 = invoke("list_items", {"limit": 10})[0]
card = json.loads(d.eval(r"""(() => {
  const c = document.querySelector('.cards [data-idx="0"]');
  const r = c.getBoundingClientRect();
  return JSON.stringify({x: r.x + 30, y: r.y + 20});
})()"""))
print("drag card at", card, "→ chip at", folded["x"], folded["y"])
mouse("mousePressed", card["x"], card["y"])
for i in range(1, 6):
    mx = card["x"] + (folded["x"] - card["x"]) * i / 5
    my = card["y"] + (folded["y"] - card["y"]) * i / 5
    mouse("mouseMoved", round(mx, 1), round(my, 1))
mouse("mouseMoved", folded["x"], folded["y"])
time.sleep(0.2)
mouse("mouseReleased", folded["x"], folded["y"])
time.sleep(1.0)

now = invoke("list_items", {"limit": 10})[0]
print("item folder_id:", now.get("folder_id"))
assert now["id"] == item0["id"] and now.get("folder_id") == fid, \
    f"拖入折叠夹失败: {now.get('folder_id')} != {fid}"

# 4) 还原：条目移出 + 展开夹 + 删夹
invoke("set_item_folder", {"id": item0["id"], "folderId": None})
d.eval(rf"""(() => {{
  const c = document.querySelector('[data-folder-id="{fid}"]');
  c.dispatchEvent(new MouseEvent('dblclick', {{bubbles: true, cancelable: true}}));
}})()""")
time.sleep(0.4)
unfolded = d.eval(rf"""document.querySelector('[data-folder-id="{fid}"]').className.includes('folded') ? 'y' : 'n'""")
assert unfolded == "n", "展开失败"
invoke("delete_folder", {"id": fid})
time.sleep(0.4)
assert invoke("list_folders", {}) == [], "夹未删除"
restored = invoke("list_items", {"limit": 10})[0]
assert restored.get("folder_id") is None, "条目未移出"
print("PASS: 双击折叠、拖卡到已折叠夹收入、展开与删除全还原")
