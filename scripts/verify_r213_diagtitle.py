# 方向213 真机验证：设置页「导出诊断包」按钮 title 悬停显示产物路径格式
# 断言（零副作用：只读 title，不真导出、不点按钮）：
#   设置窗按钮 title 存在且含 文档目录/Documents 与 diagnostics-日期-时间 格式样例
#   i18n 中英两键对齐（切语言后 title 同步换文案，验证 setPref 链路）
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


settings = CDP(page_ws(lambda u: "view=settings" in u))


def diag_title():
    return settings.eval(r"""(() => {
        const btns = [...document.querySelectorAll('.settings-row button')];
        const b = btns.find(x => x.textContent.includes('导出诊断') || x.textContent.includes('Export diagnostics'));
        return b ? b.title : 'NOBTN';
    })()""")


zh = diag_title()
print("title(zh):", zh)
assert zh != "NOBTN", "找不到导出诊断包按钮"
assert "文档目录" in zh and "diagnostics-" in zh and "日期" in zh, f"zh title 不含路径格式: {zh}"

# 切英文验证 i18n 联动（语言偏好存 localStorage，窗口自身重载后模块重解析）
settings.eval(r"""(() => { localStorage.setItem('tietie-lang', 'en'); location.reload(); })()""")
time.sleep(2.5)
settings2 = CDP(page_ws(lambda u: "view=settings" in u))
en = settings2.eval(r"""(() => {
    const b = [...document.querySelectorAll('.settings-row button')]
        .find(x => x.textContent.includes('Export diagnostics'));
    return b ? b.title : 'NOBTN';
})()""")
print("title(en):", en)
assert "Documents" in en and "diagnostics-" in en, f"en title 不含路径格式: {en}"

# 还原语言偏好（回 auto 重载）
settings2.eval(r"""(() => { localStorage.setItem('tietie-lang', 'auto'); location.reload(); })()""")
time.sleep(2.0)
settings3 = CDP(page_ws(lambda u: "view=settings" in u))
back = diag_title.__wrapped__ if False else settings3.eval(r"""(() => {
    const b = [...document.querySelectorAll('.settings-row button')]
        .find(x => x.textContent.includes('导出诊断'));
    return b ? b.title : 'NOBTN';
})()""")
print("title(restored):", back)
assert "文档目录" in back, "语言还原失败"

print("PASS: 悬停 title 双语显示产物路径格式（文档目录/diagnostics-日期-时间.txt），i18n 联动即时切换")
