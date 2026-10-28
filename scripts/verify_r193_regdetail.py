# 方向193 真机验证：热键注册失败时 regFail 标签 title 附后端错误详情
# 剧本（产品路径 set_hotkey 制造失败 + DOM 断言，结束还原原热键）：
#   get_hotkeys 基线 → set_hotkey(screenshot, 被自身占用的组合) 必失败
#   → 断言 screenshot_registered=false 且 screenshot_error 含组合与错误文本
#   → 设置页 regFail 标签 title == 该错误详情（非兜底文案）
#   → set_hotkey 还原原组合（product path）→ registered 恢复 true、error 清空
import json
import time
import urllib.request

from e2e_smoke import CDP

PORT = 9223

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as r:
    ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(r)
                  if t["type"] == "page" and "view=settings" in t["url"])
st = CDP(ws_url)


def get_hks():
    out = st.eval(r"""(async () => JSON.stringify(
  await window.__TAURI_INTERNALS__.invoke('get_hotkeys')))()""")
    if not isinstance(out, str):
        raise RuntimeError("type")
    return json.loads(out)


st.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.0)

base = get_hks()
orig = base["screenshot"]
print("baseline screenshot:", orig, "| registered:", base["screenshot_registered"],
      "| err:", base.get("screenshot_error"))

# 制造失败：把 screenshot 改成 drawer 正持有的组合（同进程自占用必注册失败）
drawer_combo = base["drawer"]
res = st.eval(rf"""(async () => {{
  try {{
    await window.__TAURI_INTERNALS__.invoke('set_hotkey',
      {{kind: 'screenshot', value: {json.dumps(drawer_combo)}}});
    return 'UNEXPECTED-OK';
  }} catch (e) {{ return String(e); }}
}})()""")
print("set to drawer combo ->", res)
assert "注册失败" in res, f"预期失败未发生: {res}"

fail = get_hks()
print("after fail:", fail["screenshot_registered"], fail.get("screenshot_error"))
assert fail["screenshot_registered"] is False, "registered 未翻 false"
err = fail.get("screenshot_error") or ""
assert drawer_combo in err and len(err) > len(drawer_combo) + 3, \
    f"error 详情缺组合/错误文本: {err!r}"

# 打开设置页刷新 → regFail 标签 title == 错误详情
st.eval('window.__TAURI_INTERNALS__.invoke("open_settings")')
time.sleep(1.0)
tag = json.loads(st.eval(r"""(() => {
  const rows = [...document.querySelectorAll('.settings-row')];
  const shot = rows.find(r => r.textContent.includes('截图到剪切板'));
  if (!shot) return 'NOROW';
  const tag = shot.querySelector('.settings-tag.err[title]');
  return tag ? JSON.stringify({text: tag.textContent.trim(), title: tag.title})
             : 'NOTAG';
})()"""))
print("regFail tag:", tag)
assert tag != "NOROW" and tag != "NOTAG", f"标签缺失: {tag}"
td = json.loads(tag)
assert td["title"] == err, f"title 不符: {td['title']!r} != {err!r}"
assert "注册失败" in td["text"]

# 还原
back = st.eval(rf"""(async () => {{
  try {{
    await window.__TAURI_INTERNALS__.invoke('set_hotkey',
      {{kind: 'screenshot', value: {json.dumps(orig)}}});
    return 'OK';
  }} catch (e) {{ return 'ERR ' + String(e); }}
}})()""")
print("restore:", back)
assert back == "OK"
final = get_hks()
assert final["screenshot_registered"] is True and not final.get("screenshot_error"), \
    f"还原态异常: {final['screenshot_registered']} {final.get('screenshot_error')}"
print("PASS: 失败→registered=false+error 详情入快照→regFail title=详情→还原即清")
