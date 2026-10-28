import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
// clipboard plugin no longer needed at JS layer — Rust paste_item handles it
import type { ClipItem, Folder, ItemKind } from "./types";
import { kindLabel } from "./types";
import { MOD } from "./platform";
import { matchQuery } from "./search";
import { hexToRgb } from "./color";
import { HighlightText } from "./highlight";
import { ContextMenu, type MenuItem } from "./ContextMenu";
import { CodeView } from "./codeView";
import { t, useLang } from "./i18n";
import { onFontScaleChange } from "./fontScale";

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
    startX: number;
    startY: number;
    moved: boolean;
    // multi-select group drag (direction 142): every selected id travels
    // together when the dragged card itself is part of the selection
    groupIds: number[] | null;
  },
};
// set when a drag actually moved; cards swallow the trailing click for 150ms
let lastCardDragEnd = 0;
const CARD_DRAG_SUPPRESS_MS = 150;
// session-level drawer scroll memory (direction 84): the horizontal card
// strip's last offset — restored on the next open, never persisted to disk
let drawerScrollLeft = 0;
// session-level search history (direction 90): the last 5 distinct
// non-empty queries, newest last; committed when the drawer opens with a
// query — the moment a search "counts" as done
const searchHist: string[] = [];
function searchHistory(): string[] {
  return searchHist;
}
function commitSearchHistory(q: string) {
  const v = q.trim();
  if (!v) return;
  const i = searchHist.indexOf(v);
  if (i >= 0) searchHist.splice(i, 1);
  searchHist.push(v);
  if (searchHist.length > 5) searchHist.shift();
  // mirror for the tray window (direction 171): module state can't cross
  // windows, same-origin localStorage can
  localStorage.setItem("tietie.searchHist", JSON.stringify(searchHist));
}

