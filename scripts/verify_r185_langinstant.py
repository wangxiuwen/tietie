# 方向185 真机验证：语言切换即时生效（本窗 + 跨窗）
# 剧本（合成 select 变更 + 双窗断言，结束还原语言偏好）：
#   记设置窗/托盘窗基线文案（中文）
#   → 合成改设置页语言下拉为 en → 设置窗自身标签即变英文
#   → 托盘窗（另一 WebView）占位符/按钮也变英文（storage 事件跨窗传播）
#   → 还原为 auto（或原值），双窗回中文
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
tray.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.6)


def snap():
    s = st.eval(r"""(() => JSON.stringify({
      langLabel: document.querySelector('.lang-select option[value=zh]')?.textContent ?? null,
      general: [...document.querySelectorAll('.settings-subhead')].map(e => e.textContent.trim()).slice(0, 2),
      select: document.querySelector('.lang-select')?.value ?? null,
    }))()""")
    t = tray.eval(r"""(() => JSON.stringify({
      placeholder: document.querySelector('input')?.placeholder ?? null,
      quit: [...document.querySelectorAll('button')].map(b => b.textContent.trim())
        .find(x => x.length > 0 && x.length < 6) ?? null,
    }))()""")
    if not isinstance(s, str) or not isinstance(t, str):
        raise RuntimeError("eval type")
    return json.loads(s), json.loads(t)


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


# 开局归位（重跑残留）：强制 auto（本机中文系统→基线中文）
set_lang("auto")
s0, t0 = snap()
print("baseline:", s0["general"], "| tray:", t0["placeholder"], t0["quit"])
orig_pref = "auto"
assert t0["placeholder"], "托盘占位符缺失"

set_lang("en")
s1, t1 = snap()
print("en:", s1["general"], "| tray:", t1["placeholder"], t1["quit"])
assert s1["general"] != s0["general"] and all(g.isascii() for g in s1["general"]), \
    f"设置窗未即时: {s1['general']}"
assert "Search" in (t1["placeholder"] or "") or t1["placeholder"] != t0["placeholder"], \
    f"托盘窗未跨窗生效: {t1['placeholder']!r} vs {t0['placeholder']!r}"
assert (t1["quit"] or "") != (t0["quit"] or "") or "Quit" in (t1["quit"] or ""), \
    f"托盘按钮未变: {t1['quit']!r}"

set_lang(orig_pref)
time.sleep(1.2)
s2, t2 = snap()
print("restored:", s2["general"][0], "| tray:", t2["placeholder"])
assert s2["general"][0] == s0["general"][0] and t2["placeholder"] == t0["placeholder"], \
    "还原失败"
print("PASS: 语言切换设置窗即时 + 托盘窗跨窗即时（storage 事件），auto 还原")
