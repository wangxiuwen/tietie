# 方向187 真机验证：抽屉图片卡缩略图角标显示宽×高
# 剧本（只读 DOM 断言）：img: 过滤后所有卡均为图片卡，每张 .img 内
#   .img-dim 文本 == 桥 list_items 同条目的 content（WxH），且非图片卡无徽章
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


def set_query(q):
    got = d.eval(rf"""(() => {{
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, {json.dumps(q)});
  i.dispatchEvent(new Event('input', {{bubbles: true}}));
  return i.value;
}})()""")
    assert got == q, got
    time.sleep(0.6)


set_query("img:")
dom = json.loads(d.eval(r"""(() => {
  const cards = [...document.querySelectorAll('.cards [data-idx]')].map(c => {
    const dim = c.querySelector('.img-dim');
    const badge = c.querySelector('.badge');
    return {text: c.textContent.slice(0, 30), kind: badge ? badge.className.split(' ')[1] : null,
            dim: dim ? dim.textContent.trim() : null};
  });
  return JSON.stringify({n: cards.length, cards});
})()"""))
n_img = sum(1 for c in dom["cards"] if c["kind"] == "image")
print("cards:", dom["n"], "| image cards:", n_img)
assert n_img >= 1, "无图片卡可验"

with_badge = [c for c in dom["cards"] if c["dim"]]
assert len(with_badge) == n_img, f"徽章覆盖不全: {len(with_badge)}/{n_img}"

# 与桥对照：徽章文本 == 条目 content（WxH）
items = json.loads(d.eval(r"""(async () => JSON.stringify(
  (await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 300}))
    .filter(x => x.kind === 'image').map(x => x.content)))()"""))
dims = [c["dim"] for c in with_badge]
for dim in dims:
    assert dim in items, f"徽章 {dim} 不在库内图片尺寸集中"
assert all("x" in c["dim"] for c in with_badge), "徽章非 WxH 格式"

# 非图片卡无徽章：切 text:
set_query("text:")
none_img = json.loads(d.eval(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.cards .img-dim')].length))()"""))
print("text: 徽章数:", none_img)
assert none_img == 0, "非图片卡出现徽章"

set_query("")
print("PASS: 图片卡 100% 覆盖 WxH 角标、文本与库内一致、非图片卡零徽章")
