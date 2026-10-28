# 方向206 真机验证：设置页热键行前缀 1/2 数字徽章
# 剧本（只读 DOM 断言）：
#   打开设置页 → 热键区两行（唤起剪切板/截图）各带 .hk-order 徽章
#   → 文本按行序为 1、2；aria-hidden；非热键行（重检测等）无徽章
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and "view=settings" in t["url"])
st = CDP(ws_url)
st.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.2)

out = st.eval(r"""(() => JSON.stringify({
  badges: [...document.querySelectorAll('.hk-order')].map(b => ({
    text: b.textContent.trim(),
    hidden: b.getAttribute('aria-hidden'),
    inLabel: !!b.closest('.settings-label'),
  })),
  otherRows: [...document.querySelectorAll('.settings-row')]
    .filter(r => r.querySelector('.hotkey-badge'))
    .map(r => !!r.querySelector('.hk-order')),
}))()""")
if not isinstance(out, str):
    raise RuntimeError("type")
data = json.loads(out)
print("badges:", data["badges"])
print("hotkey rows with badge:", data["otherRows"])

assert len(data["badges"]) == 2, f"徽章数异常: {len(data['badges'])}"
assert [b["text"] for b in data["badges"]] == ["1", "2"], "序号不符"
assert all(b["hidden"] == "true" for b in data["badges"]), "aria-hidden 缺失"
assert all(b["inLabel"] for b in data["badges"]), "徽章不在 label 内"
assert all(has for has in data["otherRows"]), "存在无徽章的热键行"
print("PASS: 两热键行前缀 1/2 徽章在位（aria-hidden、位于 label 内、全行覆盖）")
