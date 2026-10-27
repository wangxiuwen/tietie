# 方向171 真机验证：托盘搜索框 ↑ 召回抽屉同款搜索历史
# 剧本（产品路径 + localStorage 快照还原）：
#   抽屉：注入查询甲 → invoke show_drawer（提交触发点）→ 注入乙 → 再 invoke
#   → 断言 localStorage tietie.searchHist 末两位 = [甲, 乙]
#   托盘：清空查询 → 合成 ↑ → 查询=乙（最新）→ 再 ↑ → 查询=甲（更旧）
#   → 清空托盘查询 + localStorage 还原快照
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
KEY = "tietie.searchHist"


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


d = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))
tray = CDP(page_ws(lambda u: "view=tray" in u))
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.8)


def drawer_set_query(q):
    got = d.eval(rf"""(() => {{
  const i = document.querySelector('.search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, {json.dumps(q)});
  i.dispatchEvent(new Event('input', {{bubbles: true}}));
  return i.value;
}})()""")
    assert got == q, got
    time.sleep(0.3)


# localStorage 快照（还原用）——抽屉与托盘同源共享
snapshot = d.eval(f"localStorage.getItem({json.dumps(KEY)})")
print("snapshot:", snapshot)

A, B = "R171hist甲", "R171hist乙"
drawer_set_query(A)
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.6)
drawer_set_query(B)
d.eval('window.__TAURI_INTERNALS__.invoke("show_drawer")')
time.sleep(0.6)

# 抽屉侧写入断言
hist = json.loads(d.eval(f"localStorage.getItem({json.dumps(KEY)})") or "[]")
print("drawer localStorage tail:", hist[-2:])
assert hist[-2:] == [A, B], f"提交镜像异常: {hist}"

# 托盘窗读同一 storage（跨窗共享断言）
tray_hist = tray.eval(f"localStorage.getItem({json.dumps(KEY)})")
assert tray_hist is not None and json.loads(tray_hist)[-2:] == [A, B], "托盘读不到共享历史"

# 托盘：清查询 → 合成 ↑×2 召回
tray.eval(r"""(() => {
  const i = document.querySelector('.po-search input, input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
  i.focus();
})()""")
time.sleep(0.4)


def tray_up():
    tray.eval(r"""(() => {
  const i = document.querySelector('.po-search input, input');
  i.dispatchEvent(new KeyboardEvent('keydown',
    {key: 'ArrowUp', bubbles: true, cancelable: true}));
})()""")
    time.sleep(0.3)
    return tray.eval(r"""document.querySelector('.po-search input, input').value""")


v1 = tray_up()
print("↑#1:", v1)
assert v1 == B, f"首次 ↑ 应召回最新 {B}: {v1!r}"
v2 = tray_up()
print("↑#2:", v2)
assert v2 == A, f"二次 ↑ 应召回更旧 {A}: {v2!r}"

# 还原：清托盘查询 + localStorage 回快照
tray.eval(r"""(() => {
  const i = document.querySelector('.po-search input, input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(i, '');
  i.dispatchEvent(new Event('input', {bubbles: true}));
})()""")
if snapshot is None:
    d.eval(f"localStorage.removeItem({json.dumps(KEY)})")
else:
    d.eval(f"localStorage.setItem({json.dumps(KEY)}, {json.dumps(snapshot)})")
time.sleep(0.3)
# 抽屉查询也清掉
drawer_set_query("")
print("PASS: 抽屉提交镜像 localStorage、托盘 ↑ 召回最新/更旧两连、快照还原")
