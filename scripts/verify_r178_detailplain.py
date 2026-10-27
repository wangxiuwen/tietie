# 方向178 真机验证：便签详情「复制（去格式）」一键复制完整原文
# 剧本（产品数据 + 可信点击 + 剪贴板对照，结束全还原）：
#   add_memo_direct 造带 Markdown 标记便签（**粗** `码` [标签](url)）
#   → 双击开详情 →「取消编辑」退出编辑态 → 详情按钮组出现「复制（去格式）」
#   → 可信点击该钮（✓ 反馈）→ Get-Clipboard == 剥标记纯文本（URL 保留）
#   → 还原剪贴板快照 + remove_memo
import json
import subprocess
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
RAW = "开头**加粗**中段`代码`结尾看 [标签](https://example.com/r178) 收"
WANT = "开头加粗中段代码结尾看 https://example.com/r178 收"


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


line = CDP(page_ws(lambda u: "view=line" in u))
main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))


def inv(cmd, args=None):
    out = main.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} type")
    return json.loads(out)


def clip():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                         capture_output=True)
    return out.stdout.decode("gbk", "replace").rstrip("\r\n")


def set_clip(text):
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Set-Clipboard -Value {json.dumps(text)}"], capture_output=True)


# 基线清场
for m in inv("list_memos", {}):
    inv("remove_memo", {"id": m["id"]})
time.sleep(0.5)
snapshot = clip()

inv("add_memo_direct", {"content": RAW, "remindAt": None, "color": None})
time.sleep(0.5)
memo = inv("list_memos", {})[0]
assert memo["content"] == RAW

line.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
time.sleep(0.5)

# 双击开详情（编辑态）→ 取消编辑退出（色板/按钮组才渲染）
line.eval(r"""(() => {
  const c = document.querySelector('.line-card:not(.composer)');
  if (c) c.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
})()""")
time.sleep(0.5)
n = line.eval(r"""(() => {
  const b = [...document.querySelectorAll('.line-detail .btn.ghost')]
    .find(x => x.textContent.includes('取消'));
  if (!b) return 'nobtn';
  b.click();
  return 'ok';
})()""")
assert n == "ok", n
time.sleep(0.5)

btn = json.loads(line.eval(r"""(() => {
  const b = [...document.querySelectorAll('.line-detail .btn')]
    .find(x => x.textContent.trim() === '复制（去格式）');
  if (!b) return 'NOBTN';
  b.scrollIntoView({block: 'center'});
  const r = b.getBoundingClientRect();
  return JSON.stringify({x: r.x + r.width / 2, y: r.y + r.height / 2});
})()"""))
print("copyPlain btn:", btn)
assert btn != "NOBTN", "复制（去格式）按钮缺失"

# 可信点击（剪贴板 API 需用户激活）
for typ in ("mousePressed", "mouseReleased"):
    line.ws.send(json.dumps({"id": 9901, "method": "Input.dispatchMouseEvent",
                             "params": {"type": typ, "button": "left",
                                        "buttons": 1 if typ == "mousePressed" else 0,
                                        "clickCount": 1, "x": btn["x"], "y": btn["y"]}}))
    line.ws.recv_text()
    time.sleep(0.12)
time.sleep(0.5)

feedback = line.eval(r"""(() => JSON.stringify([...document.querySelectorAll('.line-detail .btn')]
  .map(b => b.textContent.trim())))()""")
print("buttons after:", feedback)
assert "已复制" in feedback or any("✓" in x for x in json.loads(feedback)) or "已复制" in feedback, \
    "无复制反馈"
got = clip()
print("clipboard:", got)
assert got == WANT, f"剪贴板不符:\n{got!r}\n期望\n{WANT!r}"

# 还原
inv("remove_memo", {"id": memo["id"]})
time.sleep(0.4)
set_clip(snapshot)
assert inv("list_memos", {}) == []
print("PASS: 详情复制（去格式）→ 剪贴板=剥标记全文（URL 保留），✓ 反馈，现场还原")
