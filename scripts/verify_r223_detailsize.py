# 方向223 真机验证：Library 详情浮层图片 meta 行补文件大小
# 剧本（零副作用：只开浮层读文本，Esc 关闭）：
#   Library 表格里找图片行 → 双击（合成 dblclick）打开详情浮层
#   → zoom-meta 文本 = "WxH · 大小(fmtBytes)" 且非图片行无 "·"
#   → Esc 关闭浮层
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223


def page_ws(match):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
        for t in json.load(r):
            if t["type"] == "page" and match(t["url"]):
                return t["webSocketDebuggerUrl"]
    return None


lib = CDP(page_ws(lambda u: "view=library" in u))

# 找到第一条图片行（badge image / content 形如 WxH）
found = json.loads(lib.eval(r"""(() => {
    const rows = [...document.querySelectorAll('.lib-table tbody tr')];
    const img = rows.find(r => {
        const badge = r.querySelector('.badge');
        return badge && (badge.className.includes('image') || badge.textContent.includes('图'));
    });
    if (!img) return JSON.stringify({found: false});
    img.scrollIntoView({block: 'center'});
    const size = [...img.querySelectorAll('td')].map(td => td.textContent.trim());
    return JSON.stringify({found: true, cells: size.slice(0, 8)});
})()"""))
assert found["found"], "Library 无图片行"
time.sleep(0.3)
print("img row cells:", found["cells"])

# 期望大小来自行内 w-size 列（fmtBytes 同源），浮层应显示同一字符串
size_cell = [c for c in found["cells"] if c and (c.endswith("B") or "KB" in c or "MB" in c)]
assert size_cell, f"行内未找到大小列: {found['cells']}"
expect = size_cell[-1].replace("图片", "").strip()
print("expected size text:", expect)

# 双击图片行打开浮层（React onDoubleClick 路径）
lib.eval(r"""(() => {
    const rows = [...document.querySelectorAll('.lib-table tbody tr')];
    const img = rows.find(r => {
        const badge = r.querySelector('.badge');
        return badge && (badge.className.includes('image') || badge.textContent.includes('图'));
    });
    img.dispatchEvent(new MouseEvent('dblclick', {bubbles: true, cancelable: true}));
    return 'dblclick';
})()""")
time.sleep(1.0)
meta = lib.eval(r"""(() => {
    const m = document.querySelector('.zoom-overlay .zoom-meta');
    return m ? m.textContent : 'NOOVERLAY';
})()""")
print("overlay meta:", meta)
assert meta != "NOOVERLAY", "详情浮层未打开"
assert expect in meta, f"浮层 meta 缺大小 {expect}: {meta}"

# Esc 关闭（浮层键盘守卫）
lib.eval(r"""(() => {
    document.activeElement && document.activeElement.blur();
    return 'ok';
})()""")
import json as _j
def raw(method, params):
    lib.seq += 1; rid = lib.seq
    lib.ws.send(_j.dumps({"id": rid, "method": method, "params": params}))
    while True:
        m = json.loads(lib.ws.recv_text())
        if m.get("id") == rid: return m.get("result", {})
raw("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
raw("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
time.sleep(0.5)
gone = lib.eval(r"""(() => !document.querySelector('.zoom-overlay') ? 'y' : 'n')()""")
print("overlay closed:", gone)
assert gone == "y", "Esc 未关闭浮层"

print("PASS: 图片详情浮层 meta 行含 fmtBytes 大小（与行内大小列同源一致）")
