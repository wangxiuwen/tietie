# 方向197 真机验证：语言下拉 focus 后字母跳转（a/z/e）
# 剧本（合成 focus + keydown + 双窗断言，结束还原 auto）：
#   聚焦语言下拉 → 合成 keydown 'e' → 下拉值变 en + 托盘窗跨窗翻英文
#   → keydown 'a' → 回 auto + 双窗回中文
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


st = CDP(page_ws(lambda u: "view=settings" in u))
tray = CDP(page_ws(lambda u: "view=tray" in u))
st.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.0)


def sel_state():
    s = st.eval(r"""(() => {
  const sel = document.querySelector('.lang-select');
  sel.focus();
  return JSON.stringify({v: sel.value, focused: document.activeElement === sel});
})()""")
    if not isinstance(s, str):
        raise RuntimeError("type")
    d = json.loads(s)
    t = tray.eval(r"""document.querySelector('input')?.placeholder ?? null""")
    return {**d, "tray": t}


def key(k):
    st.eval(rf"""(() => {{
  const sel = document.querySelector('.lang-select');
  sel.dispatchEvent(new KeyboardEvent('keydown',
    {{key: {json.dumps(k)}, bubbles: true, cancelable: true}}));
}})()""")
    time.sleep(0.9)


# 开局归位 auto
key("a")
b = sel_state()
print("baseline:", b)
assert b["v"] == "auto" and b["focused"], "基线异常"

# e → en（本窗 + 跨窗）
key("e")
s1 = sel_state()
print("after e:", s1)
assert s1["v"] == "en", f"值未跳 en: {s1['v']}"
assert "Search" in (s1["tray"] or ""), f"托盘未跨窗翻英文: {s1['tray']!r}"

# a → auto 回中文
key("a")
s2 = sel_state()
print("after a:", s2)
assert s2["v"] == "auto" and s2["tray"] == b["tray"], "还原失败"
print("PASS: focus 后 e→en/a→auto，本窗值跳 + 托盘跨窗即时，auto 还原")
