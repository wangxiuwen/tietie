# 方向152 真机验证：热键行保存了系统占用组合后行上出现持久红标
# 剧本（全程走应用自己的改键 UI，验证后还原）：
#   基线：晾衣架行(Control+Alt+J，不在冲突表)无红标
#   → 修改 → CDP 按键录 Control+Alt+KeyV（Win11 声音面板，真实事故项）→ 确定
#   → 断言行上出现红色 settings-tag.err（与系统常用组合冲突）
#   → 还原回 Control+Alt+KeyJ → 断言红标消失、徽章复原
#   → 只读复核 settings.json 已还原
# ★坑：热键区在设置窗折叠线以下，必须先 scrollIntoView 再取 rect 可信点击，
#   否则点击落空（NOCAP）。
import json
import os
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
LABEL = "晾衣架开关"


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))
st = CDP(page_ws(lambda u: "view=settings" in u))
main.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.2)


def st_eval(js):
    out = st.eval(js)
    if not isinstance(out, str):
        raise RuntimeError(f"eval returned {type(out).__name__}: {out!r}")
    return out


def row_js(body):
    return st_eval(rf"""(() => {{
  const row = [...document.querySelectorAll('.settings-row')].find(r =>
    r.querySelector('.settings-label')?.textContent.includes('{LABEL}'));
  if (!row) return 'NOROW';
  {body}
}})()""")


def row_state():
    return json.loads(row_js(r"""const badge = row.querySelector('.hotkey-badge');
  const errs = [...row.querySelectorAll('.settings-tag.err')].map(e => e.textContent.trim());
  return JSON.stringify({badge: badge ? badge.textContent : null, errs,
    visible: !!(badge && badge.offsetWidth > 0)});"""))


def click_row_button(sel, expect_capture=False):
    """scrollIntoView the button first — the hotkey section sits below the fold.
    Trusted clicks can transiently miss right after the window is shown, so
    re-scroll/re-measure/re-click until the expected effect shows (<=3 tries)."""
    for attempt in range(3):
        # ★ dict 直接解包拿到的是键名 "x"/"y"，必须按下标取坐标
        pos = json.loads(row_js(rf"""const b = row.querySelector('{sel}');
  if (!b) return 'NOBTN';
  b.scrollIntoView({{block: 'center'}});
  const r = b.getBoundingClientRect();
  return JSON.stringify({{x: r.x + r.width / 2, y: r.y + r.height / 2}});"""))
        cx, cy = pos["x"], pos["y"]
        for typ in ("mousePressed", "mouseReleased"):
            st.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                                   "params": {"type": typ, "button": "left",
                                              "buttons": 1 if typ == "mousePressed" else 0,
                                              "clickCount": 1, "x": cx, "y": cy}}))
            st.ws.recv_text()
            time.sleep(0.12)
        time.sleep(0.6)
        if not expect_capture:
            return
        for _ in range(6):
            if str(st.eval("document.querySelector('.hotkey-capture') ? 1 : 0")) == "1":
                return
            time.sleep(0.2)
    raise RuntimeError(f"click on {sel} never opened the recorder after 3 tries")


def keycombo(mods, code, key, vk):
    st.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchKeyEvent", "params": {
        "type": "keyDown", "modifiers": mods, "code": code, "key": key,
        "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}}))
    st.ws.recv_text()
    time.sleep(0.15)


CTRL_ALT = 2 | 1  # CDP modifier bitmask: Alt=1 Ctrl=2

base = row_state()
print("baseline:", base)
assert base != "NOROW" and base["errs"] == [] and "J" in base["badge"], "基线异常"
assert base["visible"], "行不可见"

# 录入 Control+Alt+KeyV
click_row_button(".btn.ghost", expect_capture=True)
keycombo(CTRL_ALT, "KeyV", "v", 86)
v = st.eval("document.querySelector('.hotkey-capture').value")
warn = st_eval(r"""[...document.querySelectorAll('.settings-tag.warn')]
  .some(e => e.textContent.includes('系统')) ? '1' : '0'""")
print("pending:", v, "| capture-time warn(101):", warn)
assert "V" in v, "录制未捕获 Ctrl+Alt+V"
assert warn == "1", "101 的录制中黄色警告消失（回归）"

click_row_button(".btn.primary")
time.sleep(1.0)

conflicted = row_state()
print("after save:", conflicted)
assert any("系统" in e for e in conflicted["errs"]), "FAIL: 保存系统冲突组合后无红标"
assert "V" in conflicted["badge"], "FAIL: 徽章未更新为新组合"
print("PASS: 系统冲突组合保存后，热键行出现持久红色标记")

# 还原 Control+Alt+KeyJ
click_row_button(".btn.ghost", expect_capture=True)
keycombo(CTRL_ALT, "KeyJ", "j", 74)
click_row_button(".btn.primary")
time.sleep(1.0)

restored = row_state()
print("restored:", restored)
assert restored["errs"] == [] and "J" in restored["badge"], "FAIL: 还原失败"

cfg = json.load(open(os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\settings.json"),
                     encoding="utf-8"))
assert cfg["clothesline_hotkey"] == "Control+Alt+KeyJ", f"配置未还原: {cfg}"
print("PASS: 还原后红标消失、徽章与配置均回到 Control+Alt+KeyJ")
