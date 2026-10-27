# 方向179 真机验证：诊断导出后 reveal 定位文件（已具备收口轮）
# 已具备：方向134（9272f29）出生即「export_diagnostics → reveal_path」链
# （Settings.tsx 657-659：导出成功后 invoke("reveal_path")）。实证走命令级：
#   bridge export_diagnostics → 返回真实路径 + 文件在盘
#   → bridge reveal_path(该路径) → Ok（资源管理器定位链路畅通）
#   → 删除导出产物还原（Explorer 打开一次为产品设计行为）
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


path = inv("export_diagnostics", {})
print("exported:", path)
assert path and os.path.isfile(path), f"产物不存在: {path}"
head = open(path, encoding="utf-8", errors="replace").read(200)
print("head:", head[:80].replace("\n", " | "))
assert "诊断" in head or "diagnostics" in head.lower() or "tietie" in head.lower(), \
    "产物内容异常"

rev = d.eval(rf"""(async () => {{
  try {{
    await window.__TAURI_INTERNALS__.invoke('reveal_path', {{path: {json.dumps(path)}}});
    return 'ok';
  }} catch (e) {{ return 'ERR ' + String(e); }}
}})()""")
print("reveal:", rev)
assert rev == "ok", rev

os.remove(path)
print("PASS: 导出→文件落盘→reveal 定位链路命令级全通（方向134 起已具备），产物已删")
