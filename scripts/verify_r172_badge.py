# 方向172 真机验证：便签到点后托盘图标角标提示张数
# 链路验证（产品数据 → 前端推导 → Rust 命令，日志观测）：
#   ★桥属性钩子不可用：tauri 运行时会重置 __TAURI_INTERNALS__ 对象（本轮实证），
#   故改为读生产日志 tietie.log 的 "tray badge -> N" 序列。
#   → add_memo_direct 造 6 秒后到点便签（remindAt=绝对秒）
#   → 等 9s：晾衣架卡获 due 类 + 日志出现 "tray badge -> 1"
#   → remove_memo：日志追加 "tray badge -> 0"（清除）
import json
import os
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
LOG = os.path.expandvars(r"%LOCALAPPDATA%\com.wangxiuwen.tietie\tietie.log")


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


line = CDP(page_ws(lambda u: "view=line" in u))
main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))


def invoke_on(ws, cmd, args=None):
    out = ws.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} -> {type(out).__name__}")
    return json.loads(out)


def log_tail():
    with open(LOG, encoding="utf-8", errors="replace") as f:
        return f.read()


# 基线清场
for m in invoke_on(main, "list_memos", {}):
    invoke_on(main, "remove_memo", {"id": m["id"]})
time.sleep(1.0)
assert invoke_on(main, "list_memos", {}) == []

# 命令级冒烟（真换图标路径畅通）
smoke = main.eval(r"""(async () => {
  try { await window.__TAURI_INTERNALS__.invoke('set_tray_badge', {n: 0}); return 'ok'; }
  catch (e) { return 'ERR ' + String(e); }
})()""")
assert smoke == "ok", smoke
print("command smoke: ok")
tail0 = log_tail().count("tray badge ->")
print("baseline badge log lines:", tail0)

# 造 6 秒后到点的便签
remind_at = int(time.time()) + 6
invoke_on(main, "add_memo_direct", {
    "content": "R172角标探针", "remindAt": remind_at, "color": None})
time.sleep(0.6)

print("waiting for due ...")
time.sleep(9)
due_card = line.eval(r"""document.querySelector('.line-card.due') ? 1 : 0""")
print("due class:", due_card)
assert str(due_card) == "1", "到点卡未标记 due（推导前提缺失）"
seg = log_tail().split("tray badge ->")[1:]  # 每条 " N" 片段
nums = [int(s.strip().split()[0]) for s in seg]
print("badge log sequence (tail):", nums[-4:])
assert 1 in nums[tail0:], f"到点后未见 badge->1: {nums[-6:]}"

# 清理：删便签 → 追加 badge->0
memo = invoke_on(main, "list_memos", {})[0]
invoke_on(main, "remove_memo", {"id": memo["id"]})
time.sleep(2.5)
nums2 = [int(s.strip().split()[0]) for s in log_tail().split("tray badge ->")[1:]]
print("final sequence (tail):", nums2[-4:])
assert nums2[-1] == 0, f"清理后未见 badge->0: {nums2[-6:]}"
print("PASS: 到点 → 日志 badge->1（含真实换图标执行）→ 删除 → badge->0，全链实测")
