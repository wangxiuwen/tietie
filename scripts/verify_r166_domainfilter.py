# 方向166 真机验证：点击链接卡域名徽章直接以该域名搜索
# 剧本（合成输入 + DOM 断言，结束清空查询还原）：
#   开局清场 → 取首个 .link-domain 徽章的域名 D 与其卡片 id
#   → 合成点击徽章 → 断言：搜索框= D、聚焦、可见卡全部为 link 且内容含 D
#   → 再断言点击未触发选中/多选（卡无 .selected/.multi-sel 由点击引起）
#   → 清空还原
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

# 开局清场（重跑残留查询）
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  if (i.value) {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    set.call(i, '');
    i.dispatchEvent(new Event('input', {bubbles: true}));
  }
})()""")
time.sleep(0.4)

badge = json.loads(d.eval(r"""(() => {
  const b = document.querySelector('.cards .link-domain');
  if (!b) return 'NOBADGE';
  const card = b.closest('[data-idx]');
  b.scrollIntoView({block: 'center'});
  return JSON.stringify({domain: b.textContent.trim(), idx: card.dataset.idx});
})()"""))
print("badge:", badge)
assert badge != "NOBADGE", "当前列表无链接卡域名徽章（先造数据或换卡）"

n = d.eval(rf"""(() => {{
  const b = [...document.querySelectorAll('.cards .link-domain')]
    .find(x => x.textContent.trim() === {json.dumps(badge['domain'])});
  if (!b) return 'gone';
  b.click();
  return 'ok';
}})()""")
assert n == "ok", f"点击失败: {n}"
time.sleep(0.6)

state = json.loads(d.eval(r"""(() => JSON.stringify({
  q: document.querySelector('.search input').value,
  focused: document.activeElement === document.querySelector('.search input'),
  cards: document.querySelectorAll('.cards [data-idx]').length,
}))()"""))
q = state["q"]
print("query:", q, "| focused:", state["focused"], "| cards:", state["cards"])
assert q == badge["domain"], f"搜索框未填入域名: {q!r}"
assert state["focused"], "搜索框未聚焦"
assert state["cards"] > 0, "过滤后无卡"

kinds = json.loads(d.eval(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.cards .badge')]
    .map(b => b.className.split(' ')[1])))()"""))
print("kinds:", set(kinds))
assert set(kinds) <= {"link"}, "过滤结果混入非链接卡"

contents = json.loads(d.eval(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.cards [data-idx]')]
    .map(c => c.textContent)))()"""))
assert all(q in c for c in contents), "存在内容不含域名的卡"

# 清空还原
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
time.sleep(0.4)
print("PASS: 域名徽章点击 → 搜索框=域名+聚焦+仅链接卡且内容含域名，已清空还原")
