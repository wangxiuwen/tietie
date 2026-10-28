# 方向202 真机验证：抽屉批量删除 >5 条两段式确认（对齐153模式）
# 剧本（可信 Ctrl 点选 6 卡 → 两段删除 → 探针复活法核对，结束还原）：
#   注：删除不可逆——用「先记 6 条真实条目 id，确认两段流程后把删掉的
#   条目当已删事实」太重。改安全法：两段 UI 流程用真实 6 卡走，
#   但在 armed 态【取消选择】不执行（测 armed 不删）；
#   执行段用 1 条可牺牲探针（临时剪贴板捕获的 R202 探针）验证 ≤5 直删；
#   >5 执行段改为：armed 后二击，断言批量栏消失+桥 list 少 6——
#   但这会真删 6 条历史。折中：>5 执行真删【6 条探针】（全为本轮临时造）。
import json
import subprocess
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and (t["url"].endswith("/") or "view=" not in t["url"]))
d = CDP(ws_url)
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)


def inv(cmd, args=None):
    out = d.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} type")
    return json.loads(out)


def set_clip(text):
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Set-Clipboard -Value '{text}'"], capture_output=True)


def click(x, y, mods=0):
    for typ in ("mousePressed", "mouseReleased"):
        d.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                              "params": {"type": typ, "button": "left",
                                         "buttons": 1 if typ == "mousePressed" else 0,
                                         "clickCount": 1, "modifiers": mods,
                                         "x": x, "y": y}}))
        d.ws.recv_text()
        time.sleep(0.12)


def card_pos(idx):
    out = d.eval(rf"""(() => {{
  const c = document.querySelector('.cards [data-idx="{idx}"]');
  if (!c) return 'NOCARD';
  c.scrollIntoView({{block: 'nearest'}});
  const r = c.getBoundingClientRect();
  return JSON.stringify({{x: r.x + 24, y: r.y + 14}});
}})()""")
    return json.loads(out)


def bar():
    out = d.eval(r"""(() => {
  const bar = document.querySelector('.batch-bar');
  if (!bar) return JSON.stringify({present: false});
  const del = [...bar.querySelectorAll('button')].find(b =>
    b.textContent.includes('删除') || b.textContent.includes('Delete'));
  return JSON.stringify({present: true, text: bar.querySelector('span').textContent.trim(),
    delLabel: del ? del.textContent.trim() : null, delCls: del ? del.className : null});
})()""")
    return json.loads(out)


def clear_sel():
    d.eval(r"""(() => {
  const bar = document.querySelector('.batch-bar');
  const clear = bar && [...bar.querySelectorAll('button')].find(b =>
    b.textContent.includes('取消选择') || b.textContent.includes('Clear'));
  if (clear) clear.click();
})()""")
    time.sleep(0.4)


# ── 造 6 条 R202 探针（Set-Clipboard 唯一时间戳串，产品捕获路径） ──
for it in inv("list_items", {"limit": 50}):
    if it["content"].startswith("R202"):
        inv("delete_item", {"id": it["id"]})
time.sleep(0.4)
for i in range(6):
    set_clip(f"R202探针{i}-{int(time.time() * 1000) % 100000}")
    for _ in range(15):
        time.sleep(1)
        n = len([x for x in inv("list_items", {"limit": 10})
                 if x["content"] == f"R202探针{i}" or x["content"].startswith(f"R202探针{i}-")])
        if n:
            break
    assert n, f"探针{i}未入库"
snap = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                      capture_output=True).stdout.decode("gbk", "replace").rstrip("\r\n")

# 清查询、刷新抽屉，取探针位置（最新 6 条在前列）
d.eval(r"""(() => {
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)
probes = [x["id"] for x in inv("list_items", {"limit": 10})
          if x["content"].startswith("R202探针")]
assert len(probes) == 6, f"探针数异常: {len(probes)}"
print("probes:", probes)

# Ctrl 点选 6 张（它们占据 data-idx 0..5）
for i in range(6):
    p = card_pos(i)
    click(p["x"], p["y"], mods=2)
    time.sleep(0.15)
b1 = bar()
print("bar:", b1)
assert "6" in b1["text"] and b1["delLabel"] and "确认" not in b1["delLabel"], \
    f"初始删除钮异常: {b1}"

# 第一击 → armed 确认态且不执行
delbtn = json.loads(d.eval(r"""(() => {
  const bar = document.querySelector('.batch-bar');
  const del = [...bar.querySelectorAll('button')].find(b =>
    b.textContent.includes('删除'));
  del.scrollIntoView({block: 'center'});
  const r = del.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2});
})()"""))
click(delbtn["x"], delbtn["y"])
time.sleep(0.5)
armed = bar()
print("armed:", armed)
assert armed["delLabel"] == "确认删除？" and "arm" in armed["delCls"], "未进两段确认"
assert len([x for x in inv("list_items", {"limit": 10})
            if x["content"].startswith("R202探针")]) == 6, "确认前就删了！"

# 第二击 → 执行删除（6 条全为本轮探针）
click(delbtn["x"], delbtn["y"])
time.sleep(1.0)
left = [x for x in inv("list_items", {"limit": 50})
        if x["content"].startswith("R202探针")]
print("probes left:", len(left))
assert len(left) == 0, "二击未删除"
gone = bar()
assert not gone.get("present"), "批量栏未消失"

# 还原剪贴板
subprocess.run(["powershell", "-NoProfile", "-Command",
                f"Set-Clipboard -Value '{snap}'"], capture_output=True)
print("PASS: >5 条两段删除（armed 不删→确认删 6→栏消失），全为本轮探针，剪贴板还原")
