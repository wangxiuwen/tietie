# 方向196 真机验证：托盘行截断时 title 补完整内容
# 剧本（只读 DOM 断言，无清理）：
#   遍历托盘可见行 → 行文本以 … 结尾（被截断）的行，
#   title 必须含完整原文（= 桥 list_items 同条目 rowText 源）；
#   未截断行 title 不附全文（仍为 备注·大小）
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

rows = json.loads(tray.eval(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.po-row')].slice(0, 20).map(r => ({
    idx: r.dataset.idx,
    text: r.querySelector('.po-text')?.textContent ?? '',
    title: r.title,
  }))))()"""))
items = json.loads(main.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 20}))
    .map(x => ({preview: x.preview, content: x.content, kind: x.kind}))))()"""))

truncated = [r for r in rows if r["text"].endswith("…")]
full_rows = [r for r in rows if not r["text"].endswith("…")]
print(f"rows={len(rows)} truncated={len(truncated)} full={len(full_rows)}")
assert len(truncated) >= 1, "现场无截断行（内容太短）——先长内容后重跑"

ok = 0
for r in truncated:
    # 找桥侧匹配条目（preview 前缀对齐）
    def flat(x):
        return " ".join((x or "").split())
    match = next((it for it in items
                  if flat(it["preview"])[:40] in r["text"]
                  or r["text"][:40] in flat(it["preview"])
                  or flat(it["content"])[:40] in r["text"]), None)
    if match is None:
        continue
    src = match["content"]
    assert src[:40] in r["title"] or (match["preview"] or "")[:40] in r["title"], \
        f"title 缺全文: idx={r['idx']} title={r['title'][:60]!r}"
    ok += 1
print(f"truncated rows verified: {ok}/{len(truncated)}")
assert ok >= 1, "无一行通过对照"

# 未截断行不含全文追加（title 结构仍是 备注·大小）
for r in full_rows[:5]:
    assert not r["title"] or "·" in r["title"] or len(r["title"]) < 30, \
        f"未截断行 title 异常长: {r['title'][:60]!r}"
print("PASS: 截断行 title 含完整原文，未截断行保持 备注·大小 结构")
