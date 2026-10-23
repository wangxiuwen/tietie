import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { check as checkUpdate, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
// clipboard plugin no longer needed at JS layer — Rust paste_item handles it
import type { ClipItem, Folder, ItemKind } from "./types";
import { kindLabel } from "./types";
import { IS_MAC, MOD } from "./platform";
import { matchQuery } from "./search";
import { t, useLang, setPref, getPref, type LangPref } from "./i18n";

type FilterTab = "all" | ItemKind;

// ─── drawer drag-to-hang: one shared tracker, listeners live in App ───
// WebView2 only honors DOM pointer capture on activated windows, so tracking
// runs on window-level listeners (verified on real hardware). A single mouse
// means a single active drag — one module-level record shared by all cards,
// with ONE set of window listeners in App instead of one per card (500 cards
// used to install 1500 handlers that every pointermove had to walk).
const cardDrag = {
  current: null as null | {
    itemId: number;
    startY: number;
    moved: boolean;
    inZone: boolean;
  },
};
// set when a drag actually moved; cards swallow the trailing click for 150ms
let lastCardDragEnd = 0;
const CARD_DRAG_SUPPRESS_MS = 150;

const TYPE_TABS: { id: FilterTab; labelKey: string; dot: string }[] = [
  { id: "all", labelKey: "tab.all", dot: "var(--accent)" },
  { id: "text", labelKey: "kind.text", dot: "var(--cat-text)" },
  { id: "link", labelKey: "kind.link", dot: "var(--cat-link)" },
  { id: "image", labelKey: "kind.image", dot: "var(--cat-image)" },
  { id: "code", labelKey: "kind.code", dot: "var(--cat-code)" },
  { id: "color", labelKey: "kind.color", dot: "var(--cat-color)" },
];

export default function App() {
  useLang(); // re-render the whole drawer on language switch
  const [items, setItems] = useState<ClipItem[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [tab, setTab] = useState<FilterTab>("all");
  const [folderId, setFolderId] = useState<number | "pinned" | null>(null);
  const [query, setQuery] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [editing, setEditing] = useState<ClipItem | null>(null);
  const [editValue, setEditValue] = useState("");
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dragGhost, setDragGhost] = useState<{ x: number; y: number; inZone: boolean } | null>(
    null,
  );
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [zoomId, setZoomId] = useState<number | null>(null);
  // ⌘/Ctrl+click multi-select for batch delete / hang
  const [multiSel, setMultiSel] = useState<Set<number>>(new Set());
  const cardsRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const editRef = useRef<HTMLTextAreaElement>(null);

  const refresh = useCallback(async () => {
    const [is, fs] = await Promise.all([
      invoke<ClipItem[]>("list_items", { limit: 500 }),
      invoke<Folder[]>("list_folders"),
    ]);
    setItems(is);
    setFolders(fs);
  }, []);

  useEffect(() => {
    refresh();
    const unlistens: UnlistenFn[] = [];
    listen<null>("clipboard-changed", () => refresh()).then((u) => unlistens.push(u));
    listen<null>("show-drawer", async () => {
      await refresh();
      setDrawerVisible(true);
      setSelectedIdx(0);
      setEditing(null);
      requestAnimationFrame(() => searchRef.current?.focus());
    }).then((u) => unlistens.push(u));
    listen<null>("hide-drawer", () => {
      setDrawerVisible(false);
      setEditing(null);
      setSettingsOpen(false);
      // The drawer can hide mid-drag (Esc, focus loss) while the OS cursor
      // is grabbed — release it or the hidden window keeps eating the mouse.
      getCurrentWindow().setCursorGrab(false).catch(() => {});
      document.body.classList.remove("dragging-hang");
    }).then((u) => unlistens.push(u));
    listen<null>("show-settings", () => setSettingsOpen(true)).then((u) => unlistens.push(u));
    return () => unlistens.forEach((u) => u());
  }, [refresh]);

  // One window-level drag tracker for every card (see cardDrag above).
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const st = cardDrag.current;
      if (!st || (e.buttons & 1) === 0) return;
      if (!st.moved) {
        if (Math.abs(st.startY - e.screenY) < 12) return;
        st.moved = true;
        setDraggingId(st.itemId);
        // grab the OS cursor so events keep flowing after leaving the window
        getCurrentWindow().setCursorGrab(true).catch(() => {});
        document.body.classList.add("dragging-hang");
      }
      // Top zone = near the clothesline. WebView2 may clamp client coords
      // at the window edge, so also accept "clearly dragged out the top".
      const screenTop = e.screenY < 320;
      const outTop = e.clientY <= 1 && st.startY - e.screenY > 140;
      const inZone = screenTop || outTop;
      if (inZone !== st.inZone) {
        st.inZone = inZone;
        invoke("hang_preview", { id: inZone ? st.itemId : null }).catch(() => {});
      }
      setDragGhost({
        x: e.screenX - window.screenX,
        y: e.screenY - window.screenY,
        inZone,
      });
    };
    const onFinish = (hangIfZone: boolean) => {
      const st = cardDrag.current;
      if (!st) return;
      cardDrag.current = null;
      document.body.classList.remove("dragging-hang");
      getCurrentWindow().setCursorGrab(false).catch(() => {});
      setDragGhost(null);
      setDraggingId(null);
      if (st.moved) {
        lastCardDragEnd = Date.now();
        if (hangIfZone && st.inZone) {
          invoke("hang_item", { id: st.itemId })
            .catch(() => {})
            .finally(() => invoke("hang_preview", { id: null }).catch(() => {}));
        } else {
          invoke("hang_preview", { id: null }).catch(() => {});
        }
      }
    };
    const onUp = () => onFinish(true);
    const onCancel = () => onFinish(false);
    window.addEventListener("pointermove", onMove, true);
    window.addEventListener("pointerup", onUp, true);
    window.addEventListener("pointercancel", onCancel, true);
    return () => {
      window.removeEventListener("pointermove", onMove, true);
      window.removeEventListener("pointerup", onUp, true);
      window.removeEventListener("pointercancel", onCancel, true);
    };
  }, []);

  const filtered = useMemo(() => {
    let xs = items;
    if (folderId === "pinned") xs = xs.filter((x) => x.pinned);
    else if (typeof folderId === "number") xs = xs.filter((x) => x.folder_id === folderId);
    if (tab !== "all") xs = xs.filter((x) => x.kind === tab);
    if (query.trim()) {
      xs = xs.filter((x) => matchQuery(x.content, x.preview, query));
    }
    return xs.slice().sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      return b.used_at - a.used_at;
    });
  }, [items, folderId, tab, query]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: items.length, pinned: 0 };
    for (const k of ["text", "link", "image", "code", "color"]) c[k] = 0;
    for (const x of items) {
      c[x.kind] = (c[x.kind] || 0) + 1;
      if (x.pinned) c.pinned++;
    }
    return c;
  }, [items]);

  const paste = useCallback(async (item: ClipItem) => {
    // Rust-side paste_item handles: write right pasteboard types
    // (text+RTF+HTML for rich text, png for image), touch_item, then
    // hide drawer + restore focus + synth ⌘V — all in one IPC.
    await invoke("paste_item", { id: item.id });
  }, []);

  const togglePin = useCallback(async (id: number) => {
    await invoke("toggle_pin", { id });
    refresh();
  }, [refresh]);

  const deleteItem = useCallback(async (id: number) => {
    await invoke("delete_item", { id });
    refresh();
  }, [refresh]);

  const startEdit = useCallback((item: ClipItem) => {
    setEditing(item);
    setEditValue(item.content);
    requestAnimationFrame(() => editRef.current?.focus());
  }, []);

  const saveEdit = useCallback(async (alsoPaste: boolean) => {
    if (!editing) return;
    await invoke("update_item_content", { id: editing.id, content: editValue });
    const id = editing.id;
    setEditing(null);
    await refresh();
    if (alsoPaste) {
      await invoke("paste_item", { id });
    }
  }, [editing, editValue, refresh]);

  // keyboard navigation
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const isMod = e.metaKey || e.ctrlKey;

      // Arrow keys always switch selection — bail out of edit mode if needed.
      // ↑/↓ alias ←/→: the strip is a single horizontal row, but up/down
      // matches the muscle memory of vertical list navigation.
      if (["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].includes(e.key)) {
        e.preventDefault();
        if (editing) setEditing(null);
        if (zoomId !== null) setZoomId(null);
        if (e.key === "ArrowRight" || e.key === "ArrowDown") {
          setSelectedIdx((i) => Math.min(i + 1, Math.max(0, filtered.length - 1)));
        } else {
          setSelectedIdx((i) => Math.max(0, i - 1));
        }
        return;
      }

      if (editing) return; // textarea handles the rest

      if (e.key === "Escape") {
        if (zoomId !== null) {
          e.preventDefault();
          e.stopPropagation();
          setZoomId(null);
          return;
        }
        if (multiSel.size > 0) {
          e.preventDefault();
          setMultiSel(new Set());
          return;
        }
        invoke("hide_window");
        return;
      }
      if (e.key === "Enter") {
        const it = filtered[selectedIdx];
        if (it) paste(it);
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        const idx = TYPE_TABS.findIndex((t) => t.id === tab);
        const next = e.shiftKey
          ? (idx - 1 + TYPE_TABS.length) % TYPE_TABS.length
          : (idx + 1) % TYPE_TABS.length;
        setTab(TYPE_TABS[next].id);
        setSelectedIdx(0);
        return;
      }
      if (isMod && /^[0-9]$/.test(e.key)) {
        e.preventDefault();
        const i = e.key === "0" ? 9 : Number(e.key) - 1;
        const it = filtered[i];
        if (it) paste(it);
        return;
      }
      if (isMod && e.key.toLowerCase() === "p") {
        e.preventDefault();
        const it = filtered[selectedIdx];
        if (it) togglePin(it.id);
        return;
      }
      if (isMod && e.key.toLowerCase() === "e") {
        e.preventDefault();
        const it = filtered[selectedIdx];
        if (it) startEdit(it);
        return;
      }
      if (isMod && e.key.toLowerCase() === "d") {
        e.preventDefault();
        const it = filtered[selectedIdx];
        if (it) deleteItem(it.id);
        return;
      }
      if (isMod && e.key.toLowerCase() === "f") {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
    }
    // Capture phase — runs before the search input's own keydown handling,
    // so preventDefault actually stops ⌘D / ⌘P / etc. from typing into search.
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [filtered, selectedIdx, tab, editing, zoomId, multiSel.size, paste, togglePin, deleteItem, startEdit]);

  // scroll selected into view
  useEffect(() => {
    const el = cardsRef.current?.querySelector<HTMLElement>(`[data-idx="${selectedIdx}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  }, [selectedIdx]);

  // hide on blur (real Tauri window only)
  useEffect(() => {
    let unlisten: UnlistenFn | undefined;
    getCurrentWindow().onFocusChanged(({ payload: focused }) => {
      if (!focused) {
        invoke("hide_window").catch(() => {});
      }
    }).then((u) => (unlisten = u));
    return () => {
      unlisten?.();
    };
  }, []);

  const showAlways = drawerVisible || items.length === 0; // show on first run for affordance
  const drawerCls = showAlways ? "drawer drawer-in" : "drawer";

  return (
    <div className={drawerCls}>
      <div className="bar">
        <div className="bar-handle" />
        <Header
          query={query}
          setQuery={(v) => {
            setQuery(v);
            setSelectedIdx(0);
          }}
          tab={tab}
          setTab={(t) => {
            setTab(t);
            setSelectedIdx(0);
          }}
          counts={counts}
          searchRef={searchRef}
        />
        <FolderChips
          folders={folders}
          folderId={folderId}
          setFolderId={(f) => {
            setFolderId(f);
            setSelectedIdx(0);
          }}
          counts={{ pinned: counts.pinned }}
        />
        <div className="strip">
          {filtered.length === 0 ? (
            <Empty />
          ) : (
            <div className="cards" ref={cardsRef}>
              {filtered.map((it, idx) =>
                editing && editing.id === it.id ? (
                  <EditCard
                    key={it.id}
                    item={it}
                    value={editValue}
                    setValue={setEditValue}
                    onCancel={() => setEditing(null)}
                    onSave={() => saveEdit(false)}
                    onSaveAndPaste={() => saveEdit(true)}
                    textareaRef={editRef}
                  />
                ) : (
                  <Card
                    key={it.id}
                    item={it}
                    idx={idx}
                    selected={idx === selectedIdx}
                    beingDragged={draggingId === it.id}
                    multiSelected={multiSel.has(it.id)}
                    onClick={(e) => {
                      if (e.metaKey || e.ctrlKey) {
                        // multi-select toggle — no zoom, no single selection
                        setMultiSel((s) => {
                          const n = new Set(s);
                          if (n.has(it.id)) n.delete(it.id);
                          else n.add(it.id);
                          return n;
                        });
                        return;
                      }
                      setSelectedIdx(idx);
                      // 单击图片卡顺手弹大图（回车仍是粘贴，浮层 Esc 关闭）
                      if (it.kind === "image") setZoomId(it.id);
                      else setZoomId(null);
                    }}
                    onDoubleClick={() => paste(it)}
                    onPin={() => togglePin(it.id)}
                    onEdit={() => startEdit(it)}
                    onDelete={() => deleteItem(it.id)}
                    onPaste={() => paste(it)}
                  />
                ),
              )}
            </div>
          )}
        </div>
        {multiSel.size > 0 && (
          <div className="batch-bar">
            <span>
              {t("batch.selected")} {multiSel.size}
            </span>
            <button
              className="btn ghost"
              onClick={async () => {
                const ids = [...multiSel];
                setMultiSel(new Set());
                await invoke("hang_items", { ids }).catch(() => {});
              }}
            >
              {t("batch.hang")}
            </button>
            <button
              className="btn primary"
              onClick={async () => {
                const ids = [...multiSel];
                setMultiSel(new Set());
                await invoke("delete_items", { ids }).catch(() => {});
              }}
            >
              {t("batch.delete")}
            </button>
            <button className="btn ghost" onClick={() => setMultiSel(new Set())}>
              {t("batch.clear")}
            </button>
          </div>
        )}
        <Footer count={filtered.length} total={items.length} />
        {zoomId !== null && (
          <ZoomOverlay
            item={items.find((x) => x.id === zoomId) ?? filtered.find((x) => x.id === zoomId)}
            onClose={() => setZoomId(null)}
          />
        )}
        {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}
        {dragGhost &&
          createPortal(
            <div className="drag-ghost" style={{ left: dragGhost.x, top: dragGhost.y }}>
              {dragGhost.inZone ? "松手挂上 ↩" : "拖到顶部挂上"}
            </div>,
            document.body,
          )}
      </div>
    </div>
  );
}

type UpdateStatus =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "uptodate" }
  | { kind: "available"; version: string; notes: string; update: Update }
  | { kind: "downloading"; pct: number }
  | { kind: "ready" }
  | { kind: "error"; msg: string };

function formatHotkey(s: string): string {
  // macOS: "Super+Shift+KeyV" → "⌘⇧V"; elsewhere → "Win+Shift+V" / "Ctrl+Alt+4".
  const parts = s.split("+").map((p) => p.trim()).filter(Boolean);
  if (IS_MAC) {
    const glyph: Record<string, string> = {
      Super: "⌘", Meta: "⌘", Cmd: "⌘", Command: "⌘",
      Shift: "⇧", Control: "⌃", Ctrl: "⌃", Alt: "⌥", Option: "⌥",
    };
    return parts.map((p) => glyph[p] ?? trimCode(p)).join("");
  }
  const name: Record<string, string> = {
    Super: "Win", Meta: "Win", Cmd: "Win", Command: "Win",
    Shift: "Shift", Control: "Ctrl", Ctrl: "Ctrl", Alt: "Alt", Option: "Alt",
  };
  const keys = parts.map((p) => name[p] ?? trimCode(p));
  const mods = keys.slice(0, -1);
  const last = keys[keys.length - 1];
  return `${mods.map((m) => m + "+").join("")}${last}`;
}

function trimCode(p: string): string {
  if (p.startsWith("Key")) return p.slice(3);
  if (p.startsWith("Digit")) return p.slice(5);
  return p;
}

interface HotkeysInfo {
  drawer: string;
  screenshot: string;
  clothesline: string;
  screenshot_registered: boolean;
  clothesline_registered: boolean;
}

function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [version, setVersion] = useState<string>("");
  const [acc, setAcc] = useState<boolean | null>(null);
  const [upd, setUpd] = useState<UpdateStatus>({ kind: "idle" });
  const [hks, setHks] = useState<HotkeysInfo | null>(null);
  const [autostart, setAutostart] = useState<boolean>(false);
  const [langPref, setLangPref] = useState<LangPref>(() => getPref());

  const reloadHotkeys = useCallback(async () => {
    setHks(await invoke<HotkeysInfo>("get_hotkeys"));
  }, []);

  const recheck = useCallback(async () => {
    const ok = await invoke<boolean>("check_accessibility");
    setAcc(ok);
  }, []);

  const checkForUpdate = useCallback(async () => {
    setUpd({ kind: "checking" });
    try {
      const update = await checkUpdate();
      if (update) {
        setUpd({
          kind: "available",
          version: update.version,
          notes: update.body ?? "",
          update,
        });
      } else {
        setUpd({ kind: "uptodate" });
      }
    } catch (e: unknown) {
      setUpd({ kind: "error", msg: e instanceof Error ? e.message : String(e) });
    }
  }, []);

  useEffect(() => {
    invoke<string>("app_version").then(setVersion);
    reloadHotkeys();
    invoke<boolean>("autostart_enabled").then(setAutostart);
    recheck();
    checkForUpdate();
    const t = setInterval(recheck, 1500);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      clearInterval(t);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [recheck, onClose, checkForUpdate, reloadHotkeys]);

  const toggleAutostart = useCallback(async (on: boolean) => {
    setAutostart(on);
    try {
      await invoke("set_autostart", { enabled: on });
    } catch (e) {
      setAutostart(!on);
      console.warn("set_autostart failed:", e);
    }
  }, []);

  const [backupMsg, setBackupMsg] = useState<string | null>(null);
  const doExportBackup = useCallback(async () => {
    setBackupMsg(t("settings.exporting"));
    try {
      const path = await invoke<string>("export_backup");
      setBackupMsg(`${t("settings.exported")} ${path}`);
    } catch (e) {
      setBackupMsg(`${t("settings.exportFail")} ${e}`);
    }
  }, []);
  const doImportBackup = useCallback(async () => {
    setBackupMsg(t("settings.importing"));
    try {
      const msg = await invoke<string>("import_backup");
      setBackupMsg(msg);
    } catch (e) {
      setBackupMsg(`${t("settings.importFail")} ${e}`);
    }
  }, []);

  const downloadAndInstall = useCallback(async () => {
    if (upd.kind !== "available") return;
    let total = 0;
    let downloaded = 0;
    setUpd({ kind: "downloading", pct: 0 });
    try {
      await upd.update.downloadAndInstall((ev) => {
        if (ev.event === "Started") {
          total = ev.data.contentLength ?? 0;
        } else if (ev.event === "Progress") {
          downloaded += ev.data.chunkLength;
          setUpd({
            kind: "downloading",
            pct: total > 0 ? Math.round((downloaded / total) * 100) : 0,
          });
        } else if (ev.event === "Finished") {
          setUpd({ kind: "ready" });
        }
      });
      await relaunch();
    } catch (e: unknown) {
      setUpd({ kind: "error", msg: e instanceof Error ? e.message : String(e) });
    }
  }, [upd]);

  const grant = useCallback(async () => {
    await invoke("request_accessibility");
    await invoke("open_accessibility_settings");
  }, []);

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-head">
          <h3>{t("settings.title")}</h3>
          <button className="settings-close" onClick={onClose} title="关闭">✕</button>
        </div>
        <div className="settings-section">
          <div className="settings-row">
            <span className="settings-label">{t("settings.version")}</span>
            <span className="settings-value">
              <span>{version || "..."}</span>
              {upd.kind === "checking" && <span className="settings-tag muted">{t("settings.checking")}</span>}
              {upd.kind === "uptodate" && (
                <>
                  <span className="settings-tag ok">{t("settings.uptodate")}</span>
                  <button className="btn ghost" onClick={checkForUpdate}>{t("settings.recheck")}</button>
                </>
              )}
              {upd.kind === "available" && (
                <button className="btn primary" onClick={downloadAndInstall}>
                  {t("settings.upgrade")} {upd.version}
                </button>
              )}
              {upd.kind === "downloading" && (
                <span className="settings-tag muted">{t("settings.download")} {upd.pct}%</span>
              )}
              {upd.kind === "ready" && <span className="settings-tag ok">{t("settings.restarting")}</span>}
              {(upd.kind === "error" || upd.kind === "idle") && (
                <button className="btn ghost" onClick={checkForUpdate}>{t("settings.checkUpdate")}</button>
              )}
            </span>
          </div>
          {upd.kind === "error" && (
            <pre className="settings-err">{t("settings.updateFailed")}:{upd.msg}</pre>
          )}
          {upd.kind === "available" && upd.notes && (
            <pre className="settings-notes">{upd.notes}</pre>
          )}

          <div className="settings-subhead">{t("settings.hotkeys")}</div>
          <HotkeyRow
            kind="drawer"
            label={t("settings.hk.drawer")}
            value={hks?.drawer ?? ""}
            onSaved={reloadHotkeys}
          />
          <HotkeyRow
            kind="screenshot"
            label={t("settings.hk.screenshot")}
            value={hks?.screenshot ?? ""}
            registered={hks?.screenshot_registered ?? true}
            onSaved={reloadHotkeys}
          />
          <HotkeyRow
            kind="clothesline"
            label={t("settings.hk.clothesline")}
            value={hks?.clothesline ?? ""}
            registered={hks?.clothesline_registered ?? true}
            onSaved={reloadHotkeys}
          />

          <div className="settings-subhead">{t("settings.general")}</div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.language")}</span>
            <span className="settings-value">
              <select
                className="lang-select"
                value={langPref}
                onChange={(e) => {
                  const v = e.target.value as "auto" | "zh" | "en";
                  setPref(v);
                  setLangPref(v);
                }}
              >
                <option value="auto">{t("settings.langAuto")}</option>
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.autostart")}</span>
            <span className="settings-value">
              <button
                className={"btn " + (autostart ? "primary" : "ghost")}
                onClick={() => toggleAutostart(!autostart)}
              >
                {autostart ? t("settings.on") : t("settings.off")}
              </button>
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.backup")}</span>
            <span className="settings-value">
              <button className="btn ghost" onClick={doExportBackup}>
                {t("settings.export")}
              </button>
              <button className="btn ghost" onClick={doImportBackup}>
                {t("settings.import")}
              </button>
            </span>
          </div>
          {backupMsg && <pre className="settings-notes">{backupMsg}</pre>}

          {IS_MAC && (
            <>
              <div className="settings-row">
                <span className="settings-label">{t("settings.accessibility")}</span>
                <span className="settings-value">
                  {acc === null ? (
                    <span className="settings-tag muted">{t("settings.detecting")}</span>
                  ) : acc ? (
                    <span className="settings-tag ok">{t("settings.granted")}</span>
                  ) : (
                    <button className="btn primary" onClick={grant}>{t("settings.grant")}</button>
                  )}
                </span>
              </div>
              {acc === false && (
                <p className="settings-hint">
                  {t("settings.accHint")}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** One rebindable hotkey row: current combo, 修改 → capture → 确定/取消. */
function HotkeyRow({
  kind,
  label,
  value,
  registered = true,
  onSaved,
}: {
  kind: string;
  label: string;
  value: string;
  registered?: boolean;
  onSaved: () => void;
}) {
  const [recording, setRecording] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const startRecording = useCallback(async () => {
    setErr(null);
    setPending(null);
    // suspend the current global combo so pressing it during capture
    // doesn't fire the OS handler (e.g. close the drawer)
    await invoke("begin_hotkey_capture", { kind }).catch(() => {});
    setRecording(true);
  }, [kind]);

  const cancelRecording = useCallback(async () => {
    setRecording(false);
    setPending(null);
    setErr(null);
    await invoke("cancel_hotkey_capture", { kind }).catch(() => {});
  }, [kind]);

  const confirmRecording = useCallback(async () => {
    if (!pending) {
      cancelRecording();
      return;
    }
    try {
      await invoke("set_hotkey", { kind, value: pending });
      setRecording(false);
      setPending(null);
      setErr(null);
      onSaved();
    } catch (e) {
      setErr(String(e));
      await invoke("cancel_hotkey_capture", { kind }).catch(() => {});
      setRecording(false);
      setPending(null);
    }
  }, [pending, cancelRecording, kind, onSaved]);

  // restore the global combo if the row unmounts mid-capture
  useEffect(() => {
    return () => {
      if (recording) {
        invoke("cancel_hotkey_capture", { kind }).catch(() => {});
      }
    };
  }, [recording, kind]);

  const captureHotkey = useCallback(
    (e: React.KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.key === "Escape") {
        cancelRecording();
        return;
      }
      if (e.key === "Enter") {
        confirmRecording();
        return;
      }
      const mods: string[] = [];
      if (e.metaKey) mods.push("Super");
      if (e.ctrlKey) mods.push("Control");
      if (e.altKey) mods.push("Alt");
      if (e.shiftKey) mods.push("Shift");
      const c = e.code;
      const isKey =
        c.startsWith("Key") || c.startsWith("Digit") || /^F\d+$/.test(c) || c === "Space";
      if (!isKey) return; // wait for a real key, ignore standalone modifier presses
      if (mods.length === 0) {
        setErr(t("settings.needMod"));
        return;
      }
      setPending([...mods, c].join("+"));
      setErr(null);
    },
    [cancelRecording, confirmRecording],
  );

  return (
    <div className="settings-row">
      <span className="settings-label">{label}</span>
      <span className="settings-value">
        {recording ? (
          <>
            <input
              className="hotkey-capture"
              autoFocus
              readOnly
              placeholder={t("settings.capturePlaceholder")}
              value={pending ? formatHotkey(pending) : ""}
              onKeyDown={captureHotkey}
            />
            <button className="btn primary" onClick={confirmRecording} disabled={!pending}>
              {t("settings.ok")}
            </button>
            <button className="btn ghost" onClick={cancelRecording}>
              {t("settings.cancel")}
            </button>
          </>
        ) : (
          <>
            <span className="hotkey-badge">{value ? formatHotkey(value) : "..."}</span>
            {!registered && (
              <span className="settings-tag err">{t("settings.regFail")}</span>
            )}
            <button className="btn ghost" onClick={startRecording}>
              {t("settings.modify")}
            </button>
          </>
        )}
      </span>
      {err && <pre className="settings-err">{err}</pre>}
    </div>
  );
}


function Header({
  query,
  setQuery,
  tab,
  setTab,
  counts,
  searchRef,
}: {
  query: string;
  setQuery: (v: string) => void;
  tab: FilterTab;
  setTab: (t: FilterTab) => void;
  counts: Record<string, number>;
  searchRef: React.RefObject<HTMLInputElement>;
}) {
  return (
    <div className="bar-header">
      <label className="search">
        <SearchIcon />
        <input
          ref={searchRef}
          placeholder={t("search.placeholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="kbd">{MOD}F</span>
      </label>
      <div className="type-tabs">
        {TYPE_TABS.map((tb) => (
          <button
            key={tb.id}
            className={"tab" + (tab === tb.id ? " active" : "")}
            onClick={() => setTab(tb.id)}
          >
            <span className="dot-sm" style={{ background: tb.dot }} />
            {t(tb.labelKey)}
            <span className="count">{counts[tb.id] ?? 0}</span>
          </button>
        ))}
      </div>
      <div className="header-right">
        <button className="icon-btn" title="设置" onClick={() => invoke("open_settings")}>
          <GearIcon />
        </button>
      </div>
    </div>
  );
}

function FolderChips({
  folders,
  folderId,
  setFolderId,
  counts,
}: {
  folders: Folder[];
  folderId: number | "pinned" | null;
  setFolderId: (id: number | "pinned" | null) => void;
  counts: { pinned: number };
}) {
  // native prompt() dialogs never open inside WebView2 — inline input instead
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const submit = async () => {
    const n = name.trim();
    setAdding(false);
    setName("");
    if (n) await invoke("create_folder", { name: n, color: pickColor() });
  };
  return (
    <div className="folders">
      <button
        className={"chip" + (folderId === null ? " active" : "")}
        onClick={() => setFolderId(null)}
      >
        {t("tab.all")}
      </button>
      <button
        className={"chip" + (folderId === "pinned" ? " active" : "")}
        onClick={() => setFolderId("pinned")}
      >
        <PinIcon size={11} /> {t("tab.pinned")} <span className="dim">{counts.pinned}</span>
      </button>
      {folders.map((f) => (
        <button
          key={f.id}
          className={"chip" + (folderId === f.id ? " active" : "")}
          onClick={() => setFolderId(f.id)}
        >
          <span className="swatch" style={{ background: f.color }} />
          {f.name}
        </button>
      ))}
      {adding ? (
        <input
          className="chip-input"
          autoFocus
          placeholder={t("folder.newPlaceholder")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => {
            if (!name.trim()) setAdding(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            } else if (e.key === "Escape") {
              e.preventDefault();
              setAdding(false);
              setName("");
            }
          }}
        />
      ) : (
        <button className="chip ghost" onClick={() => setAdding(true)}>
          {t("folder.new")}
        </button>
      )}
    </div>
  );
}

function Card({
  item,
  idx,
  selected,
  beingDragged,
  multiSelected,
  onClick,
  onDoubleClick,
  onPin,
  onEdit,
  onDelete,
  onPaste,
}: {
  item: ClipItem;
  idx: number;
  selected: boolean;
  beingDragged: boolean;
  multiSelected: boolean;
  onClick: (e: React.MouseEvent) => void;
  onDoubleClick: () => void;
  onPin: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onPaste: () => void;
}) {
  // Drag tracking (window listeners + ghost) lives in App — see cardDrag.
  // The card only registers the drag start and swallows the click that
  // trails a real drag.
  const clickSuppressed = () => Date.now() - lastCardDragEnd < CARD_DRAG_SUPPRESS_MS;

  return (
    <div
      data-idx={idx}
      className={
        "card" +
        (selected ? " selected" : "") +
        (beingDragged ? " lifting" : "") +
        (multiSelected ? " multi-sel" : "")
      }
      onClick={(e) => {
        if (clickSuppressed()) return;
        onClick(e);
      }}
      onDoubleClick={() => {
        if (!clickSuppressed()) onDoubleClick();
      }}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        cardDrag.current = { itemId: item.id, startY: e.screenY, moved: false, inZone: false };
      }}
      title={t("card.hint")}
    >
      <span className={"badge " + item.kind}>{kindLabel(item.kind)}</span>
      {item.pinned && (
        <span className="pin">
          <PinIcon />
        </span>
      )}
      <CardBody item={item} />
      <div className="meta">
        <span className="src">{item.source_app || "—"}</span>
        <span>{relTime(item.used_at)}</span>
      </div>
      {idx < 10 && <div className="index-kbd">{MOD}{idx === 9 ? 0 : idx + 1}</div>}
      <div className="actions" onClick={(e) => e.stopPropagation()}>
        <button className="action primary" onClick={onPaste}>{t("card.paste")}</button>
        <button className="action" onClick={onPin} title="置顶">📌</button>
        <button className="action" onClick={onEdit} title="编辑">✎</button>
        <button className="action" onClick={onDelete} title="删除">🗑</button>
      </div>
    </div>
  );
}

function CardBody({ item }: { item: ClipItem }) {
  if (item.kind === "image") {
    return (
      <div
        className="img"
        style={{
          backgroundImage: `url(data:image/png;base64,${item.preview})`,
        }}
      />
    );
  }
  if (item.kind === "color") {
    return (
      <>
        <div className="swatch-big" style={{ background: item.content }} />
        <div className="color-row">
          <b>{item.content}</b>
        </div>
      </>
    );
  }
  if (item.kind === "code") {
    return <pre className="body mono">{truncate(item.content, 240)}</pre>;
  }
  if (item.kind === "link") {
    return (
      <div className="body">
        <div className="link-title">{item.preview || item.content}</div>
        <div className="link-url">{item.content}</div>
      </div>
    );
  }
  return <div className="body">{truncate(item.content, 240)}</div>;
}

function EditCard({
  item,
  value,
  setValue,
  onCancel,
  onSave,
  onSaveAndPaste,
  textareaRef,
}: {
  item: ClipItem;
  value: string;
  setValue: (v: string) => void;
  onCancel: () => void;
  onSave: () => void;
  onSaveAndPaste: () => void;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
}) {
  return (
    <div className="edit-card">
      <div className="edit-head">
        <span className={"badge " + item.kind}>{kindLabel(item.kind)}</span>
        <span className="edit-hint">{t("edit.badge")}</span>
      </div>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            onSaveAndPaste();
          } else if ((e.metaKey || e.ctrlKey) && e.key === "s") {
            e.preventDefault();
            onSave();
          }
        }}
      />
      <div className="edit-foot">
        <span>{value.length} 字符 · {value.split("\n").length} 行</span>
        <div className="edit-btns">
          <button className="btn ghost" onClick={onCancel}>{t("edit.cancel")}</button>
          <button className="btn primary" onClick={onSaveAndPaste}>{t("edit.savePaste")}</button>
        </div>
      </div>
    </div>
  );
}

function Footer({ count, total }: { count: number; total: number }) {
  return (
    <div className="bar-foot">
      <div className="hints">
        <span><span className="kbd">←</span> <span className="kbd">→</span> {t("footer.switch")}</span>
        <span><span className="kbd">↵</span> {t("footer.paste")}</span>
        <span><span className="kbd">{MOD}</span><span className="kbd">1-0</span> {t("footer.direct")}</span>
        <span><span className="kbd">{MOD}</span><span className="kbd">E</span> {t("footer.edit")}</span>
        <span><span className="kbd">{MOD}</span><span className="kbd">P</span> {t("footer.pin")}</span>
        <span><span className="kbd">{MOD}</span><span className="kbd">D</span> {t("footer.del")}</span>
      </div>
      <div>
        {count}/{total} <span className="kbd">Esc</span> {t("footer.close")}
      </div>
    </div>
  );
}

/**
 * Full-size image preview overlay. Pulls the original PNG bytes via
 * get_item_image and renders them as a blob URL; falls back to the stored
 * thumbnail when the full blob has been trimmed away. Esc / backdrop click
 * closes (Esc is handled in App's key handler, which closes before the
 * drawer gets it).
 */
function ZoomOverlay({ item, onClose }: { item?: ClipItem; onClose: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [full, setFull] = useState(true);

  useEffect(() => {
    let revoke: string | null = null;
    let alive = true;
    (async () => {
      if (!item) return;
      try {
        const bytes = await invoke<number[]>("get_item_image", { id: item.id });
        if (!alive) return;
        const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
        revoke = URL.createObjectURL(blob);
        setUrl(revoke);
      } catch {
        // blob trimmed — fall back to the base64 thumbnail
        if (!alive || !item.preview) return;
        revoke = `data:image/png;base64,${item.preview}`;
        setUrl(revoke);
        setFull(false);
      }
    })();
    return () => {
      alive = false;
      if (revoke && revoke.startsWith("blob:")) URL.revokeObjectURL(revoke);
    };
  }, [item]);

  if (!item) return null;
  return (
    <div className="zoom-overlay" onClick={onClose}>
      <div className="zoom-stage" onClick={(e) => e.stopPropagation()}>
        {url ? (
          <img className="zoom-img" src={url} alt={item.content} />
        ) : (
          <div className="zoom-loading">原图加载中…</div>
        )}
        <div className="zoom-meta">
          <span>{item.content}</span>
          <span>
            {full ? "原图" : "缩略图"} · {fmtBytes(item.byte_size)} · Esc 关闭
          </span>
        </div>
      </div>
    </div>
  );
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function Empty() {
  return (
    <div className="empty">
      <div className="empty-icon">📋</div>
      <h3>{t("empty.title")}</h3>
      <p>{t("empty.desc")}</p>
    </div>
  );
}

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function PinIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2z" />
    </svg>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function relTime(unixSec: number): string {
  const diff = Math.floor(Date.now() / 1000 - unixSec);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}天前`;
  return new Date(unixSec * 1000).toLocaleDateString();
}

const FOLDER_COLORS = ["#ff9500", "#34c759", "#5856d6", "#ff2d55", "#007aff", "#af52de", "#ffcc00"];
function pickColor(): string {
  return FOLDER_COLORS[Math.floor(Math.random() * FOLDER_COLORS.length)];
}