/** True when a keydown originates inside a text field (search box / editor). */
function typingInField(e: KeyboardEvent): boolean {
  return (
    e.target instanceof HTMLElement &&
    (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")
  );
}

const TYPE_TABS: { id: FilterTab; labelKey: string }[] = [
  { id: "all", labelKey: "tab.all", },
  { id: "text", labelKey: "kind.text", },
  { id: "link", labelKey: "kind.link", },
  { id: "image", labelKey: "kind.image", },
  { id: "code", labelKey: "kind.code", },
  { id: "color", labelKey: "kind.color", },
];

export default function App() {
  useLang(); // re-render the whole drawer on language switch
  useEffect(() => onFontScaleChange(() => setDrawerVisible((v) => v)), []);
  const [items, setItems] = useState<ClipItem[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [tab, setTab] = useState<FilterTab>("all");
  const [folderId, setFolderId] = useState<number | "pinned" | null>(null);
  // card / compact-list display mode (direction 52), persisted PER FOLDER
  // (direction 86): switching folders recalls that folder's last view.
  const folderKey = (f: number | "pinned" | null) =>
    `tietie-compact-${f == null ? "all" : f}`;
  const [compact, setCompactState] = useState(
    () => localStorage.getItem("tietie-compact") === "1",
  );
  const setCompact = useCallback((v: boolean | ((prev: boolean) => boolean)) => {
    setCompactState((prev) => {
      const next = typeof v === "function" ? v(prev) : v;
      const f = folderIdRef.current;
      if (f == null) {
        // toggling in 全部 writes the global key (= all's own memory)
        localStorage.setItem("tietie-compact", next ? "1" : "0");
      } else {
        // toggling inside a folder writes ONLY that folder's key — the
        // all-view memory is untouched (direction 86)
        localStorage.setItem(folderKey(f), next ? "1" : "0");
      }
      return next;
    });
  }, []);
  // ref mirrors folderId so the setter above always reads the fresh value
  const folderIdRef = useRef(folderId);
  // when the folder changes, restore that folder's remembered view; 全部
  // reads the global key, a never-visited folder keeps the current view
  useEffect(() => {
    folderIdRef.current = folderId;
    const per =
      folderId == null
        ? localStorage.getItem("tietie-compact")
        : localStorage.getItem(folderKey(folderId));
    if (per != null) setCompactState(per === "1");
  }, [folderId]);
  const [query, setQuery] = useState("");
  // sensitive-content reveal windows (direction 113): sensitive bodies stay
  // masked until clicked, then show for 5s before re-masking automatically
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const revealItem = useCallback((id: number) => {
    setRevealed((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    window.setTimeout(() => {
      setRevealed((prev) => {
        if (!prev.has(id)) return prev;
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }, 5000);
  }, []);
  // the show-drawer listener is registered once, so it reads the live
  // query through this ref to commit it into search history (direction 90)
  const queryRef = useRef("");
  queryRef.current = query;
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [editing, setEditing] = useState<ClipItem | null>(null);
  const [editValue, setEditValue] = useState("");
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  // folder chip under the pointer during a card drag (drop-to-file target)
  const [dropFolder, setDropFolder] = useState<string | null>(null);
  // folders folded to a swatch-only chip (direction 173): double-click a chip
  // to fold/unfold — a folded folder stays a drop target
  const [foldedFolders, setFoldedFolders] = useState<Set<number>>(new Set());
  const [zoomId, setZoomId] = useState<number | null>(null);
  // ⌘/Ctrl+click multi-select for batch delete / hang
  const [multiSel, setMultiSel] = useState<Set<number>>(new Set());
  // two-step confirm on 批量删除 when the group is large (direction 202,
  // same pattern as 153): first click arms, second executes; 3s timeout
  const DEL_CONFIRM_N = 5;
  const [delArmed, setDelArmed] = useState(false);
  const delArmTimer = useRef<number | null>(null);
  useEffect(() => {
    // selection changed → drop the armed state
    setDelArmed(false);
    if (delArmTimer.current) window.clearTimeout(delArmTimer.current);
  }, [multiSel]);
  // right-click context menu on cards
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; itemId: number } | null>(null);
  // ? cheatsheet overlay
  const [cheatsheet, setCheatsheet] = useState(false);
  // what a card double-click does (direction 68): paste / copy / edit
  const [dblAction, setDblAction] = useState<"paste" | "copy" | "edit">("paste");
  useEffect(() => {
    invoke<string>("dblclick_action").then((a) => {
      if (a === "copy" || a === "edit") setDblAction(a);
    });
  }, []);
  // rendered rich-HTML preview of a clip item
  const [richView, setRichView] = useState<ClipItem | null>(null);
  // per-item note editor (direction 74): the card being annotated
  const [noteEdit, setNoteEdit] = useState<ClipItem | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
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
      // a query that was still in the box at reopen counts as a finished
      // search — commit it to the session history (direction 90)
      commitSearchHistory(queryRef.current);
      // re-read the double-click preference: it can change in settings
      // while this window lives on (direction 68)
      try {
        const a = await invoke<string>("dblclick_action");
        if (a === "copy" || a === "edit") setDblAction(a);
        else setDblAction("paste");
      } catch { /* keep current */ }
      requestAnimationFrame(() => searchRef.current?.focus());
    }).then((u) => unlistens.push(u));
    listen<null>("hide-drawer", () => {
      setCtxMenu(null);
      setDrawerVisible(false);
      setEditing(null);
      // The drawer can hide mid-drag (Esc, focus loss) while the OS cursor
      // is grabbed — release it or the hidden window keeps eating the mouse.
      getCurrentWindow().setCursorGrab(false).catch(() => {});
      document.body.classList.remove("dragging-hang");
      // session-level scroll memory (direction 84): snapshot the horizontal
      // card-strip offset so the next open lands where the user left off
      if (cardsRef.current) {
        drawerScrollLeft = cardsRef.current.scrollLeft;
      }
    }).then((u) => unlistens.push(u));
    return () => unlistens.forEach((u) => u());
  }, [refresh]);

  // restore the remembered scroll position once the strip has laid out
  useEffect(() => {
    if (!drawerVisible || !cardsRef.current) return;
    const el = cardsRef.current;
    if (drawerScrollLeft > 0 && el.scrollWidth > el.clientWidth) {
      const target = drawerScrollLeft;
      // wait a frame so the cards have real widths before scrolling back
      requestAnimationFrame(() => {
        el.scrollTo({ left: target });
      });
    }
  }, [drawerVisible, items.length]);

  // One window-level drag tracker for every card (see cardDrag above).
  // 挂绳手势已随晾衣架功能下线（2026-10-27）：拖拽仅保留文件夹归类。
  useEffect(() => {
    const lastPointer = { x: 0, y: 0 };
    const onMove = (e: PointerEvent) => {
      lastPointer.x = e.clientX;
      lastPointer.y = e.clientY;
      const st = cardDrag.current;
      if (!st || (e.buttons & 1) === 0) return;
      if (!st.moved) {
        if (Math.abs(st.startY - e.screenY) < 12 && Math.abs(st.startX - e.screenX) < 12) return;
        st.moved = true;
        setDraggingId(st.itemId);
        // grab the OS cursor so events keep flowing after leaving the window
        getCurrentWindow().setCursorGrab(true).catch(() => {});
        document.body.classList.add("dragging-hang");
      }
      // drag-to-folder: highlight the chip under the pointer
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const chip = el?.closest?.("[data-folder-id]");
      const fid = chip?.getAttribute("data-folder-id") ?? null;
      // "pinned" is a filter, not a folder — not a drop target
      setDropFolder(fid && fid !== "pinned" ? fid : null);
    };
    const onFinish = () => {
      const st = cardDrag.current;
      if (!st) return;
      cardDrag.current = null;
      document.body.classList.remove("dragging-hang");
      getCurrentWindow().setCursorGrab(false).catch(() => {});
      setDraggingId(null);
      setDropFolder(null);
      if (st.moved) {
        lastCardDragEnd = Date.now();
        const chip = document
          .elementFromPoint(lastPointer.x, lastPointer.y)
          ?.closest?.("[data-folder-id]");
        const fid = chip?.getAttribute("data-folder-id");
        if (fid && fid !== "pinned") {
          // dropped on a folder chip → file it there ("all" clears); a
          // multi-select group files together (direction 142)
          const target = fid === "all" ? null : Number(fid);
          const ids = st.groupIds && st.groupIds.length > 1 ? st.groupIds : [st.itemId];
          Promise.all(
            ids.map((id) => invoke("set_item_folder", { id, folderId: target })),
          )
            .then(() => refresh())
            .catch(() => {});
          if (st.groupIds && st.groupIds.length > 1) setMultiSel(new Set());
          setDropFolder(null);
        }
      }
    };
    const onUp = () => onFinish();
    const onCancel = () => onFinish();
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
      // masked sensitive cards stay out of search entirely (direction 183):
      // matching them would leak content hints via highlight AND the count
      xs = xs.filter(
        (x) =>
          !x.sensitive &&
          matchQuery(x.content, x.preview + " " + (x.note ?? ""), query, x.kind),
      );
    }
    return xs.slice().sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      // while searching, frequently-used items rank first (Everything-style
      // "gets better as you use it"); recency drives the unfiltered list
      if (query.trim() && a.use_count !== b.use_count) {
        return b.use_count - a.use_count;
      }
      return b.used_at - a.used_at;
    });
  }, [items, folderId, tab, query]);

  // 🔒 entries inside the active multi-select (direction 169): batch actions
  // (paste-back / hang) would bypass their masking, so the bar warns
  const multiSelSensitive = items.filter((x) => multiSel.has(x.id) && x.sensitive).length;

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

  // configurable double-click behavior (direction 68): paste / copy / edit
  const dblAct = useCallback(
    (it: ClipItem) => {
      if (dblAction === "copy") {
        navigator.clipboard.writeText(it.content).catch(() => {});
      } else if (dblAction === "edit") {
        startEdit(it);
      } else {
        paste(it);
      }
    },
    [dblAction, paste, startEdit],
  );

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
      // ↑/↓ alias ←/→: the strip is a single horizontal row, but up-down
      // matches the muscle memory of vertical list navigation.
      // Shift+↑/↓ extends the multi-selection instead of moving; plain
      // arrows move the selection.
      if (["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"].includes(e.key)) {
        e.preventDefault();
        if (editing) setEditing(null);
        if (zoomId !== null) setZoomId(null);
        const extend = e.shiftKey && (e.key === "ArrowDown" || e.key === "ArrowUp");
        if (extend) {
          const cur = filtered[selectedIdx];
          if (cur) {
            setMultiSel((s) => {
              const n = new Set(s);
              n.add(cur.id);
              return n;
            });
          }
        }
        if (e.key === "ArrowRight" || e.key === "ArrowDown") {
          const next = Math.min(selectedIdx + 1, Math.max(0, filtered.length - 1));
          if (extend && filtered[next]) {
            const add = filtered[next].id;
            setMultiSel((s) => new Set(s).add(add));
          }
          setSelectedIdx(next);
        } else {
          const prev = Math.max(0, selectedIdx - 1);
          if (extend && filtered[prev]) {
            const add = filtered[prev].id;
            setMultiSel((s) => new Set(s).add(add));
          }
          setSelectedIdx(prev);
        }
        return;
      }

      // Context-menu key / Shift+F10 opens the selected card's menu at the
      // card itself — every context action (copy / pin / hang / file /
      // sensitive / delete) then works with arrows + Enter.
      if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) {
        const it = filtered[selectedIdx];
        if (it) {
          e.preventDefault();
          const el = cardsRef.current?.querySelector<HTMLElement>(
            `[data-idx="${selectedIdx}"]`,
          );
          const r = el?.getBoundingClientRect();
          setCtxMenu({
            x: r ? r.left + r.width / 2 : window.innerWidth / 2,
            y: r ? r.top + r.height / 2 : window.innerHeight / 2,
            itemId: it.id,
          });
        }
        return;
      }

      // Space toggles the full-size zoom on the selected image card
      // (click is the mouse path).
      if (e.key === " " && !editing) {
        const it = filtered[selectedIdx];
        if (it && it.kind === "image") {
          e.preventDefault();
          setZoomId((z) => (z === it.id ? null : it.id));
        }
        return;
      }

      if (editing) return; // textarea handles the rest

      if (e.key === "?" || (e.key === "/" && e.shiftKey)) {
        if (!editing) {
          e.preventDefault();
          setCheatsheet((c) => !c);
        }
        return;
      }

      if (e.key === "Escape") {
        // Esc ladder (direction 80): every overlay peels off one layer per
        // press, from innermost outward — note editor → context menu →
        // rich preview → cheatsheet → image zoom → multi-select → drawer.
        // Editing bails above: the textarea closes itself.
        if (noteEdit) {
          e.preventDefault();
          setNoteEdit(null);
          return;
        }
        if (ctxMenu) {
          e.preventDefault();
          setCtxMenu(null);
          return;
        }
        if (richView) {
          e.preventDefault();
          setRichView(null);
          return;
        }
        if (cheatsheet) {
          e.preventDefault();
          setCheatsheet(false);
          return;
        }
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
        if (!it) return;
        // masked sensitive card: Enter reveals first instead of pasting
        // (direction 198) — a blind paste would leak 🔒 content to whatever
        // app is focused; the second Enter (within the reveal window) pastes
        if (it.sensitive && !revealed.has(it.id)) {
          e.preventDefault();
          revealItem(it.id);
          return;
        }
        paste(it);
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
      // N opens the note editor for the selected card (direction 104);
      // while typing in the search box only ⌘/Ctrl+N fires so plain "n"
      // still types normally
      // N or B opens the note editor for the selected card (directions 104
      // and 138); while typing in the search box only ⌘/Ctrl+N fires so
      // plain "n"/"b" still type normally
      if (
        (e.key.toLowerCase() === "n" || e.key.toLowerCase() === "b") &&
        (!typingInField(e) || (isMod && e.key.toLowerCase() === "n"))
      ) {
        e.preventDefault();
        const it = filtered[selectedIdx];
        if (it) {
          setNoteEdit(it);
          setNoteDraft(it.note ?? "");
        }
        return;
      }
      if (isMod && e.key.toLowerCase() === "f") {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      // rgb() copy for the selected color card (the RGB button is the
      // mouse path)
      if (isMod && e.key.toLowerCase() === "r") {
        const it = filtered[selectedIdx];
        if (it && it.kind === "color") {
          e.preventDefault();
          navigator.clipboard
            .writeText(hexToRgb(it.content))
            .catch(() => {});
        }
        return;
      }
      // ⌘/Ctrl+J opens the selected link card in the system browser
      // (direction 149); non-link cards ignore the chord
      if (isMod && e.key.toLowerCase() === "j") {
        const it = filtered[selectedIdx];
        if (it && it.kind === "link") {
          e.preventDefault();
          invoke("open_url", { url: it.content }).catch(() => {});
        }
        return;
      }
    }
    // Capture phase — runs before the search input's own keydown handling,
    // so preventDefault actually stops ⌘D / ⌘P / etc. from typing into search.
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [filtered, selectedIdx, tab, editing, zoomId, multiSel.size, cheatsheet, richView, noteEdit, ctxMenu, paste, togglePin, deleteItem, startEdit, revealed, revealItem]);

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
          compact={compact}
          setCompact={setCompact}
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
          dropFolder={dropFolder}
          foldedFolders={foldedFolders}
          onToggleFold={(id) =>
            setFoldedFolders((s) => {
              const n = new Set(s);
              if (n.has(id)) n.delete(id);
              else n.add(id);
              return n;
            })
          }
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
            <Empty hasItems={items.length > 0} query={query} inFolder={folderId != null} />
          ) : (
            <div className="cards" ref={cardsRef} role="listbox" aria-label={t("a11y.cards")}>
              {filtered.map((it, idx) => {
              // day separator before the first card of each new local day
              // (direction 177) — pinned-first order just yields more groups
              const dayOf = (ts: number) => {
                const d = new Date(ts * 1000);
                return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
              };
              const sep =
                idx > 0 && dayOf(it.used_at) !== dayOf(filtered[idx - 1].used_at)
                  ? dayLabel(it.used_at)
                  : null;
              const node =
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
                ) : compact ? (
                  <CardRow
                    key={it.id}
                    item={it}
                    idx={idx}
                    selected={idx === selectedIdx}
                    query={query}
                    revealed={revealed.has(it.id)}
                    onReveal={() => revealItem(it.id)}
                    onContext={(x, y) => setCtxMenu({ x, y, itemId: it.id })}
                    onClick={() => {
                      setSelectedIdx(idx);
                      if (it.kind === "image") setZoomId(it.id);
                      else setZoomId(null);
                    }}
                    onDoubleClick={() => dblAct(it)}
                  />
                ) : (
                  <Card
                    key={it.id}
                    item={it}
                    idx={idx}
                    selected={idx === selectedIdx}
                    beingDragged={draggingId === it.id}
                    multiSelected={multiSel.has(it.id)}
                    dragGroupIds={multiSel.has(it.id) ? [...multiSel] : null}
                    query={query}
                    revealed={revealed.has(it.id)}
                    onReveal={() => revealItem(it.id)}
                    onRichView={() => setRichView(it)}
                    onContext={(x, y) => setCtxMenu({ x, y, itemId: it.id })}
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
                    onDoubleClick={() => dblAct(it)}
                    onSearchTerm={(term) => {
                      setQuery(term);
                      searchRef.current?.focus();
                    }}
                    onPin={() => togglePin(it.id)}
                    onEdit={() => startEdit(it)}
                    onDelete={() => deleteItem(it.id)}
                    onPaste={() => paste(it)}
                  />
                );
              return (
                <Fragment key={it.id}>
                  {sep && <div className="day-sep" role="presentation">{sep}</div>}
                  {node}
                </Fragment>
              );
              })}
            </div>
          )}
        </div>
        {multiSel.size > 0 && (
          <div className="batch-bar">
            <span>
              {t("batch.selected")} {multiSel.size}
              {multiSelSensitive > 0 && (
                <span className="batch-sens" title={t("batch.sensitiveHint")}>
                  ⚠ {multiSelSensitive} 🔒
                </span>
              )}
            </span>
            <button
              className={"btn primary" + (delArmed ? " arm" : "")}
              onClick={async () => {
                if (multiSel.size > DEL_CONFIRM_N && !delArmed) {
                  // large group → require a second click within 3s
                  setDelArmed(true);
                  if (delArmTimer.current) window.clearTimeout(delArmTimer.current);
                  delArmTimer.current = window.setTimeout(() => setDelArmed(false), 3000);
                  return;
                }
                if (delArmTimer.current) window.clearTimeout(delArmTimer.current);
                const ids = [...multiSel];
                setMultiSel(new Set());
                await invoke("delete_items", { ids }).catch(() => {});
              }}
            >
              {delArmed && multiSel.size > DEL_CONFIRM_N
                ? t("batch.deleteConfirm")
                : t("batch.delete")}
            </button>
            <button className="btn ghost" onClick={() => setMultiSel(new Set())}>
              {t("batch.clear")}
            </button>
          </div>
        )}
        <Footer count={filtered.length} total={items.length} searching={query.trim().length > 0} />
        {cheatsheet && <Cheatsheet onClose={() => setCheatsheet(false)} />}

        {richView && <RichOverlay item={richView} onClose={() => setRichView(null)} />}

        {noteEdit && (
          <NoteOverlay
            item={noteEdit}
            draft={noteDraft}
            setDraft={setNoteDraft}
            onClose={() => setNoteEdit(null)}
            onSave={async () => {
              try {
                await invoke("set_item_note", { id: noteEdit.id, note: noteDraft });
              } finally {
                setNoteEdit(null);
                refresh();
              }
            }}
          />
        )}

        {zoomId !== null && (
          <ZoomOverlay
            item={items.find((x) => x.id === zoomId) ?? filtered.find((x) => x.id === zoomId)}
            onClose={() => setZoomId(null)}
          />
        )}
        {ctxMenu && (
          <ContextMenu
            x={ctxMenu.x}
            y={ctxMenu.y}
            items={buildCtxItems({
              item: items.find((i) => i.id === ctxMenu.itemId),
              folders,
              paste,
              togglePin,
              deleteItem,
              refresh,
              onFile: async (id, folderId) => {
                await invoke("set_item_folder", { id, folderId });
                refresh();
              },
              onNote: (it) => {
                setCtxMenu(null);
                setNoteEdit(it);
                setNoteDraft(it.note ?? "");
              },
            })}
            onClose={() => setCtxMenu(null)}
          />
        )}
      </div>
    </div>
  );
}

