# 方向163 真机验证：打开设置页自动刷新同步日志（已具备收口轮，自方向141 起）
# 剧本（产品路径造事件 + 合成 open_settings，结束删除探针条目）：
#   桥取 sync_events 基线 N0
#   → send_message 给 wsl-tietie（真实配对对端）→ 桥断言环 +1（⇨或⚠）
#   → 关掉设置窗再 open_settings（不碰手动刷新钮）
#     → 断言设置页 .sync-ev 行数 ≥1 且时间/对端呈现（=settings-open 自动拉了）
#   → delete_item 清理 💬 探针条目
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


def invoke_on(ws, cmd, args=None):
    out = ws.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} -> {type(out).__name__}")
    return json.loads(out)


PROBE = "R163-探针-自动刷新验证"
n0 = len(invoke_on(main, "sync_events", {}))
print("ring baseline:", n0)

r = invoke_on(main, "msg_send", {"instance": "wsl-tietie", "text": PROBE})
print("send_message:", r)
time.sleep(0.8)
ring = invoke_on(main, "sync_events", {})
print("ring now:", len(ring), "| last:", ring[-1] if ring else None)
assert len(ring) == n0 + 1, f"事件未入环: {len(ring)} != {n0 + 1}"

# 关设置窗 → 重新打开（settings-open 自动 reloadSyncLog，不点手动刷新）
st.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|hide"); })()')
time.sleep(0.5)
main.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.2)

rows = st.eval(r"""(() => JSON.stringify({
  n: document.querySelectorAll('.sync-evin, .sync-evout, .sync-evfail, [class*="sync-ev"]').length,
  empty: !!document.querySelector('.settings-tag.muted'),
  text: [...document.querySelectorAll('[class*="sync-ev"]')].slice(0, 2)
    .map(e => e.textContent.trim()).join(' // ')
}))()""")
print("settings DOM:", rows)
data = json.loads(rows)
assert data["n"] >= 1 and not data["empty"], "打开设置页未自动拉取同步日志"
assert "wsl-tietie" in data["text"], f"最新事件未呈现: {data['text']}"
print("PASS: open_settings → settings-open → 同步日志自动呈现最新事件（141 起已具备，本轮实证）")

# 清理 💬 探针条目（产品路径）
items = invoke_on(main, "list_items", {"limit": 10})
probe = next((x for x in items if x.get("content") == PROBE), None)
if probe:
    invoke_on(main, "delete_item", {"id": probe["id"]})
    print("probe item deleted")
print("done")
