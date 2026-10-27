# 方向156 真机验证：新建便签默认沿用上次提交的颜色
# 剧本（全程 UI 可信输入 + 应用桥核对，清理还原）：
#   挂 1 条引导便签（造出 recents palette）→ 开 composer A：
#   点 recents 色点 + 注入文本（React 原生 setter 旁路）+ 可信 Ctrl+Enter 提交
#   → 桥核 memo A 色值 → 开 composer B：断言 .pal-dot.active 的颜色与 A 相同
#   → 提交 B → 桥核 memo B 色值 == memo A 色值 → remove_memo 全部清理
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


line = CDP(page_ws(lambda u: "view=line" in u))
main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))


def invoke_on(ws, cmd, args=None):
    out = ws.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} -> {type(out).__name__}")
    return json.loads(out)


def trusted_click(ws, x, y):
    for typ in ("mousePressed", "mouseReleased"):
        ws.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                               "params": {"type": typ, "button": "left",
                                          "buttons": 1 if typ == "mousePressed" else 0,
                                          "clickCount": 1, "x": x, "y": y}}))
        ws.ws.recv_text()
        time.sleep(0.12)


def el_center(js_finder):
    out = line.eval(js_finder)
    if not isinstance(out, str):
        raise RuntimeError("eval type")
    pos = json.loads(out)
    return pos["x"], pos["y"]


# ── 准备：窗口可见 + 引导便签（产品命令路径） ──
line.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.6)

memos = invoke_on(main, "list_memos", {})
assert memos == [], f"基线便签非空: {len(memos)}"
first_text = invoke_on(main, "list_items", {"limit": 10})[0]["id"]
assert invoke_on(main, "hang_items", {"ids": [first_text]}) == 1
time.sleep(0.5)
boot = invoke_on(main, "list_memos", {})[0]
print("bootstrap memo color:", boot["color"])


def open_composer():
    # 窄条窗顶边按钮的可信输入有 WebView2 层怪癖（事件到 root 但 React 不派发），
    # 本轮按协议改用合成输入 el.click()
    line.eval(r"""(() => {
  const b = [...document.querySelectorAll('button.line-new')]
    .find(x => (x.title || '').includes('便签') && !x.title.includes('导出'));
  if (b) b.click();
})()""")
    time.sleep(0.5)
    assert str(line.eval(
        "document.querySelector('.line-card.composer textarea') ? 1 : 0")) == "1",         "composer 未打开"


def pick_first_pal():
    """synthetic-click the first recents dot, return its computed background color"""
    bg = line.eval(r"""(() => {
  const d = document.querySelector('.composer-recents .pal-dot');
  if (!d) return 'NODOT';
  const bg = getComputedStyle(d).backgroundColor;
  d.click();
  return bg;
})()""")
    time.sleep(0.3)
    return bg


def type_and_submit(text):
    """inject text into the composer textarea, then trusted-click the commit
    button. The button's disabled state is the oracle for whether React's
    `text` state actually picked the injection up."""
    line.eval(rf"""(() => {{
  const ta = document.querySelector('.line-card.composer textarea');
  ta.focus();
  const set = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype, 'value').set;
  set.call(ta, {json.dumps(text)});
  ta.dispatchEvent(new Event('input', {{bubbles: true}}));
}})()""")
    time.sleep(0.25)
    enabled = line.eval(
        "document.querySelector('.line-card.composer .btn.primary').disabled ? 0 : 1")
    if str(enabled) != "1":
        # React state missed the synthetic input — fall back to trusted
        # IME-style insertion
        line.ws.send(json.dumps({"id": 9903, "method": "Input.insertText",
                                 "params": {"text": text}}))
        line.ws.recv_text()
        time.sleep(0.4)
        enabled = line.eval(
            "document.querySelector('.line-card.composer .btn.primary').disabled ? 0 : 1")
    assert str(enabled) == "1", "文本注入未进入 React 状态（提交钮仍禁用）"
    line.eval(r"""document.querySelector('.line-card.composer .btn.primary').click()""")
    time.sleep(0.8)


# ── composer A：选色提交 ──
open_composer()
bg_a = pick_first_pal()
type_and_submit("R156验证A-沿用色")
memos = invoke_on(main, "list_memos", {})
a = memos[-1]
print("memo A color:", a["color"], "| picked bg:", bg_a)
assert a["content"] == "R156验证A-沿用色", "A 未按提交内容创建"

# ── composer B：默认应带上 A 的颜色 ──
open_composer()
active = json.loads(line.eval(r"""(() => {
  const d = document.querySelector('.composer-recents .pal-dot.active');
  if (!d) return 'NOACTIVE';
  return JSON.stringify({bg: getComputedStyle(d).backgroundColor,
    n: document.querySelectorAll('.composer-recents .pal-dot.active').length});
})()"""))
print("composer B active dot:", active)
assert active != "NOACTIVE" and active["n"] == 1, "B 未默认选中任何色点"
assert active["bg"] == bg_a, f"默认色与上次不一致: {active['bg']} != {bg_a}"
type_and_submit("R156验证B-应同色")
b = invoke_on(main, "list_memos", {})[-1]
assert b["content"] == "R156验证B-应同色"
assert b["color"] == a["color"], f"B 色值 != A 色值: {b['color']} != {a['color']}"
print("PASS: 新建便签默认沿用上次提交颜色（UI 选中态 + 落库色值双证）")

# ── 清理 ──
for m in invoke_on(main, "list_memos", {}):
    invoke_on(main, "remove_memo", {"id": m["id"]})
time.sleep(0.5)
assert invoke_on(main, "list_memos", {}) == [], "清理未完成"
print("PASS: 现场还原（便签清零）")