/** Context-menu entries for a clip card: copy / pin / hang / file / delete. */
function buildCtxItems({
  item,
  folders,
  paste,
  togglePin,
  deleteItem,
  refresh,
  onFile,
  onNote,
}: {
  item?: ClipItem;
  folders: Folder[];
  paste: (it: ClipItem) => void;
  togglePin: (id: number) => void;
  deleteItem: (id: number) => void;
  refresh: () => void;
  onFile: (id: number, folderId: number | null) => void;
  onNote: (it: ClipItem) => void;
}): MenuItem[] {
  if (!item) return [];
  const items: MenuItem[] = [
    { label: t("ctx.copy"), onClick: () => navigator.clipboard.writeText(item.content).catch(() => {}) },
    { label: t("ctx.pasteBack"), onClick: () => paste(item) },
    { label: item.pinned ? t("ctx.unpin") : t("ctx.pin"), onClick: () => { togglePin(item.id); } },
    {
      label: item.sensitive ? t("ctx.unmarkSensitive") : t("ctx.markSensitive"),
      onClick: () => {
        invoke("set_item_sensitive", { id: item.id, on: !item.sensitive })
          .catch((e) => console.warn("set_item_sensitive:", e))
          .finally(() => refresh());
      },
    },
    {
      label: item.note ? t("ctx.editNote") : t("ctx.addNote"),
      onClick: () => onNote(item),
    },
  ];
  if (folders.length > 0) {
    items.push({ separatorBefore: true, label: t("ctx.moveTo"), onClick: () => {} }); // header row
    for (const f of folders) {
      items.push({
        label: "　" + f.name,
        onClick: () => onFile(item.id, item.folder_id === f.id ? null : f.id),
      });
    }
    items.push({ label: t("ctx.clearFolder"), onClick: () => onFile(item.id, null) });
  }
  items.push({
    separatorBefore: true,
    danger: true,
    label: t("ctx.delete"),
    onClick: () => {
      deleteItem(item.id);
      refresh();
    },
  });
  return items;
}

