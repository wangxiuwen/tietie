# 方向186 真机验证：托盘回粘不计 use_count（抽屉回粘仍计，对照组）
# 剧本（产品路径 paste_item + 桥核对；剪贴板快照还原）：
#   取条目 A（记 use_count 基线）
#   → 桥直调 paste_item(A, bumpUsage=false)（托盘同参路径）→ use_count 不变
#   → 桥直调 paste_item(A, bumpUsage=true)（抽屉默认路径）→ use_count +1
#   → 剪贴板快照还原
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


def clip():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                         capture_output=True)
    return out.stdout.decode("gbk", "replace").rstrip("\r\n")


def set_clip(text):
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Set-Clipboard -Value {json.dumps(text)}"], capture_output=True)


def inv(cmd, args=None):
    out = d.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} type")
    return json.loads(out)


snapshot = clip()
items = inv("list_items", {"limit": 30})
target = next(x for x in items if x["kind"] == "text")
base = target["use_count"]
print("target:", target["content"][:20], "| use_count:", base)

# 托盘路径：bumpUsage=false → 不计
inv("paste_item", {"id": target["id"], "bumpUsage": False})
time.sleep(0.8)
n1 = next(x for x in inv("list_items", {"limit": 30}) if x["id"] == target["id"])["use_count"]
print("after tray-path paste:", n1)
assert n1 == base, f"托盘路径误计: {n1} != {base}"

# 抽屉默认路径：缺省 true → +1
inv("paste_item", {"id": target["id"]})
time.sleep(0.8)
n2 = next(x for x in inv("list_items", {"limit": 30}) if x["id"] == target["id"])["use_count"]
print("after drawer-path paste:", n2)
assert n2 == base + 1, f"抽屉默认路径应计: {n2} != {base + 1}"

# use_count 还原（多退一）：无直接减命令——touch 一次 +1 已是默认行为，多余一次
# 属产品计数自然态？不：验证造成的 +1 应还原。用 SQL？禁写生产库。改为接受说明：
# 此 +1 由验证路径造成，等价于一次真实回粘计数，属产品语义内扰动，保留。
set_clip(snapshot)
print("PASS: 托盘路径不计 use_count、抽屉默认路径照计（+1 为验证内自然扰动），剪贴板还原")
