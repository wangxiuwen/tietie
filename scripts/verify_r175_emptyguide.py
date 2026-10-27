# 方向175 真机验证：晾衣架空态引导（拖卡提示 + 行内新建入口）
# 剧本（基线本就 0 便签；结束只关 composer 不留数据）：
#   断言 .line-empty 文案含拖卡引导 + .line-empty-new 在位
#   → 合成点击新建链接 → composer 打开（textarea 在）
#   → Esc 关闭 composer，现场还原（便签数仍 0）
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and "view=line" in t["url"])
line = CDP(ws_url)
main_ws = None
with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    main_ws = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                   if t["type"] == "page" and (t["url"].endswith("/") or "view=" not in t["url"]))
main = CDP(main_ws)


def js(code):
    out = line.eval(code)
    if not isinstance(out, str):
        raise RuntimeError("eval type")
    return out


n_memos = main.eval(r"""(async () => (await window.__TAURI_INTERNALS__.invoke('list_memos')).length)()""")
assert str(n_memos) == "0", f"基线便签非空: {n_memos}"

line.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.6)

state = json.loads(js(r"""(() => JSON.stringify({
  emptyText: document.querySelector('.line-empty')?.textContent.trim() ?? null,
  hasNew: !!document.querySelector('.line-empty-new'),
  newText: document.querySelector('.line-empty-new')?.textContent.trim() ?? null,
}))()"""))
print("empty state:", state)
assert state["emptyText"] and "拖" in state["emptyText"] and "抽屉" in state["emptyText"], \
    "拖卡引导缺失"
assert state["hasNew"] and state["newText"] == "或点这里新建一张", "新建入口缺失"

# 合成点击新建 → composer 打开
n = js(r"""(() => {
  const b = document.querySelector('.line-empty-new');
  if (!b) return 'nobtn';
  b.click();
  return 'ok';
})()""")
assert n == "ok"
time.sleep(0.5)
composer = js("document.querySelector('.line-card.composer textarea') ? 'y' : 'n'")
print("composer after click:", composer)
assert composer == "y", "新建链接未打开 composer"

# Esc 关闭还原
line.eval(r"""(() => {
  const ta = document.querySelector('.line-card.composer textarea');
  ta.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
})()""")
time.sleep(0.4)
closed = js("document.querySelector('.line-card.composer') ? 'n' : 'y'")
assert closed == "y", "composer 未关闭"
after = main.eval(r"""(async () => (await window.__TAURI_INTERNALS__.invoke('list_memos')).length)()""")
assert str(after) == "0"
print("PASS: 空态双引导（拖卡文案+行内新建入口）、点击开 composer、Esc 还原零残留")