function Header({
  compact,
  setCompact,
  query,
  setQuery,
  tab,
  setTab,
  counts,
  searchRef,
}: {
  compact: boolean;
  setCompact: (v: boolean) => void;
  query: string;
  setQuery: (v: string) => void;
  tab: FilterTab;
  setTab: (t: FilterTab) => void;
  counts: Record<string, number>;
  searchRef: React.RefObject<HTMLInputElement>;
}) {
  // session-level search history (direction 90): ↑ cycles the last 5
  // committed queries (committed = drawer opened with a non-empty query)
  const [histIdx, setHistIdx] = useState(-1);
  // focused-with-empty-query dropdown over the same history (direction 126)
  const [histOpen, setHistOpen] = useState(false);
  const histClose = useRef<number | null>(null);
  const histItems = [...searchHistory()].reverse(); // newest first
  return (
    <div className="bar-header">
      <label className="search">
        <SearchIcon />
        <input
          ref={searchRef}
          placeholder={t("search.placeholder")}
          aria-label={t("search.placeholder")}
          onFocus={() => {
            // refocus within the blur grace period must cancel the close
            if (histClose.current != null) {
              window.clearTimeout(histClose.current);
              histClose.current = null;
            }
            setHistOpen(true);
          }}
          onBlur={() => {
            // grace period so a click on a dropdown item still lands
            histClose.current = window.setTimeout(() => {
              histClose.current = null;
              setHistOpen(false);
            }, 150);
          }}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setHistIdx(-1);
          }}
          onKeyDown={(e) => {
            const hist = searchHistory();
            if (hist.length === 0) return;
            if (e.key === "ArrowUp") {
              e.preventDefault();
              const n = Math.min(histIdx + 1, hist.length - 1);
              if (n !== histIdx) {
                setHistIdx(n);
                setQuery(hist[hist.length - 1 - n]);
              }
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              const n = Math.max(histIdx - 1, -1);
              if (n !== histIdx) {
                setHistIdx(n);
                setQuery(n < 0 ? "" : hist[hist.length - 1 - n]);
              }
            }
          }}
        />
        {query && (
          <button
            type="button"
            className="search-clear"
            aria-label={t("search.clear")}
            title={t("search.clear")}
            // keep the input focused through the press; mousedown beats blur
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              setQuery("");
              setHistIdx(-1);
              searchRef.current?.focus();
            }}
          >
            ×
          </button>
        )}
        <span className="kbd">{MOD}F</span>
        {histOpen && !query && histItems.length > 0 && (
          <div className="search-hist" aria-label={t("search.histTitle")}>
            {histItems.map((h) => (
              <button
                key={h}
                type="button"
                className="search-hist-item"
                // mousedown beats the input's blur so the click still lands
                onMouseDown={(e) => {
                  e.preventDefault();
                  setQuery(h);
                  setHistIdx(-1);
                  setHistOpen(false);
                }}
              >
                <span className="search-hist-text">{h}</span>
              </button>
            ))}
          </div>
        )}
      </label>
      <div className="type-tabs">
        {TYPE_TABS.map((tb) => (
          <button
            key={tb.id}
            className={"tab" + (tab === tb.id ? " active" : "")}
            onClick={() => setTab(tb.id)}
          >
            {t(tb.labelKey)}
            <span className="count">{counts[tb.id] ?? 0}</span>
          </button>
        ))}
      </div>
      <div className="header-right">
        <button
          className="icon-btn"
          title={compact ? t("view.cards") : t("view.compact")}
          aria-label={compact ? t("view.cards") : t("view.compact")}
          onClick={() => setCompact(!compact)}
        >
          {compact ? <CardViewIcon /> : <RowViewIcon />}
        </button>
        <button className="icon-btn" title="设置" onClick={() => invoke("open_settings")}>
          <GearIcon />
        </button>
      </div>
    </div>
  );
}

