# 方向168 真机验证：托盘行悬停 title 带条目字节数
# 剧本（DOM 断言 + 桥核对，只读无清理）：
#   取托盘前 5 行的 title 与桥 list_items 的 byte_size/note 对照
#   → 每行 title 均含 fmtBytes(byte_size) 的期望文本
#   → 有备注的行 title 为「备注 · 大小」，无备注行为「大小」
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
tray.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.6)


def fmt(n):
    if not n or n <= 0:
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


rows = json.loads(tray.eval(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.po-row')].slice(0, 5).map(r => ({
    title: r.getAttribute('title'),
    idx: r.dataset.idx,
  }))))()"""))
items = json.loads(main.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 30})).slice(0, 5)
    .map(x => ({bytes: x.byte_size, note: x.note ?? null}))))()"""))
print("rows:", rows)
print("items:", items)
assert len(rows) >= 3 and len(rows) == len(items), "行/条目对不齐"

for r, it in zip(rows, items):
    want_size = fmt(it["bytes"])
    assert want_size, f"条目 byte_size 异常: {it}"
    assert r["title"] and want_size in r["title"], f"title 缺大小: {r} want {want_size}"
    if it["note"]:
        assert r["title"].startswith(it["note"] + " · "), f"备注拼接异常: {r}"
    else:
        assert r["title"] == want_size, f"无备注行应为纯大小: {r}"

print("PASS: 托盘行 title 带字节数（备注行「备注 · 大小」，无备注行纯大小）")
