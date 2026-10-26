# -*- coding: utf-8 -*-
"""R151 / direction 142 verification: multi-select group drop into folder.

Creates a temp folder, selects TWO probe items via real Ctrl+click, drags
one of them onto the folder chip (real pointer path), asserts BOTH items
landed in the folder. Cleanup: items back to no folder + delete, folder
removed.
"""
import sys, time, json, os, subprocess, urllib.request
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

    # temp folder + two probe items via backend (net-zero, removed at end)
    fid = ws.invoke("create_folder", {"name": "整组拖入验证", "color": "#007aff"})
    assert isinstance(fid, int), fid
    a = "grp-drag-A-" + str(int(time.time()))
    b = "grp-drag-B-" + str(int(time.time()))
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=a.encode("utf-8"), capture_output=True)
    time.sleep(2.2)
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=b.encode("utf-8"), capture_output=True)
    time.sleep(2.5)
    items = ws.invoke("list_items", {"limit": 20})
    ia = next(x for x in items if x["content"] == a)
    ib = next(x for x in items if x["content"] == b)
    print("items:", ia["id"], ib["id"])

    def type_query(q):
        ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, '%s');
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""" % q)
        time.sleep(0.5)

    type_query(a)  # only A visible
    selA = ws.eval("""
(() => new Promise(res => {
  const card = document.querySelector('.card[role="option"]');
  if (!card) return res('NOCARD');
  card.dispatchEvent(new MouseEvent('click', { bubbles: true, ctrlKey: true }));
  requestAnimationFrame(() => res(String(card.className.includes('multi-sel'))));
}))()
""")
    print("A selected:", selA)
    assert selA == "true", selA

    type_query(b)  # only B visible
    selB = ws.eval("""
(() => new Promise(res => {
  const card = document.querySelector('.card[role="option"]');
  if (!card) return res('NOCARD');
  card.dispatchEvent(new MouseEvent('click', { bubbles: true, ctrlKey: true }));
  requestAnimationFrame(() => res(String(card.className.includes('multi-sel'))));
}))()
""")
    print("B selected:", selB)
    assert selB == "true", selB

    # clear search so the folder chip strip is normal; drag B onto the folder chip
    type_query("")
    ws.invoke("show_drawer")
    time.sleep(0.8)
    dragged = ws.eval("""
(() => {
  const card = [...document.querySelectorAll('.card')].find(c =>
    c.getAttribute('aria-label') && c.getAttribute('aria-label').includes('__B__'));
  if (!card) return 'NOCARD';
  const chip = document.querySelector('[data-folder-id="__F__"]');
  if (!chip) return 'NOCHIP';
  const cr = card.getBoundingClientRect();
  const fr = chip.getBoundingClientRect();
  card.dispatchEvent(new PointerEvent('pointerdown', {
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: cr.x + 20, clientY: cr.y + 20, screenX: 600, screenY: 600 }));
  window.dispatchEvent(new PointerEvent('pointermove', {
    bubbles: true, buttons: 1, pointerId: 1, pointerType: 'mouse',
    clientX: 300, clientY: 200, screenX: 300, screenY: 250 }));
  window.dispatchEvent(new PointerEvent('pointermove', {
    bubbles: true, buttons: 1, pointerId: 1, pointerType: 'mouse',
    clientX: fr.x + fr.width / 2, clientY: fr.y + fr.height / 2,
    screenX: fr.x + fr.width / 2, screenY: fr.y + fr.height / 2 }));
  window.dispatchEvent(new PointerEvent('pointerup', {
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse',
    clientX: fr.x + fr.width / 2, clientY: fr.y + fr.height / 2,
    screenX: fr.x + fr.width / 2, screenY: fr.y + fr.height / 2 }));
  return 'DRAGGED';
})()
""".replace("__B__", b[:12]).replace("__F__", str(fid)))
    print("drag:", dragged)
    assert dragged == "DRAGGED", dragged
    time.sleep(1.5)

    items2 = {x["id"]: x for x in ws.invoke("list_items", {"limit": 20})}
    fa = items2[ia["id"]].get("folder_id")
    fb = items2[ib["id"]].get("folder_id")
    print("folder_id after drag: A=", fa, "B=", fb)
    assert fa == fid and fb == fid, (fa, fb)

    # cleanup: unfile + delete items, remove folder
    ws.invoke("set_item_folder", {"id": ia["id"], "folderId": None})
    ws.invoke("set_item_folder", {"id": ib["id"], "folderId": None})
    ws.invoke("delete_item", {"id": ia["id"]})
    ws.invoke("delete_item", {"id": ib["id"]})
    ws.invoke("delete_folder", {"id": fid})
    time.sleep(0.4)
    print("R151 VERIFY PASS: both multi-selected items filed into the folder")

if __name__ == "__main__":
    main()