function FolderChips({
  dropFolder,
  folders,
  folderId,
  setFolderId,
  counts,
  foldedFolders,
  onToggleFold,
}: {
  dropFolder: string | null;
  folders: Folder[];
  folderId: number | "pinned" | null;
  setFolderId: (id: number | "pinned" | null) => void;
  counts: { pinned: number };
  foldedFolders: Set<number>;
  onToggleFold: (id: number) => void;
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
        className={
          "chip" + (folderId === null ? " active" : "") + (dropFolder === "all" ? " drop-hot" : "")
        }
        data-folder-id="all"
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
      {folders.map((f) => {
        // folded to a bare swatch (direction 173): double-click toggles;
        // the data-folder-id stays so card drops still file into it
        const folded = foldedFolders.has(f.id);
        return (
          <button
            key={f.id}
            className={
              "chip" +
              (folderId === f.id ? " active" : "") +
              (dropFolder === String(f.id) ? " drop-hot" : "") +
              (folded ? " folded" : "")
            }
            data-folder-id={f.id}
            title={folded ? f.name : undefined}
            onClick={() => setFolderId(f.id)}
            onDoubleClick={(e) => {
              e.preventDefault();
              onToggleFold(f.id);
            }}
          >
            <span className="swatch" style={{ background: f.color }} />
            {!folded && f.name}
          </button>
        );
      })}
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
  dragGroupIds,
  query,
  revealed,
  onReveal,
  onRichView,
  onContext,
  onClick,
  onDoubleClick,
  onSearchTerm,
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
  /** non-null while this card is part of an active multi-select group */
  dragGroupIds: number[] | null;
  revealed: boolean;
  onReveal: () => void;
  query: string;
  onRichView: () => void;
  onContext: (x: number, y: number) => void;
  onClick: (e: React.MouseEvent) => void;
  onDoubleClick: () => void;
  /** domain badge on link cards taps this to filter (direction 166) */
  onSearchTerm: (term: string) => void;
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
      role="option"
      aria-selected={selected}
      aria-label={`${kindLabel(item.kind)}：${item.sensitive && !revealed ? "🔒" : cardAriaText(item)}`}
      onClick={(e) => {
        if (clickSuppressed()) return;
        onClick(e);
      }}
      onMouseDown={(e) => {
        if (e.button === 1) {
          // middle-click toggles pin (direction 162, mirrors the tray rows);
          // preventDefault keeps the WebView out of autoscroll mode
          e.preventDefault();
          onPin();
        }
      }}
      onDoubleClick={() => {
        if (!clickSuppressed()) onDoubleClick();
      }}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        cardDrag.current = {
          itemId: item.id,
          startX: e.screenX,
          startY: e.screenY,
          moved: false,
          groupIds: dragGroupIds,
        };
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onContext(e.clientX, e.clientY);
      }}
      title={t("card.hint")}
    >
      <span className={"badge " + item.kind}>{kindLabel(item.kind)}</span>
      {item.sensitive && <span className="lock" title={t("ctx.markSensitive")}>🔒</span>}
      {item.pinned && (
        <span className="pin">
          <PinIcon />
        </span>
      )}
      <CardBody
        item={item}
        query={query}
        onRich={onRichView}
        masked={item.sensitive && !revealed}
        onReveal={onReveal}
        onSearchTerm={onSearchTerm}
      />
      <div className="meta">
        <span className="src">{item.source_app || "—"}</span>
        {item.use_count > 1 && (
          <span className="use-count" title={t("card.useCount")}>×{item.use_count}</span>
        )}
        {item.note && (
          <span className="note" title={item.note}>📝 {truncate(item.note, 24)}</span>
        )}
        <span title={new Date(item.used_at * 1000).toLocaleString()}>
          {relTime(item.used_at)}
        </span>
      </div>
      {idx < 10 && <div className="index-kbd">{MOD}{idx === 9 ? 0 : idx + 1}</div>}
      <div className="actions" onClick={(e) => e.stopPropagation()}>
        <button className="action primary" onClick={onPaste}>{t("card.paste")}</button>
        <button
          className="action"
          title={t("ctx.copy")}
          aria-label={t("ctx.copy")}
          onClick={() => navigator.clipboard.writeText(item.content).catch(() => {})}
        >
          ⧉
        </button>
        {item.kind === "color" && (
          <button
            className="action"
            title={t("card.copyRgb")}
            aria-label={t("card.copyRgb")}
            onClick={() => navigator.clipboard.writeText(hexToRgb(item.content)).catch(() => {})}
          >
            RGB
          </button>
        )}
        {item.kind === "image" && (
          <button
            className="action"
            title={t("card.copyImage")}
            aria-label={t("card.copyImage")}
            onClick={() => invoke("copy_item_image", { id: item.id }).catch(() => {})}
          >
            🖼
          </button>
        )}
        <button className="action" onClick={onPin} title="置顶" aria-label={t("footer.pin")}>📌</button>
        <button className="action" onClick={onEdit} title="编辑" aria-label={t("footer.edit")}>✎</button>
        <button className="action" onClick={onDelete} title="删除" aria-label={t("footer.del")}>🗑</button>
      </div>
    </div>
  );
}

