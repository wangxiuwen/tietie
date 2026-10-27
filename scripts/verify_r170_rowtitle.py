# 方向170 真机验证：Library 表格行悬停 title 显示完整预览（已具备收口轮）
# 实证（只读）：自方向123（13d2120）起 td.w-content 即带 title=content
#   （遮罩期抑制防悬停泄码），行文本截 80 字、title 承载全文。
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and "view=library" in t["url"])
lib = CDP(ws_url)
# 挂载缓存（R153 教训）：双戳刷新
lib.eval(r"""(async () => {
  await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 1});
  window.dispatchEvent(new Event('clipboard-changed'));
})()""")
time.sleep(0.8)

out = lib.eval(r"""(() => {
  const tds = [...document.querySelectorAll('td.w-content')];
  const long1 = tds.find(td => (td.getAttribute('title') || '').length > 80);
  return JSON.stringify({
    nRows: tds.length,
    longRow: long1 ? {
      titleLen: (long1.getAttribute('title') || '').length,
      shownLen: long1.querySelector('.lib-row-text').textContent.length,
    } : null,
    maskedTitleSuppressed: tds.every(td =>
      !(td.querySelector('.lib-masked') && td.getAttribute('title'))),
  });
})()""")
if not isinstance(out, str):
    raise RuntimeError("eval type")
data = json.loads(out)
print(data)
assert data["nRows"] > 0
if data["longRow"]:
    assert data["longRow"]["shownLen"] <= 80 < data["longRow"]["titleLen"], \
        "长行 title 未承载全文"
assert data["maskedTitleSuppressed"], "遮罩行 title 未抑制"
print("PASS: Library 行悬停 title 全文 + 遮罩抑制（方向123 起已具备，本轮实证）")
