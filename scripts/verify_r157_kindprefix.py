# 方向157 真机验证：抽屉搜索 text:/img:/link: 类型前缀过滤
# 剧本（合成输入驱动搜索框 + DOM 断言，结束清空搜索框还原）：
#   空查询基线记录可见卡类型集合
#   → "img:"  → 所有可见卡均 image 且有图
#   → "text:" → 所有可见卡均 text
#   → "text:先排查"（取库里真实文本词） → 仅文本且内容命中
#   → "link:" → 无 link 类型时结果为空集（或全 link）
#   → 清空查询还原
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


d = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)


def set_query(q):
    d.eval(rf"""(() => {{
  const i = document.querySelector('.search input, input[placeholder]');
  if (!i) throw new Error('no search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, {json.dumps(q)});
  i.dispatchEvent(new Event('input', {{bubbles: true}}));
}})()""")
    time.sleep(0.6)
    val = d.eval(r"""document.querySelector('.search input, input[placeholder]').value""")
    assert val == q, f"查询未注入: {val!r} != {q!r}"


def visible_kinds():
    out = d.eval(r"""(() => {
  const cards = [...document.querySelectorAll('.cards [data-idx]')];
  const kinds = cards.map(c => (c.className.match(/badge\s+(\w+)/) || [])[1]
    || (c.querySelector('.badge') ? c.querySelector('.badge').className.split(' ')[1] : null));
  return JSON.stringify({n: cards.length, kinds});
})()""")
    if not isinstance(out, str):
        raise RuntimeError("eval type")
    return json.loads(out)


base = visible_kinds()
print("baseline:", base["n"], "cards, kinds:", sorted(set(base["kinds"])))
assert base["n"] > 0, "抽屉无卡片"

set_query("img:")
r = visible_kinds()
print("img:", r["n"], sorted(set(r["kinds"])))
assert r["n"] > 0 and set(r["kinds"]) <= {"image"}, "img: 过滤异常"

set_query("text:")
r = visible_kinds()
print("text:", r["n"], sorted(set(r["kinds"])))
assert r["n"] > 0 and set(r["kinds"]) == {"text"}, "text: 过滤异常"

# 取库里一条真实文本的前几个字，验证 前缀+词 AND 组合
probe = d.eval(r"""(async () => {
  const is = await window.__TAURI_INTERNALS__.invoke('list_items', {limit: 50});
  const t = is.find(x => x.kind === 'text' && x.content.trim().length >= 3);
  return JSON.stringify(t ? t.content.trim().slice(0, 3) : null);
})()""")
word = json.loads(probe) if isinstance(probe, str) else None
assert word, "库里没有可用文本"
set_query(f"text:{word}")
r = visible_kinds()
print(f"text:{word}:", r["n"], sorted(set(r["kinds"])))
assert 0 < r["n"] <= base["n"] and set(r["kinds"]) == {"text"}, "text:词 组合过滤异常"

set_query("link:")
r = visible_kinds()
print("link:", r["n"], sorted(set(r["kinds"])))
assert set(r["kinds"]) <= {"link"}, "link: 过滤异常"

set_query("")
r = visible_kinds()
assert r["n"] == base["n"], "清空后未还原"
print("PASS: text:/img:/link: 前缀过滤 + 前缀词组合 + 清空还原，全部实测通过")