/** Short spoken-form text for a card (images: dimensions, not base64). */
/** Compact single-line row (direction 52): badge + one-line text + meta,
 *  same select/paste/context-menu semantics as the card. */
function CardRow({
  item,
  idx,
  selected,
  query,
  revealed,
  onReveal,
  onClick,
  onDoubleClick,
  onContext,
}: {
  item: ClipItem;
  idx: number;
  selected: boolean;
  query: string;
  revealed: boolean;
  onReveal: () => void;
  onClick: () => void;
  onDoubleClick: () => void;
  onContext: (x: number, y: number) => void;
}) {
  const text = item.kind === "image" ? `🖼 ${item.content}` : item.preview || item.content;
  const masked = item.sensitive && !revealed;
  return (
    <div
      data-idx={idx}
      role="option"
      aria-selected={selected}
      aria-label={`${kindLabel(item.kind)}：${masked ? "🔒" : cardAriaText(item)}`}
      className={"row-item" + (selected ? " selected" : "")}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onContext(e.clientX, e.clientY);
      }}
    >
      <span className={"badge " + item.kind}>{kindLabel(item.kind)}</span>
      <span
        className="row-text"
        onClick={
          masked
            ? (e) => {
                e.stopPropagation();
                onReveal();
              }
            : undefined
        }
      >
        {masked ? (
          `•••••••• 🔒 ${t("card.tapReveal")}`
        ) : (
          <HighlightText text={text} query={query} />
        )}
      </span>
      <span
        className="row-meta"
        title={new Date(item.used_at * 1000).toLocaleString()}
      >
        {item.sensitive && "🔒 "}
        {item.source_app || "—"} · {relTime(item.used_at)}
        {item.use_count > 1 && (
          <span className="use-count" title={t("card.useCount")}> ×{item.use_count}</span>
        )}
      </span>
      {item.pinned && (
        <span className="pin">
          <PinIcon />
        </span>
      )}
      {idx < 10 && (
        <span className="index-kbd">
          {MOD}
          {idx === 9 ? 0 : idx + 1}
        </span>
      )}
    </div>
  );
}

