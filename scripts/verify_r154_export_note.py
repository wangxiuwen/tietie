# 方向154 真机验证：导出便签附备注列（md 内联 📝，txt 加「备注：」行）
# 剧本（全程产品命令路径，验证后清理）：
#   hang_items 挂 1 条 → set_memo_note 写备注 → export_memos(md)
#   → 断言导出文件含 📝 与备注文本 → export_memos(txt) 断言「备注：」行
#   → remove_memo 还原 + 删除两个导出文件
import json
import os
import sys
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
NOTE = "R154验证备注-别删错人"

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and t["url"].endswith("localhost/"))
d = CDP(ws_url)


def invoke(cmd, args):
    out = d.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args)})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} -> {type(out).__name__}")
    return json.loads(out)


base = invoke("list_memos", {})
assert base == [], f"基线非空: {base}"

# 1) 挂一条 + 写备注（都是产品命令路径）
first_text = invoke("list_items", {"limit": 10})[0]["id"]
n = invoke("hang_items", {"ids": [first_text]})
assert n == 1, f"hang_items 返回 {n}"
memo = invoke("list_memos", {})[0]
invoke("set_memo_note", {"id": memo["id"], "note": NOTE})
got = invoke("list_memos", {})[0]["note"]
assert got == NOTE, f"备注未写入: {got!r}"

# 2) md 导出：内联 📝
md_path = invoke("export_memos", {})
md = open(md_path, encoding="utf-8").read()
print("md path:", md_path)
print("md lines:", [ln for ln in md.splitlines() if ln.strip()][-2:])
assert "📝" in md and NOTE in md, "md 导出缺备注列"
assert md.startswith("# 贴贴便签"), "md 头异常"

# 3) txt 导出：备注： 行
txt_path = invoke("export_memos", {"format": "txt"})
txt = open(txt_path, encoding="utf-8").read()
print("txt path:", txt_path)
assert f"备注：{NOTE}" in txt, "txt 导出缺备注行"
print("PASS: md 内联 📝 + txt「备注：」行均含备注列")

# 4) 清理：便签还原 + 删导出文件（本验证自建产物）
invoke("remove_memo", {"id": memo["id"]})
assert invoke("list_memos", {}) == [], "便签未清理干净"
for p in (md_path, txt_path):
    os.remove(p)
print("PASS: 便签清零、导出文件已删，现场还原")
