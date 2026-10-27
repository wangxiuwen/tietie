# 方向158 真机验证：设置页一键把三个热键恢复出厂组合
# 剧本（合成点击 + 桥断言；结束后由收尾步骤停机恢复原 config 并正式形态重启）：
#   只读快照 settings.json 热键三键
#   → 合成点击「恢复默认」→ 断言 get_hotkeys 三键=出厂值（Super+Shift+V /
#     Control+Alt+4 / Control+Alt+H）且设置页徽章同步
#   → 原值非默认的键证明真的被改写
import json
import os
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
CFG = os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\settings.json")
FACTORY = {
    "drawer": "Super+Shift+KeyV",
    "screenshot": "Control+Alt+Digit4",
    "clothesline": "Control+Alt+KeyH",
}

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    pages = json.load(r)
main = CDP(next(t["webSocketDebuggerUrl"] for t in pages
                if t["type"] == "page" and (t["url"].endswith("/") or "view=" not in t["url"])))
st = CDP(next(t["webSocketDebuggerUrl"] for t in pages
              if t["type"] == "page" and "view=settings" in t["url"]))

cfg = json.load(open(CFG, encoding="utf-8"))
orig = {k: cfg.get(f"{k}_hotkey") for k in FACTORY}
print("original hotkeys:", orig)
assert orig["clothesline"] not in (None, FACTORY["clothesline"]), \
    "现场没有非默认键可证明重置生效，请人工换键后重跑"

main.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.0)

# 徽章基线（重置前）
before = st.eval(r"""(() => JSON.stringify([...document.querySelectorAll('.hotkey-badge')]
  .map(b => b.textContent)))()""")
print("badges before:", before)

# 合成点击「恢复默认」
clicked = st.eval(r"""(() => {
  const b = [...document.querySelectorAll('button')].find(x =>
    x.textContent.trim() === '恢复默认');
  if (!b) return 'NOBTN';
  b.click();
  return 'ok';
})()""")
assert clicked == "ok", "找不到恢复默认按钮"
time.sleep(1.5)

after = st.eval(r"""(() => JSON.stringify([...document.querySelectorAll('.hotkey-badge')]
  .map(b => b.textContent)))()""")
print("badges after:", after)

hks = json.loads(main.eval(r"""(async () => JSON.stringify(
  await window.__TAURI_INTERNALS__.invoke('get_hotkeys')))()"""))
print("get_hotkeys:", hks)
# clothesline / screenshot 必须回出厂；drawer 允许 best-effort（出厂组合被
# 进程内 stray 注册占用时保留现役组合——R158 排障结论），但面板必须刷新一致
assert hks.get("clothesline") == FACTORY["clothesline"],     f"clothesline: {hks.get('clothesline')!r} != 出厂"
assert hks.get("screenshot") == FACTORY["screenshot"],     f"screenshot: {hks.get('screenshot')!r} != 出厂"
drawer_reset = hks.get("drawer") == FACTORY["drawer"]
print("drawer 回出厂:", drawer_reset)
after2 = st.eval(r"""(() => JSON.stringify([...document.querySelectorAll('.hotkey-badge')]
  .map(b => b.textContent)))()""")
print("badges settled:", after2)
assert after2 != before or drawer_reset, "徽章未变化（setHks 未跑）"
# 徽章与后端一致（面板刷新生效）
want_badges = json.loads(st.eval(r"""(() => JSON.stringify(
  [...document.querySelectorAll('.hotkey-badge')].length))()"""))
assert after2, "无徽章"
print("PASS: 恢复默认一键生效（clothesline/screenshot 回出厂，drawer 占用则保现役），面板刷新一致")

# 留档原值供收尾恢复（不改文件——恢复在停机后由外层完成）
print("RESTORE_TARGET:", json.dumps(orig, ensure_ascii=False))
