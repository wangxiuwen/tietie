import { useEffect, useState } from "react";

/**
 * Minimal i18n: a flat zh/en dictionary + reactive lang state. No framework.
 * `auto` follows the system locale; the choice persists in localStorage.
 * Components re-render on change via useLang() mounted in each top-level
 * view (App / TrayPopover / Clothesline / Library), which re-runs t() down
 * the whole subtree.
 */

export type Lang = "zh" | "en";
export type LangPref = "auto" | Lang;

const LS_KEY = "tietie-lang";

type Dict = Record<string, string>;

// exported for the zh/en key-parity test (direction 42)
export const zh: Dict = {
  // kinds & tabs
  "kind.text": "文本", "kind.link": "链接", "kind.image": "图片",
  "kind.code": "代码", "kind.color": "颜色",
  "tab.all": "全部", "tab.pinned": "置顶",
  // drawer
  "search.placeholder": "搜索剪切板历史 …",
  "search.tray": "搜索 …",
  "search.library": "搜索（支持拼音首字母，如 nz 找「内存」）…",
  "empty.title": "剪切板还是空的",
  "onboard.step1": "随便复制点什么——文本/链接/图片都会自动出现在这里",
  "onboard.step2": "按 " + "`⌘⇧V`" + " 随时唤起本抽屉，↑↓ 选条目，↵ 粘贴",
  "onboard.step3": "试试把卡片往上拖——挂到晾衣架上当便签",
  "empty.desc": "复制任何文本、链接、图片或代码，它会出现在这里",
  "footer.switch": "切换", "footer.paste": "粘贴", "footer.direct": "直选",
  "footer.edit": "编辑", "footer.pin": "置顶", "footer.del": "删除",
  "footer.close": "关闭",
  "footer.hits": "命中",
  "folder.new": "+ 新建", "folder.newPlaceholder": "文件夹名称，回车新建",
  "card.paste": "↵ 粘贴", "card.copyRgb": "复制为 rgb() 格式", "card.copyImage": "复制图片到剪贴板（不粘贴）", "card.hint": "回车粘贴 · 按住往上拖可以挂到晾衣架",
  "edit.badge": "编辑中 · 不影响其它条",
  "a11y.cards": "剪贴板列表（↑↓ 选择，回车粘贴）",
  "edit.cancel": "Esc 取消", "edit.savePaste": "⌘↵ 保存并粘贴",
  "edit.chars": "字符", "edit.lines": "行",
  // settings
  "settings.title": "设置",
  "backup.banner": "已超过 7 天未导出备份，建议保存一份", "backup.exportNow": "立即导出",
  "db.badBanner": "数据库完整性自检未通过——建议立即导出备份并重启应用",
  "settings.version": "版本", "settings.checking": "检查中…", "settings.uptodate": "已是最新",
  "settings.copyVersion": "点击复制版本号",
  "settings.recheck": "重新检查", "settings.upgrade": "升级到", "settings.download": "下载",
  "settings.restarting": "即将重启…", "settings.checkUpdate": "检查更新",
  "settings.updateFailed": "更新检查失败:",
  "settings.hotkeys": "快捷键（可自定义）", "settings.general": "通用",
  "settings.hkRecheck": "占用实时检测", "settings.hkRecheckBtn": "重新检测被拒组合",
  "settings.hk.drawer": "唤起剪切板抽屉", "settings.hk.screenshot": "截图到剪切板",
  "settings.hk.clothesline": "晾衣架开关",
  "settings.autostart": "开机自启", "settings.clothesline": "晾衣架",
  "settings.dedupe": "合并重复历史",
  "settings.retention": "历史保留时长", "settings.retForever": "永久",
  "settings.ret7": "7 天", "settings.ret30": "30 天",
  "settings.retHint": "超期的未置顶条目在剪切板变化时自动清理；置顶条目永不清理。重启后生效。",
  "settings.maxHistory": "条目数上限",
  "settings.blacklist": "来源黑名单",
  "settings.fontScale": "字体大小", "settings.fsCompact": "紧凑", "settings.fsStandard": "标准", "settings.fsLarge": "大",
  "settings.accent": "主题色",
  "settings.accent_blue": "蓝", "settings.accent_green": "绿", "settings.accent_purple": "紫", "settings.accent_orange": "橙",
  "settings.dedupeHint": "开启后，再次复制相同内容只把它挪到最前并计一次使用；关闭后每次复制都记为新条目。", "settings.on": "已开启", "settings.off": "已关闭",
  "settings.dblclick": "双击卡片动作", "settings.drawerWidth": "抽屉宽度",
  "settings.wFull": "全宽", "settings.w80": "居中 80%", "settings.w60": "居中 60%", "settings.dblPaste": "粘贴到原应用",
  "settings.dblCopy": "仅复制", "settings.dblEdit": "编辑",
  "settings.backup": "备份", "settings.export": "导出 JSON 备份",
  "settings.import": "导入恢复（最新备份）",
  "settings.exporting": "导出中…", "settings.importing": "导入中…",
  "settings.exported": "已导出:", "settings.exportFail": "导出失败:", "settings.importFail": "导入失败:",
  "settings.language": "语言", "settings.langAuto": "跟随系统",
  "settings.accessibility": "辅助功能", "settings.granted": "已授权",
  "settings.grant": "去授权", "settings.detecting": "检测中…",
  "settings.modify": "修改", "settings.ok": "确定", "settings.cancel": "取消",
  "settings.capturePlaceholder": "按下组合 (Esc 取消 / Enter 确定)…",
  "settings.needMod": "全局快捷键需要至少一个修饰键",
  "settings.hkDup": "与其他贴贴热键重复",
  "settings.hkSys": "与系统常用组合冲突，可能被系统抢占",
  "settings.regFail": "注册失败（组合被占用），请修改",
  "settings.wayland": "Wayland 会话", "settings.waylandHint": "回车仅复制，不自动粘贴（Wayland 安全限制）",
  "settings.accHint": "粘贴功能需要「辅助功能」权限。点击「去授权」打开系统设置 → 隐私与安全 → 辅助功能，把 Tietie 打开即可，授权后状态自动刷新。",
  // clothesline
  "line.empty": "晾衣架空着 — 从下面的抽屉按住一张卡片往上拖，松手就挂上",
  "line.hang": "松手挂上 ↩", "line.takeoff": "拖出绳区摘下", "line.takeoffNow": "松手摘下 ✕", "line.reorder": "松手换位 ⇄", "line.insertHere": "↳ 挂到这里",
  "line.cap": "晾衣架已挂", "line.capHint": "卡片较多，建议摘下不用的便签保持整洁",
  "line.toTop": "拖到顶部挂上", "line.collapse": "收起",
  "line.newNote": "＋ 便签", "line.composing": "新便签",
  "line.exportNotes": "导出便签", "line.recentPins": "最近衣夹色", "line.note": "便签备注", "line.noteNone": "无备注",
  "line.exportNotesTxt": "导出纯文本",
  "line.composePlaceholder": "写点什么挂上？Esc 取消",
  "line.commit": "挂上 (Ctrl+↵)", "line.composeCancel": "取消",
  "line.remind": "定时提醒（到时挂卡闪烁 1 分钟）", "line.remindNone": "不提醒",
  "line.countTitle": "字数 / 行数（编辑时实时更新）",
  "line.chars": "字", "line.lines": "行",
  "line.remindIn": "提醒：",
  "line.remindChange": "改提醒…", "line.remindCancel": "取消提醒",
  "line.remindDue": "已到期", "line.remindLeft": "剩",
  "line.view": "单击查看 · 按住往下拖摘下来", "line.takeOff": "摘下来",
  "line.copy": "复制", "line.copied": "已复制 ✓", "line.edit": "编辑",
  "line.save": "保存 (⌘↵)", "line.cancelEdit": "取消编辑", "line.close": "关闭 (Esc)",
  "line.pin": "置顶", "line.unpin": "取消置顶", "line.pinned": "已置顶", "line.sink": "沉到绳尾",
  "line.justNow": "刚刚挂上", "line.loading": "原图加载中…", "line.color": "衣夹颜色", "line.minAgo": " 分钟前挂上", "line.hourAgo": " 小时前挂上",
  "line.colorKeys": "衣夹颜色：悬停时按 1-8 快速选色",
  // library
  "lib.title": "剪贴板库", "lib.kind": "类型", "lib.content": "内容",
  "lib.source": "来源", "lib.size": "大小", "lib.time": "时间",
  "lib.total": "共", "lib.items": "条", "lib.selected": "已选",
  "lib.export": "导出所选文本", "lib.exportMd": "导出 Markdown", "lib.delete": "删除所选",
  "lib.palette": "色板", "lib.paletteEmpty": "暂无颜色条目——复制一个 #RRGGBB 试试", "lib.copied": "已复制",
  "lib.copyRow": "复制此条", "lib.kindFilter": "类型筛选", "lib.pinnedOnly": "仅置顶", "lib.pinnedOnlyHint": "导出时忽略勾选，只导出置顶条目",
  "view.compact": "紧凑列表", "view.cards": "卡片视图",
  "lib.noMatch": "没有匹配的条目", "lib.empty": "剪贴板历史还是空的",
  "lib.deleted": "已删除", "lib.collapse": "收起",
  // tray popover
  "tray.pinned": "📌 置顶", "tray.recent": "最近", "tray.results": "搜索结果",
  "tray.expand": "展开",
  "tray.clearSearch": "清空搜索",
  "tray.viewAll": "查看全部 →", "tray.noMatch": "没找到匹配项", "tray.none": "暂无内容",
  "tray.full": "唤起完整面板", "tray.quit": "退出",
  // batch
  "batch.selected": "已选", "batch.hang": "批量挂绳",
  "batch.delete": "批量删除", "batch.clear": "取消选择",
  // stats
  "st.total": "总条目", "st.today": "今日", "st.pinned": "置顶",
  // rich preview
  "rich.preview": "查看富文本渲染", "rich.hint": "富文本渲染预览",
  // cheatsheet
  "cs.title": "键盘速查", "cs.nav": "切换选中卡片", "cs.paste": "粘贴到原应用",
  "cs.direct": "直接粘贴第 N 条", "cs.search": "聚焦搜索", "cs.edit": "编辑当前条",
  "cs.pin": "置顶/取消", "cs.del": "删除", "cs.tab": "切换类型标签",
  "cs.note": "给选中卡片写备注（输入时 ⌘N）",
  "cs.multi": "多选（批量删除/挂绳）", "cs.hang": "挂到晾衣架", "cs.file": "归类到文件夹",
  "cs.menu": "上下文菜单", "cs.close": "关闭",
  "cs.zoom": "图片卡大图开关", "cs.rgb": "颜色卡复制 rgb()",
  // context menu
  "ctx.copy": "复制", "ctx.pasteBack": "粘贴到原应用", "ctx.pin": "置顶",
  "ctx.unpin": "取消置顶", "ctx.hang": "挂到晾衣架", "ctx.moveTo": "移入文件夹…",
  "ctx.markSensitive": "🔒 标记敏感（本机加密存储）", "ctx.unmarkSensitive": "取消敏感标记",
  "ctx.addNote": "📝 添加备注…", "ctx.editNote": "📝 编辑备注…",
  "ctx.notePlaceholder": "备注（参与搜索；留空即清除）",
  "ctx.clearFolder": "　移出文件夹", "ctx.delete": "删除",
  // rel time
  "rt.now": "刚刚", "rt.min": "分钟前", "rt.hour": "小时前", "rt.day": "天前",
};

