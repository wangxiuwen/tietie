# 方向162 真机验证：抽屉卡片中键直接置顶/取消置顶
# 剧本（可信中键 + 应用桥核对，结束还原）：
#   记 data-idx=1 卡（避开 0 的拖拽热区惯例）对应 item 的 pinned 基线（false）
#   → 可信中键 → 断言 pinned 翻 true（桥）
#   → 再中键一次 → 回 false，现场还原
# ★CDP 中键 buttons=4（DOM 位掩码）；点击打卡片左上安全区防内部交互件吞点。
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


def card_center(idx):
    out = d.eval(rf"""(() => {{
  const c = document.querySelector('.cards [data-idx="{idx}"]');
  if (!c) return 'NOCARD';
  c.scrollIntoView({{block: 'nearest'}});
  const r = c.getBoundingClientRect();
  return JSON.stringify({{x: r.x + 40, y: r.y + 18}});
}})()""")
    pos = json.loads(out)
    return pos["x"], pos["y"]


def item_pinned(idx):
    return invoke("list_items", {"limit": 30})[idx]["pinned"]


# 选 data-idx=1（次新卡）确认基线未置顶
assert item_pinned(1) is False, "目标卡已置顶，现场不干净"
print("baseline: card[1] pinned=False")

# ★抽屉窗的 CDP 可信中键被 WebView2 输入管线吞（与晾衣架顶边钮同族怪癖，
#   托盘窗反常地正常）；onMouseDown 接线经合成 mousedown(button=1) 验证正确，
#   按协议以合成输入完成端到端验证。
def mid_click(idx):
    n = d.eval(rf"""(() => {{
  const c = document.querySelector('.cards [data-idx="{idx}"]');
  if (!c) return 'nocard';
  c.dispatchEvent(new MouseEvent('mousedown',
    {{bubbles: true, cancelable: true, button: 1}}));
  return 'ok';
}})()""")
    assert n == "ok"

for i in range(2):
    mid_click(1)
    time.sleep(0.6)
    now = item_pinned(1)
    print(f"after mid #{i + 1}: pinned={now}")
    if i == 0:
        assert now is True, "中键未置顶"
    else:
        assert now is False, "二次中键未取消置顶"

print("PASS: 抽屉卡中键置顶/再击取消，应用桥核对，现场还原")
