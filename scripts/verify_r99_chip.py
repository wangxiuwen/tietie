# -*- coding: utf-8 -*-
"""R99 / direction 93 verification: chip scale feedback during card drag.

Real path: pointerdown on a card -> window pointermove (buttons=1) sweeping
over a real folder chip -> chip gets .drop-hot and animates to scale(1.1);
move away -> class drops and transform returns to none; finish the drag on a
neutral point so no item data is touched.
"""
import sys, time, json, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

DRAG = """
(() => {{
  const card = document.querySelector('.card[role="option"]');
  if (!card) return 'NOCARD';
  card.dispatchEvent(new PointerEvent('pointerdown', {{
    bubbles: true, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: 100, clientY: 300, screenX: 400, screenY: 500,
  }}));
  const move = (el, x, y) => el.dispatchEvent(new PointerEvent('pointermove', {{
    bubbles: true, buttons: 1, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
    clientX: x, clientY: y, screenX: 400, screenY: 530,
  }}));
  move(window, 100, 310); // cross the 12px threshold -> moved = true
  {phase}
  return 'OK';
}})()
"""

OVER_CHIP = """
  const chip = ([...document.querySelectorAll('[data-folder-id]')].find(
    c => { const v = c.getAttribute('data-folder-id'); return v && v !== 'all' && v !== 'pinned'; }
  )) || document.querySelector('[data-folder-id="all"]');
  if (!chip) return 'NOCHIP';
  const r = chip.getBoundingClientRect();
  move(window, r.left + r.width / 2, r.top + r.height / 2);
  window.__chip = chip;
"""

AWAY = """
  const chip = window.__chip;
  const r = chip.getBoundingClientRect();
  // a neutral point well below the chip strip and outside any card
  move(window, Math.max(20, r.left - 40), r.top + r.height + 200);
"""

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

    ws.invoke("show_drawer")
    time.sleep(0.8)
    assert ws.eval("String(document.querySelector('.card[role=\"option\"]') != null)") == "true", "no cards rendered"

    # drag over the chip
    r1 = ws.eval(DRAG.replace("{{", "{").replace("}}", "}").replace("{phase}", OVER_CHIP))
    assert r1 == "OK", f"drag setup failed: {r1!r}"
    time.sleep(0.4)  # let the 0.12s transition finish
    hot = ws.eval("""
(() => {
  const chip = window.__chip;
  return String(chip.classList.contains('drop-hot')) + '|' + getComputedStyle(chip).transform;
})()
""")
    print("hover chip:", hot)
    cls, tr = hot.split("|", 1)
    assert cls == "true", "chip did not get drop-hot while hovered"
    assert "1.1" in tr, f"transform not scaled: {tr!r}"

    # move away -> class drops and scale animates back
    r2 = ws.eval(DRAG.replace("{{", "{").replace("}}", "}").replace("{phase}", AWAY))
    assert r2 == "OK", f"away phase failed: {r2!r}"
    time.sleep(0.4)
    cold = ws.eval("""
(() => {
  const chip = window.__chip;
  return String(chip.classList.contains('drop-hot')) + '|' + getComputedStyle(chip).transform;
})()
""")
    print("moved away:", cold)
    cls, tr = cold.split("|", 1)
    assert cls == "false", "drop-hot did not clear after moving away"
    assert tr == "none", f"transform did not return to none: {tr!r}"

    # finish the drag on the neutral point: no chip under pointer, no top zone
    ws.eval("""
window.dispatchEvent(new PointerEvent('pointerup', {
  bubbles: true, buttons: 0, button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true,
  clientX: 20, clientY: 500, screenX: 400, screenY: 530,
}));
true
""")
    time.sleep(0.4)
    left = ws.eval("""
(() => String(document.body.classList.contains('dragging-hang')) + '|' +
  String(document.querySelector('.drag-ghost') != null))()
""")
    print("after pointerup (dragging|ghost):", left)
    assert left == "false|false", f"drag not cleaned up: {left!r}"

    print("R99 VERIFY PASS: chip scales to 1.1 while hovered during drag, resets when away")

if __name__ == "__main__":
    main()
