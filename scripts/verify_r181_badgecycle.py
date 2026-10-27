# 方向181 真机验证：托盘 ⌘N 序号徽章随 ↓ 翻页跟进（循环到新页前十行）
# 剧本（合成 ↓ 键 + DOM 断言；pageCount 会话态，结束由收尾重启自然复位）：
#   基线：徽章在第 0-9 行（⌘1..⌘0），行 10+ 无
#   → 合成 ↓×30（到底自动加载第二页）→ 徽章整体迁到第 30-39 行
#     且标签从 ⌘1 重新起算；原第 0-9 行徽章消失
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


def badges():
    out = tray.eval(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.po-row')].map(r => {
    const kbd = r.querySelector('.kbd');
    return {idx: r.dataset.idx, badge: kbd ? kbd.textContent.trim() : null};
  }).filter(x => x.badge)))()""")
    if not isinstance(out, str):
        raise RuntimeError("eval type")
    return json.loads(out)


b0 = badges()
print("baseline badges:", [(x["idx"], x["badge"]) for x in b0])
assert len(b0) == 10 and b0[0]["idx"] == "0", f"基线徽章异常: {b0[:3]}"
assert b0[9]["badge"].endswith("0"), "第 10 徽章应为 ⌘0"

# 合成 ↓×30：每次在页底触发自动加载（30 行/页）
for _ in range(30):
    tray.eval(r"""(() => {
      const i = document.querySelector('.po-search input, .po-search-box input, input');
      i.dispatchEvent(new KeyboardEvent('keydown',
        {key: 'ArrowDown', bubbles: true, cancelable: true}));
    })()""")
    time.sleep(0.04)
time.sleep(0.8)

b1 = badges()
print("after paging badges:", [(x["idx"], x["badge"]) for x in b1])
assert len(b1) == 10, f"徽章数异常: {len(b1)}"
idxs = sorted(int(x["idx"]) for x in b1)
assert idxs == list(range(30, 40)), f"徽章未迁至新页: {idxs}"
first = next(x for x in b1 if x["idx"] == "30")
last = next(x for x in b1 if x["idx"] == "39")
assert first["badge"].endswith("1") and last["badge"].endswith("0"), \
    f"循环起算错误: {first['badge']}..{last['badge']}"

rows = tray.eval("document.querySelectorAll('.po-row').length")
print("rows loaded:", rows)
assert int(rows) >= 60, f"翻页未加载: {rows}"
print("PASS: ↓ 到底自动翻页后 ⌘N 徽章循环到新页前 10 行（30-39，⌘1 重新起算）")
