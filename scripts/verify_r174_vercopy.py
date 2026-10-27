# 方向174 真机验证：设置页点击版本号复制完整版本串（已具备收口轮）
# 实证：ver-copy 按钮自方向96 起即点击复制（app_version 全串）+✓ 反馈。
# 剧本（剪贴板快照/还原）：
#   桥取 app_version 期望值 + 快照当前剪贴板
#   → 合成点击设置页版本按钮 → ✓ 反馈出现
#   → Get-Clipboard（GBK 解码）== 期望版本串
#   → 还原剪贴板快照
import json
import subprocess
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and "view=settings" in t["url"])
st = CDP(ws_url)


def clip():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                         capture_output=True)
    return out.stdout.decode("gbk", "replace").rstrip("\r\n")


snapshot = clip()
print("clipboard snapshot:", repr(snapshot[:60]))

want = st.eval(r"""(async () => await window.__TAURI_INTERNALS__.invoke('app_version'))()""")
print("app_version:", want)
assert isinstance(want, str) and want

# 合成点击无用户激活会被 navigator.clipboard 拒（老坑）——可信点击
pos = json.loads(st.eval(r"""(() => {
  const b = document.querySelector('.ver-copy');
  if (!b) return 'NOBTN';
  b.scrollIntoView({block: 'center'});
  const r = b.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2});
})()"""))
for typ in ("mousePressed", "mouseReleased"):
    st.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                           "params": {"type": typ, "button": "left",
                                      "buttons": 1 if typ == "mousePressed" else 0,
                                      "clickCount": 1, "x": pos["x"], "y": pos["y"]}}))
    st.ws.recv_text()
    time.sleep(0.12)
time.sleep(0.5)

feedback = st.eval(r"""document.querySelector('.ver-copy').textContent.includes('✓') ? 'y' : 'n'""")
got = clip()
print("feedback ✓:", feedback, "| clipboard:", got)
assert feedback == "y", "无 ✓ 反馈"
assert got == want, f"剪贴板 {got!r} != 版本串 {want!r}"

# 还原剪贴板
subprocess.run(["powershell", "-NoProfile", "-Command",
                f"Set-Clipboard -Value {json.dumps(snapshot)}"], capture_output=True)
print("PASS: 点击版本号 → 剪贴板=完整版本串 + ✓ 反馈（方向96 起已具备，本轮实证），剪贴板已还原")
