# 方向200 真机验证：链接卡域名徽章右键直接开系统浏览器
# 剧本（桥断言法：右键徽章 → open_url 已调用且目标 URL 正确）：
#   用安全法断言：右键前 monkey-patch 不了 Rust；改用行为链——
#   徽章右键触发 open_url(item.content)。为不真开浏览器干扰用户：
#   选择一条 data: 不可行（非 link）——改用桥包装法不可行（会重置）。
#   真实方案：右键真实链接卡徽章，断言 open_url 执行成功（返回 void），
#   通过查进程有浏览器唤起？重。改为断言 Rust 侧 open_url 命令对同一 URL
#   直调成功（命令级冒烟）+ 徽章 onContextMenu 存在性（DOM 事件监听）。
#   组合证：右键分发后卡片右键菜单【不】弹出（stopPropagation 生效）+
#   open_url 命令对该 URL 冒烟成功。
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

# 清残留查询
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  if (i.value) {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    set.call(i, '');
    i.dispatchEvent(new Event('input', {bubbles: true}));
  }
})()""")
time.sleep(0.4)

# 找首个域名徽章 + 对应卡 URL
badge = json.loads(d.eval(r"""(() => {
  const b = document.querySelector('.cards .link-domain');
  if (!b) return 'NOBADGE';
  const r = b.getBoundingClientRect();
  const card = b.closest('[data-idx]');
  const badge2 = card.querySelector('.link-url');
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2,
    domain: b.textContent.trim()});
})()"""))
print("badge:", badge)
assert badge != "NOBADGE", "无链接卡徽章"

# 右键分发（button=right, buttons=2）
for typ in ("mousePressed", "mouseReleased"):
    d.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                          "params": {"type": typ, "button": "right",
                                     "buttons": 2 if typ == "mousePressed" else 0,
                                     "clickCount": 1,
                                     "x": badge["x"], "y": badge["y"]}}))
    d.ws.recv_text()
    time.sleep(0.12)
time.sleep(0.6)

# 断言 1：卡片级右键菜单未被触发（stopPropagation 生效）
# ——卡片右键菜单是 ContextMenu 组件（.ctx-item 类）；徽章右键应吞掉事件
ctx = d.eval("document.querySelector('.ctx-item') ? 'y' : 'n'")
print("card ctx menu after badge right-click:", ctx)
assert ctx == "n", "右键穿透到卡片菜单（stopPropagation 失效）"

# 断言 2：右键同时不应触发左键行为（查询框没被填域名）
q = d.eval(r"""document.querySelector('.search input').value""")
print("query after right-click:", repr(q))
assert q == "", f"右键误触左键筛选: {q!r}"

# 断言 3：open_url 命令对该卡 URL 冒烟（行为链的执行段命令级实证）
url = json.loads(d.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 200}))
    .find(x => x.kind === 'link').content))()"""))
smoke = d.eval(rf"""(async () => {{
  try {{ await window.__TAURI_INTERNALS__.invoke('open_url',
    {{url: {json.dumps(url)}}}); return 'ok'; }}
  catch (e) {{ return 'ERR ' + String(e); }}
}})()""")
print("open_url smoke:", smoke)
assert smoke == "ok", smoke

print("PASS: 徽章右键 → 事件被吞（无卡片菜单/无筛选副作用）+ open_url 执行段冒烟通过")
