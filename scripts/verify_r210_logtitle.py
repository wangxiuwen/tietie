# 方向210 真机验证：同步日志行悬停 title 含完整日期
# 剧本（产品路径造事件 + DOM 断言）：
#   msg_send 造 unreachable 事件（~16s）→ 设置页日志行 title
#   断言：title 两行——首行过滤提示（184 原文）+ 次行完整日期
#   toLocaleString（含年月日，与行内 toLocaleTimeString 的 ts 一致）
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


main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))
st = CDP(page_ws(lambda u: "view=settings" in u))

# 事件环空则造一条
n = main.eval(r"""(async () => (await window.__TAURI_INTERNALS__.invoke('sync_events')).length)()""")
if int(n) == 0:
    main.eval(r"""(async () => {
      try { await window.__TAURI_INTERNALS__.invoke('msg_send',
        {instance: 'wsl-tietie', text: 'R210探针'}); } catch (e) {}
    })()""")
    print("waiting for unreachable timeout (~16s) ...")
    for _ in range(12):
        time.sleep(2)
        c = main.eval(r"""(async () => (await window.__TAURI_INTERNALS__.invoke('sync_events')).length)()""")
        if int(c) > 0:
            break

ring = json.loads(main.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('sync_events')).slice(-1)))()"""))
ev = ring[0]
print("last event ts:", ev["ts"])

main.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.2)

row = json.loads(st.eval(r"""(() => {
  const rows = [...document.querySelectorAll('button.sync-ev')];
  const row = rows[0];
  if (!row) return 'NOROW';
  return JSON.stringify({title: row.title, text: row.textContent.trim().slice(0, 30)});
})()"""))
print("row:", row)
assert row != "NOROW", "无日志行"

title = row["title"]
lines = title.split("\n")
print("title lines:", lines)
assert len(lines) == 2, f"title 非两行: {title!r}"
assert "过滤" in lines[0] or "filter" in lines[0].lower(), f"首行缺过滤提示: {lines[0]!r}"
# 完整日期：含年（toLocaleString 含 / 或 - 分隔的年月日）
full = lines[1]
assert any(ch.isdigit() for ch in full) and ("/" in full or "-" in full or "." in full), \
    f"次行非完整日期: {full!r}"
# 与行内时间同源：重建 toLocaleString 包含行内时分秒的前缀
row_time = row["text"].split(" ")[0]  # e.g. "20:47:07"
assert row_time in full, f"行内时间 {row_time} 不在完整日期内: {full!r}"
print("PASS: title 两行=过滤提示+完整日期，且与行内时间同源一致")
