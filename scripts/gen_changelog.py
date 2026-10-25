# -*- coding: utf-8 -*-
"""Generate CHANGELOG.md from the 迭代记录 section of
docs/ITERATION_BACKLOG.md (direction 57). Manual trigger:

    py -3 scripts/gen_changelog.py          # write CHANGELOG.md
    py -3 scripts/gen_changelog.py --check  # exit 1 when stale (CI-able)

The whole file is regenerated every run — edit the backlog, not this file.
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKLOG = os.path.join(ROOT, "docs", "ITERATION_BACKLOG.md")
OUT = os.path.join(ROOT, "CHANGELOG.md")
REPO = "wangxiuwen/tietie"

ROW = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.+)$")
SHA = re.compile(r"^[0-9a-f]{7,40}$")
HEADER = """# Changelog

> 由 docs/ITERATION_BACKLOG.md 的迭代记录生成——`py -3 scripts/gen_changelog.py`，请勿手改。

"""


def parse_rows():
    lines = io.open(BACKLOG, encoding="utf-8").read().splitlines()
    rows, inside = [], False
    for ln in lines:
        if ln.strip() == "## 迭代记录":
            inside = True
            continue
        if inside and ln.startswith("## "):
            break
        if not inside:
            continue
        m = ROW.match(ln)
        if m:
            rows.append(m.groups())
    return rows


def render(rows):
    out = [HEADER]
    cur = None
    for date, direction, sha, note in rows:  # backlog is newest-first
        if date != cur:
            cur = date
            out.append("## %s\n" % date)
        if SHA.match(sha):
            link = "[`%s`](https://github.com/%s/commit/%s)" % (sha, REPO, sha)
        else:
            link = "`%s`" % sha
        out.append("- **%s** %s %s\n" % (direction.strip(), link, note.strip()))
    return "\n".join(out) + "\n"


def main():
    body = render(parse_rows())
    if "--check" in sys.argv:
        current = (
            io.open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        )
        if current != body:
            print("CHANGELOG.md is stale — run: py -3 scripts/gen_changelog.py")
            return 1
        print("CHANGELOG.md up to date (%d entries)" % len(parse_rows()))
        return 0
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(body)
    print("CHANGELOG.md written (%d entries)" % len(parse_rows()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
