# -*- coding: utf-8 -*-
"""R121 / direction 115 verification: tray rows show note tooltip.

No production item has a note — temporarily annotate the newest TEXT item
(set_item_note, restored to empty afterwards), refresh the tray panel, and
assert its .po-row carries title == the note while another note-less row
carries no title at all.
"""
import sys, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

def main():
    ws = None
    for _ in range(20):
        with urllib.request.urlopen("http://127.0.0.1:9223/json/list") as r:
            targets = json.load(r)
        for t in targets:
            if "view=tray" in t["url"]:
                ws = CDP(t["webSocketDebuggerUrl"]); break
        if ws: break
        time.sleep(1)
    assert ws, "tray target not found"

    items = ws.invoke("list_items", {"limit": 100})
    target = next(x for x in items if x["kind"] == "text")
    plain = next((x for x in items if x["kind"] == "text" and x["id"] != target["id"]), None)
    print("annotating:", target["id"], "| plain control:", plain["id"] if plain else None)
    assert not ws.invoke("set_item_note", {"id": target["id"], "note": "托盘备注提示验证"}), "set note failed"

    ws.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'show-tray'}).catch(e=>String(e))")
    time.sleep(1.0)

    out = ws.eval("""
(() => {
  const rows = [...document.querySelectorAll('.po-row')];
  const find = id => null; // rows don't carry ids; match by text instead
  const byNote = rows.filter(r => (r.getAttribute('title') || '') !== '');
  const plain = rows.filter(r => !r.getAttribute('title'));
  return JSON.stringify({
    total: rows.length,
    titled: byNote.map(r => r.getAttribute('title')),
    untitledCount: plain.length,
    firstTitledText: byNote[0] ? byNote[0].textContent.slice(0, 40) : null,
  });
})()
""")
    d = json.loads(out)
    print("rows:", d)
    assert d["titled"] == ["托盘备注提示验证"], f"unexpected titles: {d['titled']}"
    assert d["untitledCount"] == d["total"] - 1, "more than one titled row"
    assert d["firstTitledText"] and "托盘备注提示验证" not in d["firstTitledText"], \
        "note leaked into row text"

    # restore: clear the note, refresh, assert no titled rows remain
    ws.invoke("set_item_note", {"id": target["id"], "note": ""})
    ws.eval("window.__TAURI_INTERNALS__.invoke('plugin:event|emit', {event: 'show-tray'}).catch(e=>String(e))")
    time.sleep(1.0)
    after = ws.eval("""
(() => JSON.stringify(
  [...document.querySelectorAll('.po-row')].filter(r => (r.getAttribute('title') || '') !== '').length
))()
""")
    assert json.loads(after) == 0, f"titles remain after restore: {after}"
    back = next(x for x in ws.invoke("list_items", {"limit": 100}) if x["id"] == target["id"])
    assert not back.get("note"), "note not restored to empty"
    print("R121 VERIFY PASS: note shows as row tooltip only, clean restore")

if __name__ == "__main__":
    main()
