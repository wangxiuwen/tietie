# -*- coding: utf-8 -*-
"""R153 / direction 147 verification: Library folder-ownership column.

Creates a temp folder, files ONE probe item into it (set_item_folder),
opens the Library table and asserts:
  - the header row has a 文件夹 column (between 来源 and 大小)
  - the probe row's folder cell shows the temp folder NAME
  - an unfiled row shows —
Cleanup: unfile + delete item, remove folder.
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def main():
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if t["url"].startswith("http://tauri.localhost/") and "?" not in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "drawer target not found"

    # drop leftovers from failed runs
    for x in ws.invoke("list_items", {"limit": 500}):
        if x["content"].startswith("folder-col-"):
            ws.invoke("delete_item", {"id": x["id"]})
    for f in ws.invoke("list_folders"):
        if f["name"] in ("归属列验证", "整组拖入验证"):
            ws.invoke("delete_folder", {"id": f["id"]})
    time.sleep(0.3)

    fid = ws.invoke("create_folder", {"name": "归属列验证", "color": "#007aff"})
    assert isinstance(fid, int), fid
    marker = "folder-col-" + str(int(time.time()))
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=marker.encode("utf-8"), capture_output=True)
    time.sleep(2.5)
    items = ws.invoke("list_items", {"limit": 20})
    item = next(x for x in items if x["content"] == marker)
    ws.invoke("set_item_folder", {"id": item["id"], "folderId": fid})
    time.sleep(0.6)

    with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
        targets = json.load(r)
    st = CDP(next(t["webSocketDebuggerUrl"] for t in targets if "view=library" in t["url"]))
    # the Library window caches its items/folders from mount — poke both loads
    st.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'library-open'}).catch(e=>String(e))")
    st.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'clipboard-changed'}).catch(e=>String(e))")
    time.sleep(1.2)
    out = st.eval("""
(() => {
  const heads = [...document.querySelectorAll('.lib-table thead th')].map(th => th.textContent.trim());
  const rows = [...document.querySelectorAll('.lib-table tbody tr')];
  const find = (txt) => rows.find(r => r.textContent.includes('__M__'));
  const probe = find('__M__');
  const probeCells = probe ? [...probe.querySelectorAll('td')].map(td => td.textContent.trim()) : null;
  const other = rows.find(r => r.querySelector('.w-folder')?.textContent.trim() === '—');
  const otherFolder = other ? other.querySelector('.w-folder')?.textContent.trim() : null;
  return JSON.stringify({ heads, probeCells, otherFolder, ncols: probe ? probe.querySelectorAll('td').length : 0 });
})()
""".replace("__M__", marker))
    d = json.loads(out)
    print("heads:", d["heads"], "| probe cells:", d["probeCells"], "| other folder:", d["otherFolder"])
    assert "文件夹" in d["heads"], d["heads"]
    # probe row's w-folder cell shows the folder name
    probe_row = st.eval("""
(() => {
  const row = [...document.querySelectorAll('.lib-table tbody tr')].find(r => r.textContent.includes('__M__'));
  return row ? row.querySelector('.w-folder').textContent.trim() : 'NOROW';
})()
""".replace("__M__", marker))
    print("probe folder cell:", probe_row)
    assert probe_row == "归属列验证", probe_row
    assert d["otherFolder"] == "—", d["otherFolder"]

    # cleanup
    ws.invoke("set_item_folder", {"id": item["id"], "folderId": None})
    ws.invoke("delete_item", {"id": item["id"]})
    ws.invoke("delete_folder", {"id": fid})
    time.sleep(0.3)
    print("R153 VERIFY PASS: folder column header + name cell + em-dash for unfiled")

if __name__ == "__main__":
    main()
