# 方向188 真机验证：设置页 #sec-* hash 直达分区滚动
# 剧本（纯 URL/伪导航 + DOM 断言，只读）：
#   设置窗 location.hash = #sec-hotkeys → settings-open 触发 →
#   断言 #sec-hotkeys 顶部接近视口顶（scrollTop 已滚动），
#   换 #sec-general 再验，最后清 hash 复位
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


main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))
st = CDP(page_ws(lambda u: "view=settings" in u))


def scroll_state(sec_id):
    out = st.eval(rf"""(() => {{
    const el = document.getElementById('{sec_id}');
    if (!el) return 'NOEL';
    const r = el.getBoundingClientRect();
    return JSON.stringify({{top: Math.round(r.top), h: Math.round(r.top)}});
  }})()""")
    if not isinstance(out, str):
        raise RuntimeError("type")
    return json.loads(out)


def goto(h):
    st.eval(rf"""location.hash = {json.dumps(h)};""")
    time.sleep(0.2)
    main.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
    time.sleep(0.9)


# 基线：无 hash 时首屏顶部即第一分区
st.eval("location.hash = '';")
time.sleep(0.2)
main.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(0.9)

goto("#sec-hotkeys")
r1 = scroll_state("sec-hotkeys")
print("#sec-hotkeys top:", r1)
assert r1 != "NOEL" and abs(r1["top"]) < 60, f"hotkeys 未滚到顶: {r1}"

goto("#sec-general")
r2 = scroll_state("sec-general")
print("#sec-general top:", r2)
# general 是末分区：页面滚到底后距顶 ~78px 即为极限（scrollIntoView 已尽力）
assert r2 != "NOEL" and abs(r2["top"]) < 120, f"general 未滚动: {r2}"

# 复位
st.eval("location.hash = '';")
time.sleep(0.2)
main.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(0.9)
h = st.eval("location.hash")
print("hash after clear:", repr(h))
assert h == "", "hash 未清"
print("PASS: #sec-hotkeys/#sec-general hash 直达滚动定位、清 hash 复位")
