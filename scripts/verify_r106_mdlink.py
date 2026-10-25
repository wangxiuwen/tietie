# -*- coding: utf-8 -*-
"""R106 / direction 100 verification: markdown export renders links as
[label](url) with a readable label derived from the URL.

Invokes the real export_selected_markdown with the production link item plus
a text item, reads the produced file, asserts the link line format, then
deletes the export file (net-zero).
"""
import sys, time, json, os, glob, re, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def main():
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if "view=library" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "library target not found"

    items = ws.invoke("list_items", {"limit": 200})
    link = next((x for x in items if x["kind"] == "link"), None)
    text = next((x for x in items if x["kind"] == "text"), None)
    assert link, "no link item in production data"
    ids = [link["id"]] + ([text["id"]] if text else [])
    print("export ids:", ids, "| link url:", link["content"][:60])

    path = ws.invoke("export_selected_markdown", {"ids": ids})
    assert isinstance(path, str) and path, f"export failed: {path!r}"
    print("exported:", path)

    md = open(path, encoding="utf-8").read()
    m = re.search(r"^- \[(.+?)\]\((.+)\)$", md, re.M)
    assert m, f"no markdown link line:\n{md[:300]}"
    label, target = m.group(1), m.group(2)
    print("link line:", f"[{label}]({target[:50]}…)")
    assert target == link["content"], f"target != url: {target!r}"
    assert not label.startswith(("http://", "https://", "www.")) and "://" not in label, \
        f"label not readable: {label!r}"
    assert label in link["content"], "label should be derived from the url"

    os.remove(path)
    assert not os.path.exists(path)
    print("R106 VERIFY PASS: link exported as [readable-label](full-url), file cleaned")

if __name__ == "__main__":
    main()
