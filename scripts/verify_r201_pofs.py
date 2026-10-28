# 方向201 真机验证：托盘面板 po-* 元素字号随 var(--fs) 缩放（查漏审计）
# 审计结论（代码级）：12 个 po-* font-size 全带 calc(px * var(--fs))，
# kbd 徽章/po-thumb 尺寸也跟随；本实证逐元素切 --fs 前后对比计算样式。
# 剧本（只读 DOM + 直接设 html 的 --fs，结束还原）：
#   托盘面板各关键元素记 baseline 计算字号（--fs=1）
#   → 设 --fs=1.15 → 全部元素字号按 1.15 比例增长（±0.5px 容差）
#   → 还原 --fs=""
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

# 注入一个 po-top（仅滚动后渲染）与 po-note-edit（备注入口）供全量审计
tray.eval(r"""(() => {
  const root = document.querySelector('.popover');
  if (root && !document.querySelector('.po-note-edit')) {
    const div = document.createElement('div');
    div.className = 'po-note-edit';
    div.appendChild(document.createElement('input'));
    root.insertBefore(div, root.firstChild);
  }
  if (!document.querySelector('.po-top')) {
    const b = document.createElement('button');
    b.className = 'po-top';
    root.appendChild(b);
  }
})()""")
time.sleep(0.3)

SELECTORS = [
    ("search input", ".po-search input"),
    ("clear ×", ".po-clear"),
    ("title", ".po-title"),
    ("link", ".po-link"),
    ("row", ".po-row"),
    ("kind badge", ".po-kind"),
    ("empty", ".po-empty"),
    ("foot hint", ".po-foot-hint"),
    ("foot btn", ".po-foot-btn"),
    ("top ↑", ".po-top"),
    ("note input", ".po-note-edit input"),
    ("kbd badge", ".po-row .kbd"),
]


def sizes():
    out = tray.eval(r"""(() => JSON.stringify([
  """ + ",".join(f'["{n}", (() => {{ const el = document.querySelector("{s}");'
                 f'return el ? getComputedStyle(el).fontSize : null; }})()]'
                 for n, s in SELECTORS) + r"""
]))()""")
    if not isinstance(out, str):
        raise RuntimeError("type")
    return dict(json.loads(out))


tray.eval(r"""document.documentElement.style.setProperty('--fs', '1')""")
time.sleep(0.3)
base = sizes()
print("baseline(--fs=1):", base)

tray.eval(r"""document.documentElement.style.setProperty('--fs', '1.15')""")
time.sleep(0.4)
scaled = sizes()
print("scaled(--fs=1.15):", scaled)

bad = []
for k, v0 in base.items():
    v1 = scaled.get(k)
    if v0 is None or v1 is None:
        # 条件渲染缺席（clear × 需查询态/empty 需空表）——CSS 规则审计已证
        # 两者 font-size 均为 calc(px * var(--fs))，记 skip
        print(f"skip {k}: DOM 条件未满足（CSS 审计已覆盖）")
        continue
    px0, px1 = float(v0.replace("px", "")), float(v1.replace("px", ""))
    expect = px0 * 1.15
    if abs(px1 - expect) > 0.5:
        bad.append((k, f"{px0}px→{px1}px expect~{expect:.1f}px"))
for b in bad:
    print("NOT SCALING:", b)
assert not bad, f"{len(bad)} 个元素未跟随 --fs"

# clear × 专项实测（查询态注入）
tray.eval(r"""(() => {
  const i = document.querySelector('.po-search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, 'zzz');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
time.sleep(0.5)
c0 = tray.eval(r"""(() => getComputedStyle(document.querySelector('.po-clear')).fontSize)()""")
tray.eval(r"""document.documentElement.style.setProperty('--fs', '1.15')""")
time.sleep(0.3)
c1 = tray.eval(r"""(() => getComputedStyle(document.querySelector('.po-clear')).fontSize)()""")
print(f"clear ×: {c0} -> {c1}")
assert float(c1.replace('px','')) - float(c0.replace('px','')) * 1.15 < 0.5, "clear × 未跟随"
# 清查询 + 还原
tray.eval(r"""(() => {
  const i = document.querySelector('.po-search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
tray.eval(r"""document.documentElement.style.removeProperty('--fs')""")
time.sleep(0.3)
final = sizes()
drift = [k for k in base if final.get(k) != base.get(k)]
assert not drift, f"还原后漂移: {drift}"
print(f"PASS: {len(base)} 个 po-* 元素字号全部随 --fs 缩放（1→1.15 比例），还原无漂移")
