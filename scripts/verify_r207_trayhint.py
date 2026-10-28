# 方向207 真机验证：托盘空搜索占位符带 ⌘N 快速复制提示
# 剧本（合成语言切换 + DOM 断言，结束还原 auto）：
#   中文（auto）→ 占位符含「⌘数字 快速复制」
#   → 切 en → 含 "⌘number quick-copies"
#   → 还原 auto
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and "view=settings" in t["url"])
st = CDP(ws_url)


def set_lang(pref):
    n = st.eval(rf"""(() => {{
      const sel = document.querySelector('.lang-select');
      const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
      set.call(sel, {json.dumps(pref)});
      sel.dispatchEvent(new Event('change', {{bubbles: true}}));
      return sel.value;
    }})()""")
    assert n == pref, n
    time.sleep(1.0)


def tray_placeholder():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        tray = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                    if t["type"] == "page" and "view=tray" in t["url"])
    t = CDP(tray)
    return t.eval(r"""(() => {
  const i = document.querySelector('.po-search input, input');
  return i ? i.placeholder : null;
})()""")


set_lang("auto")
zh = tray_placeholder()
print("zh:", zh)
assert "⌘数字" in zh and "快速复制" in zh, f"中文提示缺失: {zh!r}"

set_lang("en")
en = tray_placeholder()
print("en:", en)
assert "number" in en and "quick-cop" in en, f"英文提示缺失: {en!r}"

set_lang("auto")
back = tray_placeholder()
assert back == zh, "还原失败"
print("PASS: 空搜索占位符双语含 ⌘N 快速复制提示，auto 还原")