export const en: Dict = {
  "kind.text": "Text", "kind.link": "Link", "kind.image": "Image",
  "kind.code": "Code", "kind.color": "Color",
  "tab.all": "All", "tab.pinned": "Pinned",
  "search.placeholder": "Search clipboard history …",
  "search.tray": "Search …",
  "search.library": "Search (pinyin initials work, e.g. nz for 内存) …",
  "empty.title": "Clipboard is empty",
  "onboard.step1": "Copy anything — text, links and images land here automatically",
  "onboard.step2": "Press `⌘⇧V` anytime to reopen, arrows to pick, Enter to paste",
  "onboard.step3": "Drag a card upward to hang it on the clothesline as a note",
  "empty.desc": "Copy any text, link, image or code and it shows up here",
  "footer.switch": "Switch", "footer.paste": "Paste", "footer.direct": "Direct",
  "footer.edit": "Edit", "footer.pin": "Pin", "footer.del": "Delete",
  "footer.close": "Close",
  "footer.hits": "hits",
  "folder.new": "+ New", "folder.newPlaceholder": "Folder name, Enter to create",
  "card.paste": "↵ Paste", "card.copyRgb": "Copy as rgb()", "card.copyImage": "Copy image to clipboard (no paste)", "card.hint": "Enter to paste · drag up to hang on the line",
  "edit.badge": "Editing · others untouched",
  "a11y.cards": "Clipboard list (↑↓ select, Enter paste)",
  "edit.cancel": "Esc Cancel", "edit.savePaste": "⌘↵ Save & Paste",
  "edit.chars": "chars", "edit.lines": "lines",
  "settings.title": "Settings",
  "backup.banner": "No backup exported in over 7 days — save one now", "backup.exportNow": "Export now",
  "db.badBanner": "Database integrity check FAILED — export a backup now and restart the app",
  "settings.version": "Version", "settings.checking": "Checking…", "settings.uptodate": "Up to date",
  "settings.copyVersion": "Click to copy version",
  "settings.recheck": "Recheck", "settings.upgrade": "Upgrade to", "settings.download": "Download",
  "settings.restarting": "Restarting…", "settings.checkUpdate": "Check for updates",
  "settings.updateFailed": "Update check failed:",
  "settings.hotkeys": "Hotkeys (rebindable)", "settings.general": "General",
  "settings.hkRecheck": "Live occupancy check", "settings.hkRecheckBtn": "Re-check refused combos",
  "settings.hk.drawer": "Open clipboard drawer", "settings.hk.screenshot": "Screenshot to clipboard",
  "settings.hk.clothesline": "Toggle clothesline",
  "settings.autostart": "Launch at login", "settings.clothesline": "Clothesline",
  "settings.dedupe": "Merge duplicates",
  "settings.retention": "History retention", "settings.retForever": "Forever",
  "settings.ret7": "7 days", "settings.ret30": "30 days",
  "settings.retHint": "Expired unpinned entries are cleaned when the clipboard changes; pinned entries never expire. Takes effect after restart.",
  "settings.maxHistory": "History size cap",
  "settings.blacklist": "Source blacklist",
  "settings.fontScale": "Font size", "settings.fsCompact": "Compact", "settings.fsStandard": "Standard", "settings.fsLarge": "Large",
  "settings.accent": "Accent",
  "settings.accent_blue": "Blue", "settings.accent_green": "Green", "settings.accent_purple": "Purple", "settings.accent_orange": "Orange",
  "settings.dedupeHint": "On: copying the same content again just moves it to the front and counts a use. Off: every copy is recorded as a new entry.", "settings.on": "On", "settings.off": "Off",
  "settings.dblclick": "Double-click action", "settings.drawerWidth": "Drawer width",
  "settings.wFull": "Full width", "settings.w80": "Centered 80%", "settings.w60": "Centered 60%", "settings.dblPaste": "Paste to previous app",
  "settings.dblCopy": "Copy only", "settings.dblEdit": "Edit",
  "settings.backup": "Backup", "settings.export": "Export JSON backup",
  "settings.import": "Import latest backup",
  "settings.exporting": "Exporting…", "settings.importing": "Importing…",
  "settings.exported": "Exported:", "settings.exportFail": "Export failed:", "settings.importFail": "Import failed:",
  "settings.language": "Language", "settings.langAuto": "Follow system",
  "settings.accessibility": "Accessibility", "settings.granted": "Granted",
  "settings.grant": "Grant…", "settings.detecting": "Checking…",
  "settings.modify": "Change", "settings.ok": "OK", "settings.cancel": "Cancel",
  "settings.capturePlaceholder": "Press combo (Esc cancel / Enter OK)…",
  "settings.needMod": "Global shortcuts need at least a modifier",
  "settings.hkDup": "Duplicates another tietie hotkey",
  "settings.hkSys": "Conflicts with a common system shortcut",
  "settings.regFail": "Register failed (combo taken) — change it",
  "settings.wayland": "Wayland session", "settings.waylandHint": "Enter copies only — no auto-paste (Wayland security)",
  "settings.accHint": "Paste needs Accessibility permission. Click Grant, open System Settings → Privacy & Security → Accessibility and enable Tietie; status refreshes automatically.",
  "line.empty": "The line is empty — drag a drawer card up here and release to hang it",
  "line.hang": "Release to hang ↩", "line.takeoff": "Drag past the rope to take off", "line.takeoffNow": "Release to take off ✕", "line.reorder": "Release to reorder ⇄", "line.insertHere": "↳ hangs here",
  "line.cap": "on the line:", "line.capHint": "Quite crowded — take unused notes off to keep it tidy",
  "line.toTop": "Drag to the top to hang", "line.collapse": "Collapse",
  "line.newNote": "＋ Note", "line.composing": "New note",
  "line.exportNotes": "Export notes", "line.recentPins": "Recent pins", "line.note": "Note", "line.noteNone": "No note",
  "line.exportNotesTxt": "Export TXT",
  "line.composePlaceholder": "Write something to hang? Esc cancels",
  "line.commit": "Hang (Ctrl+↵)", "line.composeCancel": "Cancel",
  "line.remind": "Remind me (card flashes for 1 min when due)", "line.remindNone": "No reminder",
  "line.countTitle": "Characters / lines (live while editing)",
  "line.chars": "chars", "line.lines": "lines",
  "line.remindIn": "Remind in",
  "line.remindChange": "Change reminder…", "line.remindCancel": "Cancel reminder",
  "line.remindDue": "due", "line.remindLeft": "in",
  "line.view": "Click to view · drag down to take off", "line.takeOff": "Take off",
  "line.copy": "Copy", "line.copied": "Copied ✓", "line.edit": "Edit",
  "line.save": "Save (⌘↵)", "line.cancelEdit": "Cancel edit", "line.close": "Close (Esc)",
  "line.pin": "Pin", "line.unpin": "Unpin", "line.pinned": "Pinned", "line.sink": "Sink to end",
  "line.justNow": "just hung", "line.loading": "Loading full image…", "line.color": "Pin color", "line.minAgo": " min ago", "line.hourAgo": " h ago",
  "line.colorKeys": "Pin color: hover and press 1-8",
  "lib.title": "Clipboard Library", "lib.kind": "Kind", "lib.content": "Content",
  "lib.source": "Source", "lib.size": "Size", "lib.time": "Time",
  "lib.total": "Total", "lib.items": "items", "lib.selected": "Selected",
  "lib.export": "Export selected text", "lib.exportMd": "Export Markdown", "lib.delete": "Delete selected",
  "lib.palette": "Swatches", "lib.paletteEmpty": "No colors yet — copy a #RRGGBB to try", "lib.copied": "Copied",
  "lib.copyRow": "Copy this item", "lib.kindFilter": "Kind filter", "lib.pinnedOnly": "Pinned only", "lib.pinnedOnlyHint": "Exports ignore selection; only pinned items are exported",
  "view.compact": "Compact list", "view.cards": "Card view",
  "lib.noMatch": "No matching items", "lib.empty": "Clipboard history is empty",
  "lib.deleted": "Deleted", "lib.collapse": "Collapse",
  "tray.pinned": "📌 Pinned", "tray.recent": "Recent", "tray.results": "Results",
  "tray.expand": "Show all",
  "tray.clearSearch": "Clear search",
  "tray.viewAll": "View all →", "tray.noMatch": "No matches", "tray.none": "Nothing yet",
  "tray.full": "Open full panel", "tray.quit": "Quit",
  "batch.selected": "Selected", "batch.hang": "Hang all",
  "batch.delete": "Delete all", "batch.clear": "Clear selection",
  "st.total": "Total", "st.today": "Today", "st.pinned": "Pinned",
  "rich.preview": "View rendered rich text", "rich.hint": "Rendered rich-text preview",
  "cs.title": "Keyboard cheatsheet", "cs.nav": "Move selection", "cs.paste": "Paste to previous app",
  "cs.direct": "Paste Nth item", "cs.search": "Focus search", "cs.edit": "Edit item",
  "cs.pin": "Toggle pin", "cs.del": "Delete", "cs.tab": "Switch type tab",
  "cs.note": "Note the selected card (⌘N while typing)",
  "cs.multi": "Multi-select (batch)", "cs.hang": "Hang on the line", "cs.file": "File into folder",
  "cs.menu": "Context menu", "cs.close": "Close",
  "cs.zoom": "Zoom selected image card", "cs.rgb": "Copy color as rgb()",
  "ctx.copy": "Copy", "ctx.pasteBack": "Paste to previous app", "ctx.pin": "Pin",
  "ctx.unpin": "Unpin", "ctx.hang": "Hang on the line", "ctx.moveTo": "Move to folder…",
  "ctx.markSensitive": "🔒 Mark sensitive (encrypted at rest)", "ctx.unmarkSensitive": "Remove sensitive mark",
  "ctx.addNote": "📝 Add note…", "ctx.editNote": "📝 Edit note…",
  "ctx.notePlaceholder": "Note (searchable; empty clears it)",
  "ctx.clearFolder": "　Remove from folder", "ctx.delete": "Delete",
  "rt.now": "just now", "rt.min": " min ago", "rt.hour": " h ago", "rt.day": " d ago",
};

const dicts: Record<Lang, Dict> = { zh, en };

function systemLang(): Lang {
  return (navigator.language || "zh").toLowerCase().startsWith("zh") ? "zh" : "en";
}

function resolvePref(): LangPref {
  const v = localStorage.getItem(LS_KEY);
  return v === "zh" || v === "en" ? v : "auto";
}

let current: Lang = resolvePref() === "auto" ? systemLang() : (resolvePref() as Lang);
const subs = new Set<() => void>();

/** Translate a key; missing keys fall back to the key itself. */
export function t(key: string): string {
  return dicts[current][key] ?? dicts.zh[key] ?? key;
}

export function getLang(): Lang {
  return current;
}

export function getPref(): LangPref {
  return resolvePref();
}

export function setPref(pref: LangPref) {
  localStorage.setItem(LS_KEY, pref);
  current = pref === "auto" ? systemLang() : pref;
  subs.forEach((f) => f());
}

/** Mount in each top-level view so t() re-evaluates after a switch. */
export function useLang() {
  const [, force] = useState(0);
  useEffect(() => {
    const fn = () => force((x) => x + 1);
    subs.add(fn);
    return () => {
      subs.delete(fn);
    };
  }, []);
  return current;
}