/** Registrable host of a link ("www." stripped); "" when unparseable. */
function linkDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function cardAriaText(item: ClipItem): string {
  const s = item.kind === "image" ? item.content : (item.preview || item.content);
  const one = s.replace(/\s+/g, " ").trim();
  return one.length > 60 ? one.slice(0, 60) + "…" : one;
}

function CardBody({
  item,
  query,
  onRich,
  masked,
  onReveal,
  onSearchTerm,
}: {
  item: ClipItem;
  query: string;
  onRich: () => void;
  masked: boolean;
  onReveal: () => void;
  onSearchTerm: (term: string) => void;
}) {
  // sensitive body stays masked until clicked (direction 113); the reveal
  // click only unmasks — it does not select the card
  if (masked) {
    return (
      <div
        className="body masked"
        onClick={(e) => {
          e.stopPropagation();
          onReveal();
        }}
      >
        •••••••• <span className="masked-hint">🔒 {t("card.tapReveal")}</span>
      </div>
    );
  }
  if (item.kind === "image") {
    return (
      <div
        className="img"
        // fade the decoded thumbnail in (direction 144): large base64
        // backgrounds pop in with a flash once decoded; the opacity
        // transition turns that pop into a gentle reveal
        style={{
          backgroundImage: `url(data:image/png;base64,${item.preview})`,
          animation: "img-fade-in 0.28s ease-out",
        }}
      >
        {/* dimensions chip on the corner (direction 187) — for image items
            the content column IS the WxH string */}
        <span className="img-dim">{item.content}</span>
      </div>
    );
  }
  if (item.kind === "color") {
    return (
      <>
        <div className="swatch-big" style={{ background: item.content }} />
        <div className="color-row">
          <b>{item.content}</b>
          <span className="color-alt">{hexToRgb(item.content)}</span>
        </div>
      </>
    );
  }
  if (item.rich_html) {
    // rendered rich text available — pinned corner badge opens the preview
    // (direction 79: corner placement survives any body truncation and is
    // identical on platforms where rich text rarely exists, e.g. Windows)
    return (
      <div className="body rich-wrap">
        <button className="rich-badge" title={t("rich.preview")} aria-label={t("rich.preview")} onClick={(e) => { e.stopPropagation(); onRich(); }}>
          ✦
        </button>
        <span>{truncate(item.content, 200)}</span>
      </div>
    );
  }
  if (item.kind === "code") {
    return (
      <pre className="body mono">
        {query.trim() ? (
          <HighlightText text={truncate(item.content, 240)} query={query} />
        ) : (
          <CodeView text={truncate(item.content, 240)} />
        )}
      </pre>
    );
  }
  if (item.kind === "link") {
    const domain = linkDomain(item.content);
    return (
      <div className="body">
        <div className="link-title">
          {/* inline link glyph: click copies the URL directly (direction 98) */}
          <button
            className="link-copy"
            title={t("ctx.copy")}
            aria-label={t("ctx.copy")}
            onClick={(e) => {
              e.stopPropagation();
              navigator.clipboard.writeText(item.content).catch(() => {});
            }}
          >
            🔗
          </button>
          <HighlightText text={item.preview || item.content} query={query} />
        </div>
        <div className="link-url">
          {/* registrable host as a glanceable badge (direction 118); click
              filters the list down to this domain (direction 166) */}
          {domain && (
            <button
              className="link-domain"
              title={t("card.filterDomain")}
              aria-label={t("card.filterDomain")}
              onClick={(e) => {
                e.stopPropagation();
                onSearchTerm(domain);
              }}
              // right-click opens the card's URL in the system browser
              // (direction 200) — the badge already knows the row is a link
              onContextMenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                invoke("open_url", { url: item.content }).catch(() => {});
              }}
            >
              {domain}
            </button>
          )}
          <HighlightText text={item.content} query={query} />
        </div>
      </div>
    );
  }
  return <div className="body"><HighlightText text={truncate(item.content, 240)} query={query} /></div>;
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

function Footer({
  count,
  total,
  searching,
}: {
  count: number;
  total: number;
  searching: boolean;
}) {
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
        {/* live status: hit count while searching (direction 62), otherwise
           visible/total so the bare "39/39" is self-explaining (direction 117) */}
        <span className={searching ? "hit-count" : undefined}>
          {searching ? `${t("footer.hits")} ` : `${t("footer.showing")} `}
          {count}/{total}
        </span>{" "}
        <span className="kbd">Esc</span> {t("footer.close")}
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
  // wheel zoom on the image (direction 190): 1 = natural size, clamped so
  // the image never leaves a usable range; resets when the item changes
  const [scale, setScale] = useState(1);
  useEffect(() => setScale(1), [item?.id]);
  // 1.2s ✓ flash after the right-click copy (direction 192)
  const [copiedFlash, setCopiedFlash] = useState(false);

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
          <img
            className="zoom-img"
            src={url}
            alt={item.content}
            style={{ transform: `scale(${scale})`, transformOrigin: "center center" }}
            onWheel={(e) => {
              e.preventDefault();
              setScale((k) => Math.min(4, Math.max(0.25, k * (e.deltaY < 0 ? 1.15 : 1 / 1.15))));
            }}
            // right-click copies the image straight to the clipboard
            // (direction 192) — no context menu over the enlarged view
            onContextMenu={(e) => {
              e.preventDefault();
              e.stopPropagation();
              invoke("copy_item_image", { id: item.id }).catch(() => {});
              setCopiedFlash(true);
              window.setTimeout(() => setCopiedFlash(false), 1200);
            }}
          />
        ) : (
          <div className="zoom-loading">原图加载中…</div>
        )}
        <div className="zoom-meta">
          <span>{item.content}</span>
          <span>
            {full ? "原图" : "缩略图"} · {fmtBytes(item.byte_size)} ·{" "}
            {copiedFlash ? "✓ 已复制" : "右键复制 · Esc 关闭"}
          </span>
        </div>
      </div>
    </div>
  );
}

