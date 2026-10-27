# 方向177 真机验证：抽屉列表按天分组插日期分隔行
# 剧本（只读 DOM 断言 + 桥数据对照）：
#   桥取 list_items(30) 按 used_at 本地日计算期望分组数
#   → DOM .day-sep 数量 == 相邻跨日次数；分隔行无 data-idx；卡片数不减
#   → 每条分隔行文本 == 其后首卡的 dayLabel（今天/昨天/M/D）
#   → 顶部第一条分隔前的卡（首组）无分隔行（列表开头干净）
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


def day_of(ts):
    dd = time.localtime(ts)
    return f"{dd.tm_year}-{dd.tm_mon}-{dd.tm_mday}"


def day_label(ts):
    dd = time.localtime(ts)
    n = time.localtime()
    y = time.localtime(time.time() - 86400)
    if day_of(ts) == day_of(time.time()):
        return "今天"
    if day_of(ts) == f"{y.tm_year}-{y.tm_mon}-{y.tm_mday}":
        return "昨天"
    return f"{dd.tm_mon}/{dd.tm_mday}"


items = json.loads(d.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 200}))
    .map(x => ({id: x.id, used_at: x.used_at, pinned: x.pinned}))))()"""))
print("items:", len(items))
# 抽屉渲染全量 items（不只 30），对照口径一致

dom = json.loads(d.eval(r"""(() => {
  const cards = [...document.querySelectorAll('.cards > *')];
  return JSON.stringify({
    children: cards.length,
    seps: [...document.querySelectorAll('.day-sep')].map(e => ({
      text: e.textContent.trim(), hasIdx: e.hasAttribute('data-idx')})),
    cardNodes: document.querySelectorAll('.cards [data-idx]').length,
  });
})()"""))
print("seps:", [s["text"] for s in dom["seps"]], "| card nodes:", dom["cardNodes"])

# 期望：按 used_at 相邻跨日次数（列表渲染顺序 = list_items 返回序）
expect_days = []
for i in range(1, len(items)):
    if day_of(items[i]["used_at"]) != day_of(items[i - 1]["used_at"]):
        expect_days.append(day_label(items[i]["used_at"]))
print("expect:", expect_days)
assert len(dom["seps"]) == len(expect_days), \
    f"分隔数 {len(dom['seps'])} != 期望 {len(expect_days)}"
got_texts = [s["text"] for s in dom["seps"]]
assert got_texts == expect_days, f"分隔文案/顺序不符: {got_texts} != {expect_days}"
assert all(not s["hasIdx"] for s in dom["seps"]), "分隔行带 data-idx（污染选择序）"
assert dom["cardNodes"] == len(items), f"卡片数 {dom['cardNodes']} != {len(items)}"

# 分隔行位置：每条 .day-sep 的下一个兄弟必须是卡（其 used_at 属于该天）
ok = d.eval(r"""(() => {
  const seps = [...document.querySelectorAll('.day-sep')];
  return seps.every(s => s.nextElementSibling &&
    (s.nextElementSibling.hasAttribute('data-idx') ||
     s.nextElementSibling.querySelector('[data-idx]'))) ? 'y' : 'n';
})()""")
assert ok == "y", "存在分隔行不紧邻卡片的错位"
print("PASS: 按天分隔行数量/文案/顺序/无 data-idx/卡片数全对，紧邻其后卡片")
