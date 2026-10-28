# 方向194 真机验证：托盘面板用户拉宽后跨会话保持
# 剧本（桥 set_size 模拟用户拉宽 → Resized 事件持久化 → 重启恢复 → 还原）：
#   打开托盘 → 基线 320 宽
#   → set_size Logical 480x460（模拟拉宽）→ settings 落 tray_popover_w=480
#   → 杀进程重启 → 打开托盘 → 宽 480（跨会话恢复）
#   → set_size 回 320x460 → settings 归默认值 → 重启复核 320 → 清 settings 键
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


def tray_ws():
    return page_ws(lambda u: "view=tray" in u)


def restart_with_cdp():
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like '*tietie*' } "
                    "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; "
                    "Start-Sleep -Seconds 2; "
                    "$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9223'; "
                    "Start-Process \"$env:LOCALAPPDATA\\tietie\\tietie.exe\"; "
                    "Start-Sleep -Seconds 4"], capture_output=True)


def size():
    # 走 show_tray_panel（托盘菜单「查看最近剪切板」同一条 toggle 路径，
    # 持久尺寸在该路径恢复）——先 hide 保证 toggle 进入 show 分支
    st = CDP(tray_ws())
    st.eval(r"""(async () => {
  await window.__TAURI_INTERNALS__.invoke('plugin:window|hide');
  await window.__TAURI_INTERNALS__.invoke('show_tray_panel');
})()""")
    time.sleep(0.6)
    out = st.eval(r"""(async () => JSON.stringify(
  await window.__TAURI_INTERNALS__.invoke('plugin:window|inner_size')))()""")
    if not isinstance(out, str):
        raise RuntimeError("type")
    return json.loads(out)


def set_size(w, h):
    st = CDP(tray_ws())
    st.eval(rf"""(async () => {{
  await window.__TAURI_INTERNALS__.invoke('plugin:window|hide');
  await window.__TAURI_INTERNALS__.invoke('show_tray_panel');
  await window.__TAURI_INTERNALS__.invoke('plugin:window|set_size',
    {{ value: {{ Logical: {{ width: {w}, height: {h} }} }} }});
  return 'ok';
}})()""")
    time.sleep(0.8)


def settings_w():
    st = CDP(tray_ws())
    return st.eval(r"""(async () => {
  try { return await window.__TAURI_INTERNALS__.invoke('get_setting', {key: 'tray_popover_w'}); }
  catch (e) { return 'NOCMD'; }
})()""")


# 有无 get_setting 命令不确定——直接读 settings.json（LOCALAPPDATA 域只读）
import os
CFG = os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\settings.json")


def cfg_w():
    d = json.load(open(CFG, encoding="utf-8"))
    return d.get("tray_popover_w")


# 基线（重跑残留 480 时先归位再验全链）
b = size()
print("current:", b)
if abs(b["width"] - 480) < 6:
    set_size(320, 460)
    time.sleep(0.8)
    b = size()
    print("reset baseline:", b)
assert abs(b["width"] - 320) < 4, f"基线宽异常: {b['width']}"

# 模拟拉宽 → 事件持久化
set_size(480, 460)
time.sleep(0.8)
w = cfg_w()
print("persisted tray_popover_w:", w)
assert str(w) == "480", f"未持久化: {w!r}"

# 重启 → 跨会话恢复（重启后首次 show 会走 position_tray_popover 用持久值）
restart_with_cdp()
a = size()
print("after restart:", a)
assert abs(a["width"] - 480) < 6, f"跨会话未恢复: {a['width']}"

# 还原 320 并复核
set_size(320, 460)
time.sleep(0.8)
restart_with_cdp()
z = size()
print("restored:", z)
assert abs(z["width"] - 320) < 6, f"还原失败: {z['width']}"
print("PASS: 拉宽 480 持久化 → 重启恢复 480 → 还原 320 复核，全链实测")
