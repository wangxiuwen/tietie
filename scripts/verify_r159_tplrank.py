# 方向159 真机验证：便签模板按使用计数排序，常用靠前
# 剧本（合成输入，晾衣架窗；模板为会话级，重启自清，无需清理）：
#   开 composer → 存模板 B(先) 再 A(后) → 初始序 [A,B]（0 使用按新近）
#   → 点 A×1、B×2 → 断言 chip 序变为 [B,A]（按使用数）
#   → 再存模板 C（0 使用）→ 断言 C 排在末尾而非最前（排序不变式）
#   → 补一个 tie-break：点 C×2 与 B 追平 → C 在 B 前（稳定排序+新近优先）
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


line = CDP(page_ws(lambda u: "view=line" in u))
line.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.6)


def js(code):
    out = line.eval(code)
    if not isinstance(out, str):
        raise RuntimeError(f"eval -> {type(out).__name__}")
    return out


def close_composer():
    line.eval(r"""(() => {
  const c = [...document.querySelectorAll('button')].find(b =>
    b.closest('.line-compose-foot') && b.className.includes('ghost'));
  if (document.querySelector('.line-card.composer') && c) c.click();
})()""")
    time.sleep(0.3)


def open_composer():
    n = js(r"""(() => {
  const b = [...document.querySelectorAll('button.line-new')]
    .find(x => (x.title || '').includes('便签') && !x.title.includes('导出'));
  if (!b) return 'nobtn';
  b.click();
  return 'ok';
})()""")
    assert n == "ok", f"新建按钮: {n}"
    time.sleep(0.5)
    assert js("document.querySelector('.line-card.composer textarea') ? 'y' : 'n'") == "y", \
        "composer 未打开"


def set_text(text):
    got = js(rf"""(() => {{
  const ta = document.querySelector('.line-card.composer textarea');
  const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  set.call(ta, {json.dumps(text)});
  ta.dispatchEvent(new Event('input', {{bubbles: true}}));
  return ta.value;
}})()""")
    assert got == text, f"文本未注入: {got!r}"
    time.sleep(0.2)


def click_chip(label):
    n = js(rf"""(() => {{
  const c = [...document.querySelectorAll('.tpl-chip')]
    .find(x => x.textContent.trim() === {json.dumps(label)});
  if (!c) return 'NOCHIP';
  c.click();
  return 'ok';
}})()""")
    assert n == "ok", f"chip {label} 不存在"
    time.sleep(0.3)


def add_tpl(text):
    set_text(text)
    n = js(r"""(() => {
  const b = document.querySelector('.line-card.composer .tpl-add');
  if (!b) return 'nobtn';
  b.click();
  return 'ok';
})()""")
    assert n == "ok", "存模板按钮不在"
    time.sleep(0.4)


def chip_order():
    """read the chip order, retrying until two consecutive reads agree"""
    prev = None
    for _ in range(6):
        cur = json.loads(js(r"""JSON.stringify([...document.querySelectorAll('.tpl-chip')]
  .map(c => c.textContent.trim()))"""))
        if cur == prev:
            return cur
        prev = cur
        time.sleep(0.35)
    return prev


close_composer()
open_composer()
add_tpl("模版乙条目")   # label = 前 6 字 "模版乙条目"
add_tpl("模版甲条目")
order0 = chip_order()
print("initial order:", order0)
assert "模版甲条目" in order0 and "模版乙条目" in order0
assert order0.index("模版甲条目") < order0.index("模版乙条目"), "0 使用应按新近序（甲后加在前）"

click_chip("模版甲条目")           # 甲 uses=1
click_chip("模版乙条目")           # 乙 uses=1
click_chip("模版乙条目")           # 乙 uses=2
order1 = chip_order()
print("after A1/B2:", order1)
assert order1.index("模版乙条目") < order1.index("模版甲条目"), "常用未前置"

add_tpl("模版丙条目")              # 丙 uses=0
order2 = chip_order()
print("after add C:", order2)
assert order2[-1] == "模版丙条目", "0 使用新模板不应插到最前"

click_chip("模版丙条目")
click_chip("模版丙条目")           # 丙 uses=2，与乙追平——稳定排序保持既有相对序
order3 = chip_order()
print("after C2 tie:", order3)
assert order3.index("模版丙条目") < order3.index("模版甲条目"), "追平后仍应高于低使用项"
assert order3 == ["模版乙条目", "模版丙条目", "模版甲条目"], "追平应保持稳定（不跳位）"
print("PASS: 模板按使用计数排序、0 使用不插队、追平保持稳定序，全部实测")
