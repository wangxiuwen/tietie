# 方向169 真机验证：批量栏所选含 🔒 敏感项时显示警示
# 剧本（产品命令标记敏感 + 抽屉可信 Ctrl 点选，结束全还原）：
#   set_item_sensitive(itemA, true)（产品命令路径）
#   → Ctrl+点选 A+B 两卡 → 断言批量栏「已选 2」+「⚠ 1 🔒」chip 在位且 title 正确
#   → Ctrl+点 A 取消其选择 → chip 消失、剩「已选 1」
#   → 清选择 + set_item_sensitive(A, false) 还原
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


def ctrl_click_card(idx):
    pos = json.loads(d.eval(rf"""(() => {{
  const c = document.querySelector('.cards [data-idx="{idx}"]');
  if (!c) return 'NOCARD';
  c.scrollIntoView({{block: 'nearest'}});
  const r = c.getBoundingClientRect();
  return JSON.stringify({{x: r.x + 24, y: r.y + 14}});
}})()"""))
    for typ in ("mousePressed", "mouseReleased"):
        d.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                              "params": {"type": typ, "button": "left",
                                         "buttons": 1 if typ == "mousePressed" else 0,
                                         "clickCount": 1, "modifiers": 2,
                                         "x": pos["x"], "y": pos["y"]}}))
        d.ws.recv_text()
        time.sleep(0.12)


def bar():
    out = d.eval(r"""(() => {
  const bar = document.querySelector('.batch-bar');
  if (!bar) return JSON.stringify({present: false});
  const chip = bar.querySelector('.batch-sens');
  return JSON.stringify({present: true,
    text: bar.querySelector('span').textContent.trim(),
    chip: chip ? {text: chip.textContent.trim(), title: chip.title} : null});
})()""")
    if not isinstance(out, str):
        raise RuntimeError("bar eval type")
    return json.loads(out)


# 清残留选择
d.eval(r"""(() => {
  const bar = document.querySelector('.batch-bar');
  const clear = bar && [...bar.querySelectorAll('button')].find(b =>
    b.textContent.includes('取消选择'));
  if (clear) clear.click();
})()""")
time.sleep(0.3)

items = invoke("list_items", {"limit": 10})
a, b = items[0], items[1]
invoke("set_item_sensitive", {"id": a["id"], "on": True})
time.sleep(0.5)

ctrl_click_card(0)
time.sleep(0.2)
ctrl_click_card(1)
time.sleep(0.5)
s1 = bar()
print("select A+B:", s1)
assert s1["present"], "批量栏未出现"
assert "2" in s1["text"], f"已选计数异常: {s1['text']}"
assert s1["chip"] and s1["chip"]["text"] == "⚠ 1 🔒", f"敏感 chip 异常: {s1['chip']}"
assert "敏感" in s1["chip"]["title"], f"chip title 异常: {s1['chip']}"

ctrl_click_card(0)  # 取消 A
time.sleep(0.4)
s2 = bar()
print("deselect A:", s2)
assert "1" in s2["text"] and not s2["chip"], "取消敏感项后 chip 未消失"

# 还原：清选择 + 摘掉敏感标记
d.eval(r"""(() => {
  const bar = document.querySelector('.batch-bar');
  const clear = bar && [...bar.querySelectorAll('button')].find(b =>
    b.textContent.includes('取消选择'));
  if (clear) clear.click();
})()""")
invoke("set_item_sensitive", {"id": a["id"], "on": False})
time.sleep(0.5)
assert not bar()["present"], "清理后批量栏仍在"
left = invoke("list_items", {"limit": 10})[0]["sensitive"]
assert left is False, "敏感标记未还原"
print("PASS: 含敏感项多选出现 ⚠ 1 🔒 警示、取消即隐、现场全还原")
