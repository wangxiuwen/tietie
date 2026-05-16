import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { writeText, writeImage } from "@tauri-apps/plugin-clipboard-manager";
import type { ClipItem, Folder, ItemKind } from "./types";
import { KIND_LABEL } from "./types";

type FilterTab = "all" | ItemKind;

const TYPE_TABS: { id: FilterTab; label: string; dot: string }[] = [
  { id: "all", label: "全部", dot: "var(--accent)" },
  { id: "text", label: "文本", dot: "var(--cat-text)" },
  { id: "link", label: "链接", dot: "var(--cat-link)" },
  { id: "image", label: "图片", dot: "var(--cat-image)" },
  { id: "code", label: "代码", dot: "var(--cat-code)" },
  { id: "color", label: "颜色", dot: "var(--cat-color)" },
];

export default function App() {
  const [items, setItems] = useState<ClipItem[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [tab, setTab] = useState<FilterTab>("all");
  const [folderId, setFolderId] = useState<number | "pinned" | null>(null);
  const [query, setQuery] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [editing, setEditing] = useState<ClipItem | null>(null);
  const [editValue, setEditValue] = useState("");
  const [drawerVisible, setDrawerVisible] = useState(false);
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
    }).then((u) => unlistens.push(u));
    return () => unlistens.forEach((u) => u());
  }, [refresh]);

  const filtered = useMemo(() => {
    let xs = items;
    if (folderId === "pinned") xs = xs.filter((x) => x.pinned);
    else if (typeof folderId === "number") xs = xs.filter((x) => x.folder_id === folderId);
    if (tab !== "all") xs = xs.filter((x) => x.kind === tab);
    if (query.trim()) {
      const q = query.toLowerCase();
      xs = xs.filter(
        (x) => x.preview.toLowerCase().includes(q) || x.content.toLowerCase().includes(q),
      );
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
    if (item.kind === "image") {
      try {
        const bytes = await invoke<number[]>("get_item_image", { id: item.id });
        await writeImage(new Uint8Array(bytes));
      } catch (e) {
        console.error(e);
      }
    } else {
      await writeText(item.content);
    }
    await invoke("touch_item", { id: item.id });
    // paste_back hides the drawer, restores focus to the previously-active app,
    // and synthesizes ⌘V so the content is actually pasted (not just copied).
    await invoke("paste_back");
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
    setEditing(null);
    await refresh();
    if (alsoPaste) {
      await writeText(editValue);
      await invoke("paste_back");
    }
  }, [editing, editValue, refresh]);

  // keyboard navigation
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (editing) return; // edit textarea handles its own keys
      const isMod = e.metaKey || e.ctrlKey;

      if (e.key === "Escape") {
        invoke("hide_window");
        return;
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        setSelectedIdx((i) => Math.min(i + 1, Math.max(0, filtered.length - 1)));
        return;
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setSelectedIdx((i) => Math.max(0, i - 1));
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
      if (isMod && /^[1-9]$/.test(e.key)) {
        e.preventDefault();
        const i = Number(e.key) - 1;
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
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filtered, selectedIdx, tab, editing, paste, togglePin, deleteItem, startEdit]);

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
                    onClick={() => setSelectedIdx(idx)}
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
        <Footer count={filtered.length} total={items.length} />
      </div>
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
          placeholder="搜索剪切板历史 …"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="kbd">⌘F</span>
      </label>
      <div className="type-tabs">
        {TYPE_TABS.map((t) => (
          <button
            key={t.id}
            className={"tab" + (tab === t.id ? " active" : "")}
            onClick={() => setTab(t.id)}
          >
            <span className="dot-sm" style={{ background: t.dot }} />
            {t.label}
            <span className="count">{counts[t.id] ?? 0}</span>
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
  return (
    <div className="folders">
      <button
        className={"chip" + (folderId === null ? " active" : "")}
        onClick={() => setFolderId(null)}
      >
        全部
      </button>
      <button
        className={"chip" + (folderId === "pinned" ? " active" : "")}
        onClick={() => setFolderId("pinned")}
      >
        <PinIcon size={11} /> 置顶 <span className="dim">{counts.pinned}</span>
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
      <button
        className="chip ghost"
        onClick={async () => {
          const name = prompt("新建文件夹名称");
          if (!name) return;
          await invoke("create_folder", { name, color: pickColor() });
        }}
      >
        + 新建
      </button>
    </div>
  );
}

function Card({
  item,
  idx,
  selected,
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
  onClick: () => void;
  onDoubleClick: () => void;
  onPin: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onPaste: () => void;
}) {
  return (
    <div
      data-idx={idx}
      className={"card" + (selected ? " selected" : "")}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
    >
      <span className={"badge " + item.kind}>{KIND_LABEL[item.kind]}</span>
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
      {selected && idx < 9 && <div className="index-kbd">⌘{idx + 1}</div>}
      <div className="actions" onClick={(e) => e.stopPropagation()}>
        <button className="action primary" onClick={onPaste}>↵ 粘贴</button>
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
        <span className={"badge " + item.kind}>{KIND_LABEL[item.kind]}</span>
        <span className="edit-hint">编辑中 · 不影响其它条</span>
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
          <button className="btn ghost" onClick={onCancel}>Esc 取消</button>
          <button className="btn primary" onClick={onSaveAndPaste}>⌘↵ 保存并粘贴</button>
        </div>
      </div>
    </div>
  );
}

function Footer({ count, total }: { count: number; total: number }) {
  return (
    <div className="bar-foot">
      <div className="hints">
        <span><span className="kbd">←</span> <span className="kbd">→</span> 切换</span>
        <span><span className="kbd">↵</span> 粘贴</span>
        <span><span className="kbd">⌘</span><span className="kbd">1-9</span> 直选</span>
        <span><span className="kbd">⌘</span><span className="kbd">E</span> 编辑</span>
        <span><span className="kbd">⌘</span><span className="kbd">P</span> 置顶</span>
        <span><span className="kbd">⌘</span><span className="kbd">D</span> 删除</span>
      </div>
      <div>
        {count}/{total} <span className="kbd">Esc</span> 关闭
      </div>
    </div>
  );
}

function Empty() {
  return (
    <div className="empty">
      <div className="empty-icon">📋</div>
      <h3>剪切板还是空的</h3>
      <p>复制任何文本、链接、图片或代码，它会出现在这里</p>
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
