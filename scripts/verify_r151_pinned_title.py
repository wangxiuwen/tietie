# 方向151 真机验证：托盘面板无置顶条目时「📌 置顶」区标题隐藏（零改动收口轮）
# 前提：DB 只读实查 pinned=1 条数为 0；应用以 CDP 9223 启动。
# 断言：
#   1) 托盘页不存在包含「置顶」的 .po-title（整块置顶 po-section 不渲染）
#   2) 「最近」标题仍在（列表本体正常，隐藏只针对置顶分区）
import sys
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
    ws = None
    for t in json.load(r):
        if t["type"] == "page" and "view=tray" in t["url"]:
            ws = CDP(t["webSocketDebuggerUrl"])
            break
assert ws, "tray target not found"
cdp = ws

js = r"""(() => {
  const titles = [...document.querySelectorAll('.po-title > span')].map(e => e.textContent.trim());
  const pinnedSection = [...document.querySelectorAll('.po-section')].filter(s =>
    s.querySelector('.po-title') && s.querySelector('.po-title').textContent.includes('置顶'));
  return JSON.stringify({titles, pinnedSections: pinnedSection.length,
    rows: document.querySelectorAll('.po-row').length});
})()"""
data = json.loads(cdp.eval(js))
print("titles =", data["titles"])
print("pinnedSections =", data["pinnedSections"], "| rows =", data["rows"])

has_pinned_title = any("置顶" in t for t in data["titles"])
has_recent_title = any("最近" in t for t in data["titles"])
assert not has_pinned_title, "FAIL: 无置顶条目但置顶区标题仍渲染"
assert data["pinnedSections"] == 0, "FAIL: 无置顶条目但置顶 po-section 仍渲染"
assert has_recent_title, "FAIL: 最近区标题也不见了（隐藏范围扩大误伤）"
assert data["rows"] > 0, "FAIL: 面板行数为 0，页面可能未加载"
print("PASS: 无置顶时置顶区整段不渲染（标题随之隐藏），最近区不受影响")
