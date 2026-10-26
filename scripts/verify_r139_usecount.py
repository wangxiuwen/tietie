# -*- coding: utf-8 -*-
"""R139 / direction 133 verification: cards show cumulative use count.

The newest text item usually has use_count == 1 (no badge). We drive the
REAL re-copy path twice — Set-Clipboard with the same text bumps use_count
via the dedupe upsert (use_count + 1) — then assert the badge appears on the
card with the expected ×N, and that a fresh single-use item shows none.
Clipboard restored afterwards.
"""
import sys, time, json, subprocess, urllib.request
sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from e2e_smoke import CDP

PS = ["powershell", "-NoProfile", "-Command"]

def clip():
    r = subprocess.run(PS + ["Get-Clipboard"], capture_output=True)
    return r.stdout.decode("gbk", errors="replace").strip()

def main():
    prior = clip()
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

    def set_clip(text):
        # Set-Clipboard mangles non-ASCII via this path; use stdin pipe
        subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                       input=text.encode("utf-8"), capture_output=True)

    def card_state(content_prefix):
        # search the item to the front via the real search input, read badge
        ws.eval("""
(() => {
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, %s);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""" % json.dumps(content_prefix))
        time.sleep(0.5)
        return ws.eval("""
(() => {
  const card = document.querySelector('.card[role="option"]');
  if (!card) return JSON.stringify({ found: false });
  const b = card.querySelector('.use-count');
  return JSON.stringify({ found: true, badge: b ? b.textContent : null });
})()
""")

    marker = "usecount-verify-" + str(int(time.time()))
    set_clip(marker)
    time.sleep(2.0)
    d1 = json.loads(card_state(marker))
    print("first copy:", d1)
    assert d1["found"], "card not found after first copy"
    assert d1["badge"] is None, f"badge on single use: {d1}"

    # the OS clipboard can't signal "re-copied the SAME text" — the dedupe
    # bump fires when content REAPPEARS after something else: A → B → A
    other = "usecount-other-" + str(int(time.time()))
    set_clip(other)
    time.sleep(2.0)
    set_clip(marker)
    time.sleep(2.0)
    # second interleave → ×2
    set_clip(other)
    time.sleep(2.0)
    set_clip(marker)
    time.sleep(2.5)
    d2 = json.loads(card_state(marker))
    print("after A→B→A:", d2)
    assert d2["found"], "card lost after re-copies"
    assert d2["badge"] in ("×2", "×3", "×4"), f"unexpected badge: {d2}"

    # row view shows it too
    ws.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x => x.title === '紧凑列表' || x.title === '卡片视图');
  if (b) b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return true;
})()
""")
    time.sleep(0.5)
    row_badge = ws.eval("""
(() => {
  const row = document.querySelector('.row-item');
  const b = row?.querySelector('.use-count');
  return JSON.stringify({ badge: b ? b.textContent : null });
})()
""")
    print("row badge:", row_badge)
    assert row_badge and json.loads(row_badge)["badge"], "row view missing badge"

    # restore view + clipboard; the probe item rides history trim later
    ws.eval("""
(() => {
  const b = [...document.querySelectorAll('button')].find(x => x.title === '紧凑列表' || x.title === '卡片视图');
  if (b) b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  const el = document.querySelector('.bar-header .search input');
  const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  set.call(el, ''); el.dispatchEvent(new Event('input', { bubbles: true }));
  return true;
})()
""")
    subprocess.run(["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                   input=prior.encode("utf-8"), capture_output=True)
    print("R139 VERIFY PASS: badge appears after re-copies (real dedupe path)")

if __name__ == "__main__":
    main()
