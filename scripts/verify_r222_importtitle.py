# 方向222 真机验证：设置页导入按钮 title 悬停说明导入规则
# 断言（零副作用：只读 title，不真导入）：
#   备份行「导入」按钮 title 含 文档目录/最新 tietie-backup 规则与
#   合并语义（仅补入）——文案先对源码核实（restore_backup 存在即跳过
#   + INSERT OR IGNORE），不得凭空断言
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

tip = settings.eval(r"""(() => {
    const rows = [...document.querySelectorAll('.settings-row')];
    const row = rows.find(r => r.textContent.includes('备份') || r.textContent.includes('Backup'));
    if (!row) return 'NOROW';
    const btn = [...row.querySelectorAll('button')]
        .find(b => b.textContent.includes('导入') || b.textContent.includes('Import'));
    return btn ? btn.title : 'NOBTN';
})()""")
print("import title:", tip)
assert tip not in ("NOROW", "NOBTN"), f"导入按钮未找到: {tip}"
# 语义断言对齐后端三事实：文档目录、挑最新、仅补入
assert "文档目录" in tip, f"未说明来源目录: {tip}"
assert "最新" in tip and "tietie-backup-" in tip, f"未说明挑选规则: {tip}"
assert "补入" in tip, f"未说明合并语义: {tip}"

# 导出按钮 title 仍在（218 回归不回退）
exp = settings.eval(r"""(() => {
    const rows = [...document.querySelectorAll('.settings-row')];
    const row = rows.find(r => r.textContent.includes('备份') || r.textContent.includes('Backup'));
    const btn = [...row.querySelectorAll('button')]
        .find(b => b.textContent.includes('导出') || b.textContent.includes('Export'));
    return btn ? btn.title : 'NOBTN';
})()""")
print("export title (regression):", exp)
assert "tietie-backup-" in exp, "218 导出 title 回退"

print("PASS: 导入按钮 title 三事实（文档目录/挑最新/仅补入）+ 218 导出 title 无回退")