/** ? — quick keyboard cheatsheet overlay (Esc closes). */
function Cheatsheet({ onClose }: { onClose: () => void }) {
  const rows: [string, string][] = [
    ["←/→/↑/↓", t("cs.nav")],
    ["↵", t("cs.paste")],
    [`${MOD}1…0`, t("cs.direct")],
    [`${MOD}F`, t("cs.search")],
    [`${MOD}E`, t("cs.edit")],
    [`${MOD}P`, t("cs.pin")],
    [`${MOD}D`, t("cs.del")],
    ["N", t("cs.note")],
    ["Tab", t("cs.tab")],
    [`${MOD}+点击 / ⇧↑↓`, t("cs.multi")],
    ["拖卡片→文件夹", t("cs.file")],
    ["右键 / Menu ⇧F10", t("cs.menu")],
    ["空格", t("cs.zoom")],
    [`${MOD}R`, t("cs.rgb")],
    [`${MOD}J`, t("cs.link")],
    ["Esc", t("cs.close")],
  ];
  return (
    <div className="cheat-overlay" onClick={onClose}>
      <div className="cheat-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-head">
          <h3>{t("cs.title")}</h3>
          <button className="settings-close" onClick={onClose} title={t("cs.close")}>✕</button>
        </div>
        <div className="cheat-grid">
          {rows.map(([k, v]) => (
            <div key={k} className="cheat-row">
              <span className="kbd">{k}</span>
              <span>{v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Per-item note editor (direction 74): small centered overlay, ⌘↵ saves. */
function NoteOverlay({
  item,
  draft,
  setDraft,
  onClose,
  onSave,
}: {
  item: ClipItem;
  draft: string;
  setDraft: (v: string) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <div className="zoom-overlay" onClick={onClose}>
      <div className="zoom-stage" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 460 }}>
        <div className="zoom-meta" style={{ marginBottom: 8 }}>
          <span>{truncate(item.content, 48)}</span>
        </div>
        <textarea
          autoFocus
          className="note-edit"
          value={draft}
          placeholder={t("ctx.notePlaceholder")}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Escape") {
              e.preventDefault();
              onClose();
            } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              onSave();
            }
          }}
          rows={3}
        />
        <div className="line-compose-foot" style={{ marginTop: 8 }}>
          <span style={{ flex: 1 }} />
          <button className="btn ghost" onClick={onClose}>{t("line.composeCancel")}</button>
          <button className="btn primary" onClick={onSave}>{t("line.save")}</button>
        </div>
      </div>
    </div>
  );
}

/** Rendered rich-HTML preview in a sandboxed iframe (no scripts). */
function RichOverlay({ item, onClose }: { item: ClipItem; onClose: () => void }) {
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const h = await invoke<string | null>("get_item_rich", { id: item.id });
        if (alive) setHtml(h);
      } catch {
        if (alive) setHtml(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [item.id]);

  return (
    <div className="zoom-overlay" onClick={onClose}>
      <div className="zoom-stage" onClick={(e) => e.stopPropagation()}>
        {html ? (
          <iframe
            className="rich-frame"
            sandbox=""
            srcDoc={`<meta charset="utf-8"><body style="margin:12px;font:13px/1.6 -apple-system,sans-serif">${html}</body>`}
            title="rich"
          />
        ) : (
          <div className="zoom-loading">…</div>
        )}
        <div className="zoom-meta">
          <span>{truncate(item.content, 60)}</span>
          <span>{t("rich.hint")} · Esc</span>
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

// rotating usage tip under the search-miss empty state (direction 165): the
// cursor advances each time the empty state is entered, so consecutive misses
// surface different capabilities
const EMPTY_TIP_KEYS = [
  "empty.tip1",
  "empty.tip2",
  "empty.tip3",
  "empty.tip4",
  "empty.tip5",
];
let emptyTipCursor = 0;

function Empty({
  hasItems,
  query,
  inFolder,
}: {
  hasItems: boolean;
  query: string;
  inFolder: boolean;
}) {
  // filtered to nothing while history exists (search miss / empty folder) —
  // a compact hint, not the first-run guidance (direction 107)
  if (hasItems) {
    const tip = t(EMPTY_TIP_KEYS[emptyTipCursor % EMPTY_TIP_KEYS.length]);
    emptyTipCursor += 1;
    return (
      <div className="empty">
        <div className="empty-icon">{query ? "🔍" : "🗂"}</div>
        <h3>{query ? t("empty.noMatch") : inFolder ? t("empty.emptyFolder") : t("empty.title")}</h3>
        {query && <p>{t("empty.noMatchDesc")}</p>}
        {query && <p className="empty-tip">💡 {tip}</p>}
      </div>
    );
  }
  return (
    <div className="empty">
      <div className="empty-icon">📋</div>
      <h3>{t("empty.title")}</h3>
      <p>{t("empty.desc")}</p>
      {/* first-run 3-step onboarding (direction 76) */}
      <div className="onboard">
        <div className="onboard-step">
          <span className="onboard-n">1</span>
          <span>{t("onboard.step1")}</span>
        </div>
        <div className="onboard-step">
          <span className="onboard-n">2</span>
          <span>{t("onboard.step2")}</span>
        </div>
        <div className="onboard-step">
          <span className="onboard-n">3</span>
          <span>{t("onboard.step3")}</span>
        </div>
      </div>
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

function RowViewIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function CardViewIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="4" y="4" width="16" height="16" rx="2" />
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

/** Day label for the list separators (direction 177): 今天 / 昨天 / M/D. */
function dayLabel(unixSec: number): string {
  const d = new Date(unixSec * 1000);
  const now = new Date();
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (sameDay(d, now)) return t("day.today");
  const yd = new Date(now.getTime() - 86400_000);
  if (sameDay(d, yd)) return t("day.yesterday");
  return `${d.getMonth() + 1}/${d.getDate()}`;
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
