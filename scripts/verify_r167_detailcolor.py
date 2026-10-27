# 方向167 真机验证：详情视图数字键 1-8 直接换色（不再要求色板悬停）
# 剧本（合成开详情 + 可信数字键 + 桥核对，结束清理）：
#   挂 1 条（accent 蓝）→ 双击挂卡开详情（不悬停色板）
#   → 可信按 "3" → 色板序 [#0078d4,#007aff,#34c759,...] 第 3 = #34c759
#   → 断言 memo.color==#34c759 且 active 色点同步
#   → 聚焦备注输入框再按 "5" → 色不变（打字守卫）
#   → Esc 关详情、remove_memo 清理
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


def key(ws, k, code, vk, mods=0):
    ws.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchKeyEvent", "params": {
        "type": "keyDown", "modifiers": mods, "key": k, "code": code,
        "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}}))
    ws.ws.recv_text()
    ws.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchKeyEvent", "params": {
        "type": "keyUp", "modifiers": 0, "key": k, "code": code,
        "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}}))
    ws.ws.recv_text()
    time.sleep(0.15)


# 开局清场：关残留详情浮层（浮层在时挂卡不渲染）+ 清残留便签
key(line, "Escape", "Escape", 27)
time.sleep(0.3)
for m in invoke_on(main, "list_memos", {}):
    invoke_on(main, "remove_memo", {"id": m["id"]})
time.sleep(0.4)
assert invoke_on(main, "list_memos", {}) == [], "基线便签非空"
first = invoke_on(main, "list_items", {"limit": 10})[0]["id"]
assert invoke_on(main, "hang_items", {"ids": [first]}) == 1
time.sleep(0.5)
memo = invoke_on(main, "list_memos", {})[0]
print("memo color:", memo["color"])

line.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.5)
n = line.eval(r"""(() => {
  const c = document.querySelector('.line-card:not(.composer)');
  if (!c) return 'nocard';
  c.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
  return 'ok';
})()""")
assert n == "ok", n
time.sleep(0.6)
assert str(line.eval("document.querySelector('.line-detail') ? 1 : 0")) in ("1", 1), "详情未打开"
print("detail open ✓（未悬停色板）")
# 双击开的详情自带编辑态（textarea 聚焦、色板不渲染）——点「取消编辑」退出，
# 顺带早前的失败恰好证明打字守卫在编辑态正确拦截数字键
n = line.eval(r"""(() => {
  const b = [...document.querySelectorAll('.line-detail .btn.ghost')]
    .find(x => x.textContent.includes('取消'));
  if (!b) return 'nobtn';
  b.click();
  return 'ok';
})()""")
assert n == "ok", n
time.sleep(0.5)
assert str(line.eval("document.querySelectorAll('.line-detail .pal-dot').length > 0 ? 1 : 0")) in ("1", 1),     "退出编辑后色板未渲染"
line.eval(r"""(() => { const el = document.activeElement; if (el && el.blur) el.blur(); })()""")
time.sleep(0.2)

# 可信数字键 3 → paletteColors[2] = #34c759
key(line, "3", "Digit3", 51)
time.sleep(0.6)
now = invoke_on(main, "list_memos", {})[0]
print("after key3 color:", now["color"])
assert now["color"] == "#34c759", f"换色失败: {now['color']}"
active = line.eval(r"""(() => {
  const d = document.querySelector('.line-detail .pal-dot.active');
  return d ? getComputedStyle(d).backgroundColor : null;
})()""")
print("active dot:", active)
assert active == "rgb(52, 199, 89)", f"active 色点未同步: {active}"

# 打字守卫：聚焦备注输入框后按 5，色不变
focused = line.eval(r"""(() => {
  const inp = document.querySelector('.line-detail input');
  if (!inp) return 'noinput';
  inp.focus();
  return 'ok';
})()""")
assert focused == 'ok', f"备注输入框不在: {focused}"
time.sleep(0.3)
key(line, "5", "Digit5", 53)
time.sleep(0.5)
after = invoke_on(main, "list_memos", {})[0]
print("after key5-in-input color:", after["color"])
assert after["color"] == "#34c759", "打字守卫失效（输入框内数字键仍换色）"

# Esc 关详情 + 清理
key(line, "Escape", "Escape", 27)
time.sleep(0.4)
invoke_on(main, "remove_memo", {"id": memo["id"]})
time.sleep(0.4)
assert invoke_on(main, "list_memos", {}) == []
print("PASS: 详情数字键换色（免悬停）、active 同步、输入框守卫、清理还原")
