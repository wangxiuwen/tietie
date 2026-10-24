# -*- coding: utf-8 -*-
# Direction 47 verification: render the deb desktop template with the
# documented tauri-bundler variables and validate it against the
# freedesktop Desktop Entry spec essentials (no desktop-file-utils on
# this machine / WSL — structural spec checks instead).
import json
import re

ROOT = r"D:\company\tuling\workspace\tietie"
tpl = open(ROOT + r"\src-tauri\assets\tietie.desktop", encoding="utf-8").read()
conf = json.load(open(ROOT + r"\src-tauri\tauri.conf.json", encoding="utf-8"))

# tauri-bundler supplies: name (productName), comment (description),
# exec, icon, categories (bundle.category)
vals = {
    "name": conf["productName"],
    "comment": conf["bundle"]["longDescription"],
    "exec": "/usr/bin/tietie",
    "icon": conf["identifier"],
    "categories": conf["bundle"]["category"],
}
rendered = re.sub(r"\{\{(\w+)\}\}", lambda m: vals[m.group(1)], tpl)
print(rendered)

lines = [l.rstrip() for l in rendered.splitlines()]
assert lines[0] == "[Desktop Entry]", "missing group header"
kv = {}
for l in lines[1:]:
    if not l:
        continue
    k, _, v = l.partition("=")
    assert re.fullmatch(r"[A-Za-z0-9-]+", k), f"bad key syntax: {k}"
    kv[k] = v

# spec: required keys for Type=Application
for req in ("Type", "Name", "Exec"):
    assert kv.get(req), f"missing required key {req}"
assert kv["Type"] == "Application"
# icon theme entry: hicolor icons are installed under the identifier
assert kv["Icon"] == "com.wangxiuwen.tietie", "icon name != identifier"
# registered main category present
assert "Utility" in kv["Categories"], "Categories must contain Utility"
# string-list keys use ; separators
for listkey in ("Categories", "Keywords"):
    assert re.fullmatch(r"[^;]+(;[^;]*)*;?", kv[listkey]), f"bad list: {kv[listkey]}"
# comment carries the product description, non-empty
assert len(kv["Comment"]) > 10, "Comment too short"
# exec must be absolute per spec recommendation for system-wide installs
assert kv["Exec"].startswith("/"), "Exec not absolute"
print("DESKTOP TEMPLATE CHECK PASS")
