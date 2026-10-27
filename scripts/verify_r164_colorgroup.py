# 方向164 真机验证：导出 md 按颜色分组（## 色名 小节）
# 剧本（产品命令路径，结束清理还原）：
#   挂 1 条（accent 蓝）+ add_memo_direct 1 条指定绿
#   → export_memos(md) 断言两个 ## 色名 小节、各自内容正确、无游离 bullet
#   → export_memos(txt) 回归断言仍平铺无 ## 行
#   → remove_memo×2 + 删两个导出文件
import json
import os
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and (t["url"].endswith("/") or "view=" not in t["url"]))
d = CDP(ws_url)


def invoke(cmd, args=None):
    out = d.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} -> {type(out).__name__}")
    return json.loads(out)


assert invoke("list_memos", {}) == [], "基线便签非空，先清场"

first = invoke("list_items", {"limit": 10})[0]["id"]
assert invoke("hang_items", {"ids": [first]}) == 1
invoke("add_memo_direct", {"content": "R164绿组探针", "remindAt": None, "color": "#34c759"})
time.sleep(0.6)
memos = invoke("list_memos", {})
print("memos:", [(m["content"][:12], m["color"]) for m in memos])
assert len(memos) == 2
colors = {m["color"] for m in memos}
assert "#34c759" in colors and len(colors) == 2

md_path = invoke("export_memos", {})
md = open(md_path, encoding="utf-8").read()
print("---- md ----")
print(md)
# Python 侧镜像 Rust color_name（8 色板+hex 兜底）
CN = {"#007aff": "蓝", "#0078d4": "蓝", "#34c759": "绿", "#ff9500": "橙",
      "#ff2d55": "红", "#af52de": "紫", "#5856d6": "靛", "#8e8e93": "灰",
      "#ffcc00": "黄"}
name_of = lambda c: CN.get(c, c)
green = next(m for m in memos if m["color"] == "#34c759")
other = next(m for m in memos if m["color"] != "#34c759")
assert md.startswith("# 贴贴便签（2 张）"), "md 头异常"
gi = md.index("## 绿（1 张）")
oi = md.index(f"## {name_of(other['color'])}（1 张）")
assert md.index("R164绿组探针") > gi, "绿探针不在绿小节"
other_head = other["content"].splitlines()[0][:10]
assert md.index(other_head) > oi, f"另一条不在其色小节（{name_of(other['color'])}）"
assert abs(gi - oi) > 4, "两个小节标题挤在一起"
# 每条 bullet 必须归属某小节：正文区不以 - 开头（游离 bullet 检查）
body_after_header = md.split("\n\n", 1)[1]
assert body_after_header.lstrip().startswith("##"), "存在未分组的游离 bullet"

txt_path = invoke("export_memos", {"format": "txt"})
txt = open(txt_path, encoding="utf-8").read()
assert "##" not in txt and "贴贴便签（2 张）" in txt, "txt 被分节改动（回归）"
print("PASS: md 按颜色分节（蓝/绿 各一）、txt 保持平铺")

invoke("remove_memo", {"id": memos[0]["id"]})
invoke("remove_memo", {"id": memos[1]["id"]})
time.sleep(0.5)
assert invoke("list_memos", {}) == [], "清理未完成"
for p in (md_path, txt_path):
    os.remove(p)
print("PASS: 现场还原（便签清零、导出文件已删）")
