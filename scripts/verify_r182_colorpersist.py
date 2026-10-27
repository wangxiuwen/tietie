# 方向182 真机验证：晾衣架颜色筛选跨会话记忆
# 剧本（合成点击 + 重启实例验证持久，结束还原 null 并删 key）：
#   点击某色点 → active 迁移 + localStorage 记下颜色
#   → 杀进程重启（新会话）→ 断言该色点仍 active（跨会话恢复）
#   → 点「全部」还原（active 回 ∗、key 删除）
import json
import subprocess
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

# 开局还原（防残留）
line.eval(r"""(() => {
  const all = document.querySelector('.cfilter-dot.all');
  if (all && !all.className.includes('active')) all.click();
})()""")
time.sleep(0.4)
base = line.eval("localStorage.getItem('tietie.memoColorFilter')")
assert base in (None, "null", ""), f"开局残留筛选: {base!r}"

# 选第一个彩色点
picked = json.loads(line.eval(r"""(() => {
  const dots = [...document.querySelectorAll('.cfilter-dot')].filter(d => !d.className.includes('all'));
  const d = dots.find(x => getComputedStyle(x).backgroundColor === 'rgb(0, 122, 255)');
  const target = d || dots[0];
  if (!target) return 'NODOT';
  const bg = getComputedStyle(target).backgroundColor;
  target.click();
  return JSON.stringify({bg});
})()"""))
print("picked:", picked)
assert picked != "NODOT", "无色点"
time.sleep(0.5)  # 等 React 渲染再读 active（同步块内读是旧 DOM）
active_now = line.eval(r"""(() => {
  const a = document.querySelector('.cfilter-dot.active');
  return a ? getComputedStyle(a).backgroundColor : null;
})()""")
assert active_now == picked["bg"], f"选色未生效: {active_now}"
stored = line.eval("localStorage.getItem('tietie.memoColorFilter')")
print("stored:", stored)
assert stored and stored.startswith("#"), f"未持久化: {stored!r}"

# 杀进程重启（新会话）
subprocess.run(["powershell", "-NoProfile", "-Command",
                "Get-Process tietie -ErrorAction SilentlyContinue | Stop-Process -Force; "
                "Start-Sleep -Seconds 2; "
                "$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9223'; "
                "Start-Process \"$env:LOCALAPPDATA\\tietie\\tietie.exe\"; "
                "Start-Sleep -Seconds 4"], capture_output=True)

line2 = CDP(page_ws(lambda u: "view=line" in u))
line2.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.8)

after = json.loads(line2.eval(r"""(() => {
  const all = document.querySelector('.cfilter-dot.all');
  const active = document.querySelector('.cfilter-dot.active');
  return JSON.stringify({
    allActive: all ? all.className.includes('active') : null,
    activeBg: active ? getComputedStyle(active).backgroundColor : null,
    stored: localStorage.getItem('tietie.memoColorFilter'),
  });
})()"""))
print("after restart:", after)
assert after["allActive"] is False, "重启后筛选丢失（回到全部）"
assert after["activeBg"] == picked["bg"], f"重启后 active 色不符: {after['activeBg']} != {picked['bg']}"

# 还原：点「全部」→ active 回 ∗ 且 key 删除
line2.eval(r"""(() => document.querySelector('.cfilter-dot.all').click())()""")
time.sleep(0.4)
final = json.loads(line2.eval(r"""(() => JSON.stringify({
  allActive: document.querySelector('.cfilter-dot.all').className.includes('active'),
  stored: localStorage.getItem('tietie.memoColorFilter'),
}))()"""))
print("restored:", final)
assert final["allActive"] is True and final["stored"] is None, "还原失败"
print("PASS: 颜色筛选点击即存、跨重启恢复、点全部清 key，全链实测")
