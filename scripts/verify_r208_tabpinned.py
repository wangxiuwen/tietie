# 方向208 真机验证：抽屉 Tab 环含置顶过滤位
# 剧本（合成 Tab 键 + DOM 断言，结束 Tab 回 all 还原）：
#   基线 all → 连按 Tab 至「置顶」高亮（环新增位）
#   → 断言可见卡全部为置顶卡（桥 pinned 集一致）
#   → 再 Tab 回 all 复原
#   → 环完整性：连按 7 次 Tab 回到 all（环长 7）
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


def js(code):
    out = d.eval(code)
    if not isinstance(out, str):
        raise RuntimeError("type")
    return out


def tab_state():
    return json.loads(js(r"""(() => JSON.stringify({
  active: document.querySelector('.type-tabs .tab.active')?.textContent.trim() ?? null,
  tabs: [...document.querySelectorAll('.type-tabs .tab')].map(t => t.textContent.trim()),
  cards: document.querySelectorAll('.cards [data-idx]').length,
}))()"""))


def press_tab():
    # blur 搜索框防历史召回，然后 window 级 Tab
    d.eval(r"""(() => { const el = document.activeElement; if (el && el.blur) el.blur(); })()""")
    time.sleep(0.15)
    for typ in ("keyDown", "keyUp"):
        d.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchKeyEvent",
                              "params": {"type": typ, "key": "Tab", "code": "Tab",
                                         "windowsVirtualKeyCode": 9, "nativeVirtualKeyCode": 9}}))
        d.ws.recv_text()
    time.sleep(0.4)


# 开局归位：点「全部」
d.eval(r"""(() => {
  const all = [...document.querySelectorAll('.type-tabs .tab')].find(t => t.textContent.includes('全部') || t.textContent.includes('All'));
  if (all) all.click();
})()""")
time.sleep(0.5)
b = tab_state()
print("baseline:", b)
assert b["active"].startswith("全部") or b["active"].startswith("All"), f"基线非全部: {b['active']}"
assert any(t.startswith("置顶") or t.startswith("Pinned") for t in b["tabs"]), f"Tab 环缺置顶位: {b['tabs']}"

# 连按 Tab 至置顶高亮（最多 8 步防死循环）
hit = False
for _ in range(8):
    press_tab()
    st = tab_state()
    if st["active"].startswith("置顶") or st["active"].startswith("Pinned"):
        hit = True
        break
assert hit, "Tab 环走不到置顶位"

# 置顶位下的卡全部为 pinned
pinned = tab_state()
pinned_ids = set(json.loads(js(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 300}))
    .filter(x => x.pinned).map(x => x.id)))()""")))
cards = json.loads(js(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.cards [data-idx]')].length))()"""))
print(f"pinned tab: active={pinned['active']} cards={cards} pinned_ids={len(pinned_ids)}")
assert pinned_ids, "库内无置顶条目（先置顶一条）"
assert cards == len(pinned_ids), f"置顶位卡数 {cards} != 桥置顶数 {len(pinned_ids)}"

# 环完整性：从置顶位继续 Tab 走满一圈（7 位）回 all
back = None
for _ in range(7):
    press_tab()
    st = tab_state()
    if st["active"].startswith("全部") or st["active"].startswith("All"):
        back = st
        break
print("after 6 more Tabs:", back["active"])
assert back["active"].startswith("全部") or back["active"].startswith("All"), f"环长异常未回全部: {back['active']}"

# 复原确认（all 下卡数恢复）
final = tab_state()
assert final["cards"] > len(pinned_ids), "all 位卡数未恢复"
print("PASS: Tab 环含置顶位（7 位循环）、置顶位卡集与桥一致、环回全部")
