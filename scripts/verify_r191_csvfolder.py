# 方向191 真机验证：CSV 导出补 folder 列
# 剧本（产品命令造夹/归条 → 导出断言 → 全还原）：
#   create_folder → 选一条 A set_item_folder(A, fid)
#   → export_selected_csv([A 的 id, 另一条无夹条目 B])
#   → 断言：表头含 folder 列；A 行末列 == 夹名；B 行末列为空
#   → A 移出夹、delete_folder、删导出文件
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


def inv(cmd, args=None):
    out = d.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} type")
    return json.loads(out)


# 清残留夹
for f in inv("list_folders", {}):
    inv("delete_folder", {"id": f["id"]})
time.sleep(0.3)

FNAME = "R191夹"
fid = inv("create_folder", {"name": FNAME, "color": "#34c759"})
items = inv("list_items", {"limit": 20})
a = items[0]
b = next(x for x in items if x.get("folder_id") is None and x["id"] != a["id"])
inv("set_item_folder", {"id": a["id"], "folderId": fid})
time.sleep(0.4)

path = inv("export_selected_csv", {"ids": [a["id"], b["id"]]})
print("csv:", path)
rows = open(path, encoding="utf-8-sig").read().strip().splitlines()
print("rows:", rows)
header = rows[0]
assert header.endswith(",folder"), f"表头缺 folder 列: {header}"
assert header.count(",") == 5, f"列数异常: {header}"

# A 行：末列 == 夹名；B 行：末列为空
def last_cell(row):
    # 简单 CSV：不在引号内的最后一个逗号后即末列（夹名无逗号）
    if row.count(",") >= 5:
        return row.rsplit(",", 1)[1]
    return None

la, lb = last_cell(rows[1]), last_cell(rows[2])
print("A 末列:", repr(la), "| B 末列:", repr(lb))
assert la == FNAME, f"A 行 folder 列异常: {la!r}"
assert lb == "", f"B 行 folder 列应为空: {lb!r}"

# 还原
inv("set_item_folder", {"id": a["id"], "folderId": None})
inv("delete_folder", {"id": fid})
time.sleep(0.3)
os.remove(path)
assert inv("list_folders", {}) == []
print("PASS: CSV 表头含 folder、A 行=夹名、B 行空、夹与文件全还原")
