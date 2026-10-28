# 方向212 真机验证：托盘行 hover 显示快删 × 按钮并删除
# 剧本（临时探针行 + 可信 hover/click + 桥核对，探针即删除对象）：
#   Set-Clipboard 造唯一探针（捕获入库）→ 托盘显示该行
#   → 基线（未 hover）× 隐藏（display:none）
#   → 可信 mouseMoved 移入该行 → × 显现
#   → 可信点 × → 行消失、桥条目删除（探针为临时数据无需还原）
import json
import subprocess
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
TS = int(time.time())
PROBE = f"R212快删探针{TS}"


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


tray = CDP(page_ws(lambda u: "view=tray" in u))
main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))


def inv(cmd, args=None):
    out = main.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} type")
    return json.loads(out)


# 清残留 + 造探针
for it in inv("list_items", {"limit": 50}):
    if it["content"].startswith("R212"):
        inv("delete_item", {"id": it["id"]})
time.sleep(0.4)
subprocess.run(["powershell", "-NoProfile", "-Command",
                f"Set-Clipboard -Value '{PROBE}'"], capture_output=True)
pid = None
for _ in range(20):
    time.sleep(1)
    f = [x["id"] for x in inv("list_items", {"limit": 5}) if x["content"] == PROBE]
    if f:
        pid = f[0]
        break
assert pid, "探针未入库"
print("probe id:", pid)

# 托盘显示并刷新
tray.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.6)
tray.eval(r"""(() => {
  const i = document.querySelector('input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
time.sleep(0.6)


def move(x, y):
    tray.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                             "params": {"type": "mouseMoved", "x": x, "y": y}}))
    tray.ws.recv_text()
    time.sleep(0.4)


# 定位探针行（最新在前）
pos = json.loads(tray.eval(r"""(() => {
  const rows = [...document.querySelectorAll('.po-row')];
  const row = rows.find(r => r.textContent.includes('R212快删探针'));
  if (!row) return 'NOROW';
  const r = row.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2,
    rowX: r.x, rowW: r.width});
})()"""))
assert pos != "NOROW", "探针行不在托盘"
print("row at:", pos)

# 基线：× 隐藏（先把指针挪到远角清残留 hover 态）
move(10, 300)
time.sleep(0.3)
hidden = tray.eval(r"""(() => {
  const rows = [...document.querySelectorAll('.po-row')];
  const row = rows.find(r => r.textContent.includes('R212快删探针'));
  const del = row.querySelector('.po-del');
  return del ? getComputedStyle(del).display : 'NODEL';
})()""")
print("× display (no hover):", hidden)
assert hidden == "none", f"未 hover 已显示: {hidden}"

# hover 该行 → × 显现
move(pos["x"], pos["y"])
shown = tray.eval(r"""(() => {
  const rows = [...document.querySelectorAll('.po-row')];
  const row = rows.find(r => r.textContent.includes('R212快删探针'));
  const del = row.querySelector('.po-del');
  const r = del.getBoundingClientRect();
  return JSON.stringify({display: getComputedStyle(del).display,
    x: r.x + r.width / 2, y: r.y + r.height / 2});
})()""")
print("× after hover:", shown)
d = json.loads(shown)
assert d["display"] != "none", "hover 未显现 ×"

# 可信点 ×（先重 hover 确保在位）
move(pos["x"], pos["y"])
for typ in ("mousePressed", "mouseReleased"):
    tray.ws.send(json.dumps({"id": 9902, "method": "Input.dispatchMouseEvent",
                             "params": {"type": typ, "button": "left",
                                        "buttons": 1 if typ == "mousePressed" else 0,
                                        "clickCount": 1, "x": d["x"], "y": d["y"]}}))
    tray.ws.recv_text()
    time.sleep(0.12)
time.sleep(1.0)

# 行消失 + 桥核对
gone = tray.eval(r"""(() => [...document.querySelectorAll('.po-row')]
  .some(r => r.textContent.includes('R212快删探针')) ? 'n' : 'y')()""")
left = [x for x in inv("list_items", {"limit": 50}) if x["content"].startswith("R212")]
print("row gone:", gone, "| bridge left:", len(left))
assert gone == "y" and len(left) == 0, "快删未生效"
print("PASS: hover 显 × / 点击删行删库，探针即删除对象")
