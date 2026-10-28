# 方向221 真机验证：Library 行 hover 显现 × 快删（对齐 212）
# 剧本（零副作用：探针即删除对象）：
#   预清残留探针 → Set-Clipboard 造唯一探针入库 → Library 行出现
#   → 基线（指针远角）× visibility hidden
#   → 可信 mouseMoved 移到该行 → × visible
#   → 可信点 × → 行消失 + 桥条目删除归零 → 剪贴板还原
import json
import subprocess
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
TS = int(time.time())
PROBE = f"R221行删探针{TS}"


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


lib = CDP(page_ws(lambda u: "view=library" in u))
main = CDP(page_ws(lambda u: u.rstrip("/").endswith("tauri.localhost")))


def raw(page, method, params):
    page.seq += 1
    rid = page.seq
    page.ws.send(json.dumps({"id": rid, "method": method, "params": params}))
    while True:
        m = json.loads(page.ws.recv_text())
        if m.get("id") == rid:
            if "error" in m:
                raise RuntimeError(m["error"])
            return m.get("result", {})


def inv(cmd, args=None):
    out = main.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} type")
    return json.loads(out)


def clip_snapshot():
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw -ErrorAction SilentlyContinue"],
        capture_output=True)
    return r.stdout.decode("utf-8", errors="replace").strip("\r\n") or None


def clip_set(v):
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Set-Clipboard -Value '{v}'"], capture_output=True)


# 预清 + 快照
for it in inv("list_items", {"limit": 60}):
    if isinstance(it["content"], str) and "R221" in it["content"]:
        inv("delete_item", {"id": it["id"]})
snap = clip_snapshot()

try:
    clip_set(PROBE)
    pid = None
    for _ in range(20):
        time.sleep(1)
        f = [x["id"] for x in inv("list_items", {"limit": 5}) if x["content"] == PROBE]
        if f:
            pid = f[0]
            break
    assert pid, "探针未入库"
    print("probe id:", pid)

    # Library 搜索定位探针行（新条目在最上，直接找文本）
    time.sleep(0.5)
    pos = json.loads(lib.eval(r"""((p) => {
        const rows = [...document.querySelectorAll('.lib-table tbody tr')];
        const tr = rows.find(r => r.textContent.includes(p));
        if (!tr) return JSON.stringify({found: false});
        tr.scrollIntoView({block: 'center'});
        const b = tr.getBoundingClientRect();
        const btn = tr.querySelector('.lib-row-del');
        const bb = btn.getBoundingClientRect();
        return JSON.stringify({found: true, row: {x: b.left + b.width / 2, y: b.top + b.height / 2},
                               del: {x: bb.left + bb.width / 2, y: bb.top + bb.height / 2}});
    })(""" + json.dumps(PROBE) + ")"))
    assert pos["found"], "探针行未找到"
    time.sleep(0.3)

    # 基线：指针远角 → × hidden
    raw(lib, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 10, "y": 300})
    time.sleep(0.3)
    st = json.loads(lib.eval(r"""((p) => {
        const rows = [...document.querySelectorAll('.lib-table tbody tr')];
        const tr = rows.find(r => r.textContent.includes(p));
        const btn = tr && tr.querySelector('.lib-row-del');
        return JSON.stringify({vis: btn ? getComputedStyle(btn).visibility : 'n/a'});
    })(""" + json.dumps(PROBE) + ")"))
    print("baseline × visibility:", st)
    assert st["vis"] == "hidden", f"基线未隐藏: {st}"

    # 可信移入行 → × visible
    raw(lib, "Input.dispatchMouseEvent", {"type": "mouseMoved",
                                          "x": pos["row"]["x"], "y": pos["row"]["y"]})
    time.sleep(0.4)
    st = json.loads(lib.eval(r"""((p) => {
        const rows = [...document.querySelectorAll('.lib-table tbody tr')];
        const tr = rows.find(r => r.textContent.includes(p));
        const btn = tr && tr.querySelector('.lib-row-del');
        return JSON.stringify({vis: btn ? getComputedStyle(btn).visibility : 'n/a'});
    })(""" + json.dumps(PROBE) + ")"))
    print("hover × visibility:", st)
    assert st["vis"] == "visible", f"hover 未显现: {st}"

    # 可信点 × → 行消失 + 桥归零
    raw(lib, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": pos["del"]["x"], "y": pos["del"]["y"],
                                          "button": "left", "buttons": 1, "clickCount": 1})
    raw(lib, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pos["del"]["x"], "y": pos["del"]["y"],
                                          "button": "left", "buttons": 0, "clickCount": 1})
    time.sleep(0.8)
    gone = lib.eval(r"""((p) => {
        const rows = [...document.querySelectorAll('.lib-table tbody tr')];
        return rows.some(r => r.textContent.includes(p)) ? 'n' : 'y';
    })(""" + json.dumps(PROBE) + ")")
    left = [x["id"] for x in inv("list_items", {"limit": 60}) if x["content"] == PROBE]
    print("row gone:", gone, "| bridge left:", len(left))
    assert gone == "y" and not left, "删除未生效"

    print("PASS: hover 显 × / 可信点删行删库（探针即删除对象）")
finally:
    for it in inv("list_items", {"limit": 60}):
        if isinstance(it["content"], str) and "R221" in it["content"]:
            inv("delete_item", {"id": it["id"]})
    if snap:
        clip_set(snap)
    print("cleanup done")
