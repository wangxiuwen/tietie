# 方向184 真机验证：同步日志点击按对端过滤（再点取消）
# 剧本（产品路径造双对端事件 + 合成点击断言；事件环内存态无需清理）：
#   现有配对 wsl-tietie（unreachable 也入环）→ 再经 msg_send 造第二对端事件？
#   配对表仅 wsl 一个对端——单对端即可验证：先补一条 in 事件需要第二对端，
#   改用 ring 现状：若有≥2 条事件（含 fail）直接用；否则 msg_send 造一条
#   → 断言初始全部行显示 → 点某行 → 仅剩该 peer 的行 + .on 高亮
#   → 再点同 peer 行 → 全部恢复
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


main = CDP(page_ws(lambda u: u.endswith("/") or "view=" not in u))
st = CDP(page_ws(lambda u: "view=settings" in u))


def rows():
    out = st.eval(r"""(() => JSON.stringify(
      [...document.querySelectorAll('button.sync-ev')].map(b => ({
        text: b.textContent.trim(), on: b.className.includes('on')}))))()""")
    if not isinstance(out, str):
        raise RuntimeError("eval type")
    return json.loads(out)


ring = json.loads(main.eval(r"""(async () => JSON.stringify(
  await window.__TAURI_INTERNALS__.invoke('sync_events')))()"""))
print("ring:", len(ring), [e["dir"] for e in ring])
if len(ring) == 0:
    # 造一条产品路径事件（unreachable 也入环，约 16s 超时）
    main.eval(r"""(async () => {
      try { await window.__TAURI_INTERNALS__.invoke('msg_send',
        {instance: 'wsl-tietie', text: 'R184探针'}); } catch (e) {}
      return 'sent';
    })()""")
    print("waiting for unreachable timeout (~16s) ...")
    for _ in range(12):
        time.sleep(2)
        n = main.eval(r"""(async () => (await window.__TAURI_INTERNALS__.invoke('sync_events')).length)()""")
        if int(n) > 0:
            break

main.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.2)

r0 = rows()
print("all rows:", len(r0))
assert len(r0) >= 1, "日志无行（事件未入环）"

# 点第一行 → 过滤到该行 peer（可能只剩部分行）
first_text = r0[0]["text"]
st.eval(r"""(() => {
  const b = document.querySelector('button.sync-ev');
  if (b) b.click();
})()""")
time.sleep(0.5)
r1 = rows()
print("filtered:", len(r1), "| on:", [x["on"] for x in r1])
assert all(x["on"] for x in r1) and len(r1) >= 1, "过滤态异常"
peer_seg = first_text.split("·")[0]
for x in r1:
    assert x["text"].split("·")[0].strip().endswith(peer_seg.split()[-1]), \
        f"异对端行漏入: {x['text']}"

# 同 peer 再点 → 取消过滤恢复全量
st.eval(r"""(() => {
  const b = document.querySelector('button.sync-ev.on');
  if (b) b.click();
})()""")
time.sleep(0.5)
r2 = rows()
print("restored:", len(r2))
assert len(r2) == len(r0) and not any(x["on"] for x in r2), "取消过滤未恢复全量"
print("PASS: 点击按对端过滤（.on 高亮、仅该对端行）、再点取消恢复全量")
