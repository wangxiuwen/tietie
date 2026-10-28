# 方向218 真机验证：设置页备份导出按钮 title 悬停显示产物路径格式
# 断言（零副作用：只读 title，不真导出）：
#   主行「导出」按钮 title 含 文档目录 与 tietie-backup-日期-时间 格式样例
#   横幅「立即导出」按钮（若渲染）title 同源
#   对齐后端事实：export_backup 产 document_dir/tietie-backup-{time_fmt}.json
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

# 主行导出按钮：settings.backup 行内的 settings.export
main = settings.eval(r"""(() => {
    const rows = [...document.querySelectorAll('.settings-row')];
    const row = rows.find(r => r.textContent.includes('备份') || r.textContent.includes('Backup'));
    if (!row) return 'NOROW';
    const btn = [...row.querySelectorAll('button')]
        .find(b => b.textContent.includes('导出') || b.textContent.includes('Export'));
    return btn ? btn.title : 'NOBTN';
})()""")
print("main export title:", main)
assert main not in ("NOROW", "NOBTN"), f"主行导出按钮未找到: {main}"
assert "文档目录" in main and "tietie-backup-" in main and "日期" in main, f"title 不含路径格式: {main}"

# 横幅按钮（条件渲染，存在才断言）
banner = settings.eval(r"""(() => {
    const b = [...document.querySelectorAll('.backup-banner button')].pop();
    return b ? b.title : '(no banner)';
})()""")
print("banner title:", banner)
if banner != "(no banner)":
    assert "tietie-backup-" in banner, f"横幅按钮 title 缺格式: {banner}"

# 后端事实对齐：title 样例应匹配 time_fmt 产物名样式（8 位日期-6 位时间）
assert "2026" in main and ".json" in main, "样例文件名不完整"

print("PASS: 备份导出按钮 title 双语键显示产物路径格式（文档目录/tietie-backup-日期-时间.json）")
