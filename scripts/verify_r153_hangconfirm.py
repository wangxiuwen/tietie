# 方向153 真机验证：抽屉多选 >5 条时批量挂绳需两段式确认
# 剧本（全程走应用自己的 UI，验证后把挂出的便签全部摘掉还原）：
#   Ctrl+可信点击 6 张文本卡 → 批量栏「已选 6」
#   → 点「批量挂绳」→ 按钮变红色「确认挂绳？」且便签数未增加（未执行）
#   → 等 3.2s 超时 → 按钮回「批量挂绳」（解除）
#   → 再点两段确认 → 批量栏消失、便签 +6
#   → remove_memo 清理新增 6 条、复核计数回基线
# ★坑（R158）：坐标必须 pos["x"] 下标取；JS 三元返回数字要 str()；折叠线下先 scrollIntoView。
# ★坑（R159）：sqlite3 只读开 file: URI 看不到 WAL 里应用刚写的数据（读到旧快照）——
#   计数一律走应用桥 list_memos；memo 内容字段名是 content 不是 text。
import json
import sys
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and t["url"].endswith("localhost/"))
d = CDP(ws_url)


def memo_count():
    """count via the app bridge — sqlite3 read-only misses fresh WAL data"""
    n = d.eval(r"""(async () => (await window.__TAURI_INTERNALS__.invoke('list_memos')).length)()""")
    return int(n)


def click(sel_center, mods=0):
    """trusted click at pre-measured (x, y); mods: CDP bitmask (Ctrl=2)."""
    x, y = sel_center["x"], sel_center["y"]
    for typ in ("mousePressed", "mouseReleased"):
        d.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                              "params": {"type": typ, "button": "left",
                                         "buttons": 1 if typ == "mousePressed" else 0,
                                         "clickCount": 1, "modifiers": mods,
                                         "x": x, "y": y}}))
        d.ws.recv_text()
        time.sleep(0.12)


def center(js):
    out = d.eval(js)
    if not isinstance(out, str):
        raise RuntimeError(f"eval returned {type(out).__name__}")
    pos = json.loads(out)
    return {"x": pos["x"], "y": pos["y"]}


CARD_CENTER = r"""(() => {{
  const c = document.querySelector('.cards [data-idx="{i}"]');
  if (!c) return 'NOCARD';
  c.scrollIntoView({{block: 'nearest'}});
  const r = c.getBoundingClientRect();
  // top-left safe zone: card-middle hits interactive children (🔗 copy …)
  return JSON.stringify({{x: r.x + 24, y: r.y + 14}});
}})()"""

HANG_BTN = r"""(() => {
  const bar = document.querySelector('.batch-bar');
  if (!bar) return 'NOBAR';
  const b = [...bar.querySelectorAll('button')].find(x => x.textContent.includes('挂绳'));
  if (!b) return 'NOBTN';
  b.scrollIntoView({block: 'center'});
  const r = b.getBoundingClientRect();
  return JSON.stringify({label: b.textContent.trim(), cls: b.className,
    x: r.x + r.width / 2, y: r.y + r.height / 2,
    selText: bar.querySelector('span')?.textContent.trim()});
})()"""

base = memo_count()
print("memo baseline:", base)

# 需要抽屉可见：挂出前先确保窗口显示，并清掉可能残留的多选
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)
d.eval(r"""(() => {
  const bar = document.querySelector('.batch-bar');
  const clear = bar && [...bar.querySelectorAll('button')].find(b =>
    b.textContent.includes('取消选择'));
  if (clear) clear.click();
})()""")
time.sleep(0.4)

items = d.eval(r"""(async () => {
  const is = await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 40});
  const texts = is.filter(x => x.kind === 'text').slice(0, 6).map(x => x.content);
  return JSON.stringify(texts);
})()""")
contents = json.loads(items)
print("first-6 text contents:", [c[:18] for c in contents])
assert len(contents) == 6, "文本条目不足 6 条"

# Ctrl+click 多选 6 张卡（data-idx 0..5 即前 6 张卡）
for i in range(6):
    click(center(CARD_CENTER.format(i=i)), mods=2)
    time.sleep(0.15)
bar = json.loads(d.eval(HANG_BTN))
print("bar:", bar)
assert "6" in bar["selText"], f"多选未到 6: {bar['selText']}"
assert bar["label"] == "批量挂绳" and "arm" not in bar["cls"], "初始按钮态异常"

# 第一次点击 → 应进入 armed 确认态且不执行
click({"x": bar["x"], "y": bar["y"]})
time.sleep(0.5)
armed = json.loads(d.eval(HANG_BTN))
print("armed:", armed)
assert armed["label"] == "确认挂绳？" and "arm" in armed["cls"], "未进入两段确认态"
assert memo_count() == base, "确认前就执行了挂绳！"

# 3s 超时自动解除
time.sleep(3.4)
timed = json.loads(d.eval(HANG_BTN))
print("after timeout:", timed["label"])
assert timed["label"] == "批量挂绳" and "arm" not in timed["cls"], "超时未解除确认态"

# 两段确认执行
click({"x": timed["x"], "y": timed["y"]})
time.sleep(0.4)
armed2 = json.loads(d.eval(HANG_BTN))
click({"x": armed2["x"], "y": armed2["y"]})
time.sleep(1.0)
assert memo_count() == base + 6, f"确认后便签数异常: {memo_count()} != {base + 6}"
print("PASS: >5 条挂绳两段确认（armed 不执行、超时解除、确认后 +6）")

# 清理：按内容匹配 remove_memo 这 6 条
memos = json.loads(d.eval(r"""(async () => {
  const ms = await window.__TAURI_INTERNALS__.invoke('list_memos');
  return JSON.stringify(ms.map(m => ({id: m.id, content: m.content})));
})()"""))
new_ids = [m["id"] for m in memos if any(m["content"] == c for c in contents)]
print("new memo ids:", new_ids)
assert len(new_ids) == 6, f"按内容定位新增便签失败: {len(new_ids)}"
for mid in new_ids:
    d.eval(f'(async () => window.__TAURI_INTERNALS__.invoke("remove_memo", {{id: {mid}}}))()')
time.sleep(0.8)
assert memo_count() == base, f"清理后计数未回基线: {memo_count()}"
print("PASS: 清理完成，便签计数回到基线", base)
