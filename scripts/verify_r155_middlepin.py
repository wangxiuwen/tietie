# 方向155 真机验证：托盘行中键直接置顶/取消置顶
# 剧本（可信中键输入 + 应用桥核对，全程还原）：
#   显示托盘窗 → 记首行（data-idx=0，list_items[0]）pinned 基线
#   → 可信中键点击首行 → 断言 pinned 翻 true + DOM 出现「置顶」分区标题
#   → 再中键一次 → pinned 回 false + 置顶分区消失（回到基线）
# ★坑：CDP buttons 位掩码 DOM 语义 middle=4；隐藏窗不吃输入，先 plugin:window|show。
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


tray = CDP(page_ws(lambda u: "view=tray" in u))
main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))


def invoke_on(ws, cmd, args=None):
    out = ws.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} -> {type(out).__name__}")
    return json.loads(out)


# 托盘窗自己显示自己（窗口插件通道，与 R156 set_size 同法）
tray.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); '
          'await window.__TAURI_INTERNALS__.invoke("plugin:window|set_focus"); })()')
time.sleep(0.8)


def row0_center():
    out = tray.eval(r"""(() => {
  const c = document.querySelector('.po-row[data-idx="0"]');
  if (!c) return 'NOROW';
  c.scrollIntoView({block: 'center'});
  const r = c.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2,
    text: c.querySelector('.po-text')?.textContent ?? ''});
})()""")
    pos = json.loads(out)
    return {"x": pos["x"], "y": pos["y"], "text": pos["text"]}


def pinned_section_titles():
    return tray.eval(r"""[...document.querySelectorAll('.po-title > span')]
  .map(e => e.textContent.trim()).join('|')""")


def item0():
    return invoke_on(main, "list_items", {"limit": 30})[0]


base = item0()
assert base["pinned"] is False, f"基线首行已置顶，选错对象: {base['preview'][:20]}"
print("baseline row0:", base["preview"][:24], "| pinned:", base["pinned"])
assert "置顶" not in pinned_section_titles(), "基线不该有置顶分区"

# 中键 #1 → 置顶
r0 = row0_center()
print("click row0:", r0["text"][:24], "at", r0["x"], r0["y"])
for typ in ("mousePressed", "mouseReleased"):
    tray.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                             "params": {"type": typ, "button": "middle",
                                        "buttons": 4 if typ == "mousePressed" else 0,
                                        "clickCount": 1, "x": r0["x"], "y": r0["y"]}}))
    tray.ws.recv_text()
    time.sleep(0.12)
time.sleep(0.8)

now = item0()
print("after mid#1: pinned:", now["pinned"], "| titles:", pinned_section_titles())
assert now["pinned"] is True, "中键未置顶"
assert now["id"] == base["id"], "首行换人（排序异常）"
assert "置顶" in pinned_section_titles(), "置顶分区未出现"

# 中键 #2 → 取消还原
r1 = row0_center()
for typ in ("mousePressed", "mouseReleased"):
    tray.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                             "params": {"type": typ, "button": "middle",
                                        "buttons": 4 if typ == "mousePressed" else 0,
                                        "clickCount": 1, "x": r1["x"], "y": r1["y"]}}))
    tray.ws.recv_text()
    time.sleep(0.12)
time.sleep(0.8)

back = item0()
print("after mid#2: pinned:", back["pinned"], "| titles:", pinned_section_titles())
assert back["pinned"] is False and "置顶" not in pinned_section_titles(), "还原失败"
print("PASS: 中键置顶/再中键取消，全程应用桥核对，现场还原")
