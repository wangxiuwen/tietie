# 方向215 真机验证：抽屉链接卡 https 显示 🔒 锁标（http 不显示）
# 剧本：Set-Clipboard 造 https/http 双探针（捕获入库）→ 抽屉 DOM 断言
#   https 卡 .link-secure 存在（🔒 + title）且在 .link-domain 左侧
#   http 卡无 .link-secure
#   收尾：删双探针 + 还原剪贴板快照
import json
import subprocess
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223
TS = int(time.time())
P_HTTPS = f"https://example.com/r215h-{TS}"
P_HTTP = f"http://example.com/r215p-{TS}"


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


drawer = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))


def inv(cmd, args=None):
    out = drawer.eval(
        f"(async () => JSON.stringify(await window.__TAURI_INTERNALS__.invoke('{cmd}', "
        f"{json.dumps(args or {})})))()")
    if not isinstance(out, str):
        raise RuntimeError(f"{cmd} type")
    return json.loads(out)


def clip_snapshot():
    # UTF-8 console + errors=replace: GBK console bytes (Chinese on the board)
    # otherwise blow up the reader thread and silently drop the restore.
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw -ErrorAction SilentlyContinue"],
        capture_output=True)
    return r.stdout.decode("utf-8", errors="replace").strip("\r\n") or None


def clip_set(v):
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Set-Clipboard -Value '{v}'"], capture_output=True)


# 清残留探针
for it in inv("list_items", {"limit": 60}):
    if isinstance(it["content"], str) and "r215" in it["content"]:
        inv("delete_item", {"id": it["id"]})
snap = clip_snapshot()

try:
    # 双探针入库
    for probe in (P_HTTPS, P_HTTP):
        clip_set(probe)
        for _ in range(20):
            time.sleep(1)
            if any(x["content"] == probe for x in inv("list_items", {"limit": 5})):
                break
        else:
            raise RuntimeError(f"探针未入库: {probe}")
    print("both probes captured")

    # 抽屉显示 + DOM 断言
    drawer.eval('(async () => { await window.__TAURI_INTERNALS__.invoke("plugin:window|show"); })()')
    time.sleep(0.8)

    def card_state(probe):
        return drawer.eval(r"""((p) => {
            const cards = [...document.querySelectorAll('.card')];
            const c = cards.find(x => x.textContent.includes(p));
            if (!c) return JSON.stringify({found: false});
            const lock = c.querySelector('.link-secure');
            const dom = c.querySelector('.link-domain');
            const order = lock && dom
                ? (lock.compareDocumentPosition(dom) & Node.DOCUMENT_POSITION_FOLLOWING ? 'lock-first' : 'dom-first')
                : 'n/a';
            return JSON.stringify({
                found: true,
                lock: !!lock,
                glyph: lock ? lock.textContent.trim() : '',
                title: lock ? lock.title : '',
                color: lock ? getComputedStyle(lock).color : '',
                order: order,
            });
        })(""" + json.dumps(probe) + ")")

    hs = json.loads(card_state(P_HTTPS))
    hp = json.loads(card_state(P_HTTP))
    print("https card:", hs)
    print("http card :", hp)
    assert hs["found"], "https 探针卡未在抽屉找到"
    assert hs["lock"] and hs["glyph"] == "🔒" and "https" in hs["title"], f"https 卡锁标异常: {hs}"
    assert hs["order"] == "lock-first", f"锁标不在域名徽章左侧: {hs}"
    assert hs["color"] != "rgba(0, 0, 0, 0)" and hs["color"] != "", "锁标颜色未生效"
    assert hp["found"], "http 探针卡未在抽屉找到"
    assert not hp["lock"], f"http 卡不应有锁标: {hp}"

    print("PASS: https 卡 🔒（域名徽章左侧·绿·title）而 http 卡无")
finally:
    # 清探针 + 还原剪贴板
    for it in inv("list_items", {"limit": 60}):
        if isinstance(it["content"], str) and "r215" in it["content"]:
            inv("delete_item", {"id": it["id"]})
    if snap:
        clip_set(snap)
    print("cleanup done")
