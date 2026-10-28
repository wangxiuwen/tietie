import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { ClipItem } from "./types";
import { kindLabel } from "./types";
import { matchQuery } from "./search";
import { t, useLang } from "./i18n";
import { onFontScaleChange } from "./fontScale";

/**
 * 剪贴板库 — full-window management table over the whole history:
 * search (incl. pinyin initials), multi-select rows, batch delete and
 * text export. Opened from the tray menu; closing hides the window.
 */
export default function Library() {
  useLang();
  useEffect(() => onFontScaleChange(() => setItems((x) => [...x])), []);
  const [items, setItems] = useState<ClipItem[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  // rich-row detail overlay opened by double-click (direction 199)
  const [richView, setRichView] = useState<ClipItem | null>(null);
  // folder names for the ownership column (direction 147)
  const [folders, setFolders] = useState<{ id: number; name: string }[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [stats, setStats] = useState<ClipStats | null>(null);
  type SortKey = "time" | "kind" | "size" | "source";
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>(() => {
    // filter memory (direction 75): structural filters survive reopens
    try {
      const raw = localStorage.getItem("lib-sort");
      const v = raw ? JSON.parse(raw) : null;
      if (
        v &&
        ["time", "kind", "size", "source"].includes(v.key) &&
        (v.dir === 1 || v.dir === -1)
      ) {
        return v as { key: SortKey; dir: 1 | -1 };
      }
    } catch { /* fall through to default */ }
    return { key: "time", dir: -1 };
  });
  useEffect(() => {
    localStorage.setItem("lib-sort", JSON.stringify(sort));
  }, [sort]);

  interface ClipStats {
    total: number;
    today: number;
    pinned: number;
    by_kind: [string, number][];
    top_sources: [string, number][];
  }

  const refresh = useCallback(async () => {
    setItems(await invoke<ClipItem[]>("list_items", { limit: 500 }));
    setStats(await invoke<ClipStats>("clip_stats"));
    // folder names ride the same refresh so later-created folders appear
    invoke<{ id: number; name: string }[]>("list_folders").then(setFolders).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const unlistens: UnlistenFn[] = [];
    listen("clipboard-changed", refresh).then((u) => unlistens.push(u));
    listen("library-open", refresh).then((u) => unlistens.push(u));
    return () => unlistens.forEach((u) => u());
  }, [refresh]);


  // kind filter (direction 75): chips over text/link/image/code/color
  const [kindFilter, setKindFilter] = useState<string>(
    () => localStorage.getItem("lib-kind") || "all",
  );
  useEffect(() => {
    localStorage.setItem("lib-kind", kindFilter);
  }, [kindFilter]);
  const filtered = useMemo(() => {
    let base = kindFilter !== "all" ? items.filter((x) => x.kind === kindFilter) : items;
    if (query.trim()) {
      const q = query.trim();
      base = base.filter((x) => matchQuery(x.content, x.preview + " " + (x.note ?? ""), q));
    }
    const dir = sort.dir;
    return base.slice().sort((a, b) => {
      switch (sort.key) {
        case "kind":
          return a.kind.localeCompare(b.kind) * dir;
        case "size":
          return (a.byte_size - b.byte_size) * dir;
        case "source":
          return (a.source_app ?? "").localeCompare(b.source_app ?? "") * dir;
        default:
          return (a.used_at - b.used_at) * dir;
      }
    });
  }, [items, query, sort, kindFilter]);

  const sortBy = (key: SortKey) =>
    setSort((s) =>
      s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: key === "time" ? -1 : 1 },
    );

  const allSelected = filtered.length > 0 && filtered.every((x) => selected.has(x.id));

  const toggle = (id: number) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };
  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(filtered.map((x) => x.id)));
  };

  const del = useCallback(async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    const n = await invoke<number>("delete_items", { ids });
    setSelected(new Set());
    setMsg(`${t("lib.deleted")} ${n}`);
    await refresh();
  }, [selected, refresh]);

  // export filter (direction 88): pinned-only overrides the row selection
  const [pinnedOnly, setPinnedOnly] = useState(false);
  const pinnedIds = useMemo(
    () => filtered.filter((x) => x.pinned).map((x) => x.id),
    [filtered],
  );
  const exportTargets = pinnedOnly ? pinnedIds : [...selected];

  const exportText = useCallback(async () => {
    const ids = exportTargets;
    if (ids.length === 0) return;
    try {
      const path = await invoke<string>("export_selected_text", { ids });
      setMsg(`已导出: ${path}`);
      invoke("reveal_path", { path }).catch(() => {}); // open at the file
    } catch (e) {
      setMsg(`导出失败: ${e}`);
    }
  }, [exportTargets]);

  const exportMarkdown = useCallback(async () => {
    const ids = exportTargets;
    if (ids.length === 0) return;
    try {
      const path = await invoke<string>("export_selected_markdown", { ids });
      setMsg(`已导出: ${path}`);
      invoke("reveal_path", { path }).catch(() => {}); // open at the file
    } catch (e) {
      setMsg(`导出失败: ${e}`);
    }
  }, [exportTargets]);

  const exportCsv = useCallback(async () => {
    const ids = exportTargets;
    if (ids.length === 0) return;
    try {
      const path = await invoke<string>("export_selected_csv", { ids });
      setMsg(`已导出: ${path}`);
      invoke("reveal_path", { path }).catch(() => {}); // open at the file
    } catch (e) {
      setMsg(`导出失败: ${e}`);
    }
  }, [exportTargets]);

  // swatch-grid view over the color-kind items (direction 51)
  const [view, setView] = useState<"table" | "palette">(
    () => (localStorage.getItem("lib-view") === "palette" ? "palette" : "table"),
  );
  useEffect(() => {
    localStorage.setItem("lib-view", view);
  }, [view]);
  const colors = useMemo(
    () => filtered.filter((x) => x.kind === "color"),
    [filtered],
  );
  const copyColor = useCallback((hex: string) => {
    navigator.clipboard.writeText(hex).catch(() => {});
    setMsg(`${t("lib.copied")} ${hex}`);
  }, []);

  // keyboard rows (direction 72): ↑/↓ move a cursor, ↵ copies the row,
  // Del removes it — the table works without touching the mouse. The
  // cursor is index-based over `filtered` and skipped while typing in the
  // search box or in the palette view.
  const [cursor, setCursor] = useState(-1);
  // sensitive rows stay masked until their text is clicked, then show for 5s
  // before re-masking automatically (direction 123, same UX as cards in 113)
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const revealRow = useCallback((id: number) => {
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
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      // the detail overlay owns Escape even while a field is focused —
      // an open modal must not strand the user (direction 199)
      if (richView) {
        if (e.key === "Escape") setRichView(null);
        return;
      }
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (view !== "table" || filtered.length === 0) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setCursor((c) =>
          e.key === "ArrowDown"
            ? Math.min(c + 1, filtered.length - 1)
            : Math.max(c - 1, 0),
        );
      } else if ((e.ctrlKey || e.metaKey) && (e.key === "a" || e.key === "A")) {
        // Ctrl+A selects the current filter results (direction 180) — same
        // toggle semantics as the header checkbox (all-on → clears)
        e.preventDefault();
        setSelected((prev) =>
          filtered.every((x) => prev.has(x.id))
            ? new Set()
            : new Set(filtered.map((x) => x.id)),
        );
      } else if (e.key === "Enter" && cursor >= 0 && cursor < filtered.length) {
        e.preventDefault();
        const it = filtered[cursor];
        if (it.kind !== "image") {
          navigator.clipboard.writeText(it.content).catch(() => {});
          setMsg(copiedMsg(it));
        }
      } else if ((e.key === "Delete" || e.key === "Backspace") && cursor >= 0) {
        e.preventDefault();
        const it = filtered[cursor];
        invoke<number>("delete_items", { ids: [it.id] }).then((n) => {
          setMsg(`${t("lib.deleted")} ${n}`);
          refresh();
          setCursor((c) => Math.min(c, filtered.length - 2));
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, filtered, cursor, refresh, richView]);

  // keep the cursor row visible
  useEffect(() => {
    if (cursor < 0 || view !== "table") return;
    const el = document.querySelector(
      `.lib-table tbody tr:nth-child(${cursor + 1})`,
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor, view]);

  return (
    <div className="lib">
      <div className="lib-head">
        <h2>{t("lib.title")}</h2>
        <input
          className="lib-search"
          placeholder={t("search.library")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            // Esc clears an active query (direction 204 companion) — the ×
            // button needs pointer travel, Esc is the keyboard twin
            if (e.key === "Escape" && query) {
              e.preventDefault();
              setQuery("");
            }
          }}
        />
        {query && (
          <button
            className="lib-clear"
            aria-label={t("search.clear")}
            title={t("search.clear")}
            onClick={() => setQuery("")}
          >
            ×
          </button>
        )}
        <button
          className={"btn ghost" + (view === "palette" ? " active" : "")}
          onClick={() => setView(view === "palette" ? "table" : "palette")}
        >
          {t("lib.palette")}
        </button>
        <select
          className="lang-select"
          value={kindFilter}
          aria-label={t("lib.kindFilter")}
          title={t("lib.kindFilter")}
          onChange={(e) => setKindFilter(e.target.value)}
        >
          <option value="all">{t("tab.all")}</option>
          <option value="text">{t("kind.text")}</option>
          <option value="link">{t("kind.link")}</option>
          <option value="image">{t("kind.image")}</option>
          <option value="code">{t("kind.code")}</option>
          <option value="color">{t("kind.color")}</option>
        </select>
        <button className="btn ghost" onClick={() => getCurrentWindow().hide()}>
          {t("lib.collapse")}
        </button>
      </div>
      {stats && (
        <div className="stats-bar">
          <div className="stat-cell">
            <b>{stats.total}</b>
            <span>{t("st.total")}</span>
          </div>
          <div className="stat-cell">
            <b>{stats.today}</b>
            <span>{t("st.today")}</span>
          </div>
          <div className="stat-cell">
            <b>{stats.pinned}</b>
            <span>{t("st.pinned")}</span>
          </div>
          <div className="stat-kinds">
            {stats.by_kind.map(([k, n]) => (
              <div key={k} className="stat-row">
                <span className={"po-kind kind-" + k}>{kindLabel(k)}</span>
                <div className="stat-track">
                  <div className="stat-fill" style={{ width: `${(n / stats.total) * 100}%` }} />
                </div>
                <span className="stat-n">{n}</span>
              </div>
            ))}
          </div>
          {stats.top_sources.length > 0 && (
            <div className="stat-sources">
              {stats.top_sources.map(([s, n]) => (
                <span key={s} className="stat-src">
                  {s} <b>{n}</b>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {view === "palette" ? (
        <div className="palette-grid">
          {colors.map((it) => (
            <button
              key={it.id}
              className="palette-cell"
              title={it.content}
              onClick={() => copyColor(it.content)}
            >
              <span className="palette-chip" style={{ background: it.content }} />
              <span className="palette-hex">{it.content}</span>
            </button>
          ))}
          {colors.length === 0 && (
            <div className="po-empty">{t("lib.paletteEmpty")}</div>
          )}
        </div>
      ) : (
      <div className="lib-table-wrap">
        <table className="lib-table">
          <thead>
            <tr>
              <th className="w-check">
                <input type="checkbox" checked={allSelected} onChange={toggleAll} />
              </th>
              <th className="w-kind">
                <button className={"th-sort" + (sort.key === "kind" ? " on" : "")} onClick={() => sortBy("kind")}>
                  {t("lib.kind")}{sort.key === "kind" ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
                </button>
              </th>
              <th>{t("lib.content")}</th>
              <th className="w-src">
                <button className={"th-sort" + (sort.key === "source" ? " on" : "")} onClick={() => sortBy("source")}>
                  {t("lib.source")}{sort.key === "source" ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
                </button>
              </th>
              <th className="w-folder">{t("lib.folder")}</th>
              <th className="w-size">
                <button className={"th-sort" + (sort.key === "size" ? " on" : "")} onClick={() => sortBy("size")}>
                  {t("lib.size")}{sort.key === "size" ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
                </button>
              </th>
              <th className="w-time">
                <button className={"th-sort" + (sort.key === "time" ? " on" : "")} onClick={() => sortBy("time")}>
                  {t("lib.time")}{sort.key === "time" ? (sort.dir === 1 ? " ↑" : " ↓") : ""}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it, idx) => (
              <tr
                key={it.id}
                className={
                  (selected.has(it.id) ? "sel " : "") +
                  (idx === cursor ? " kcursor" : "")
                }
                onClick={(e) => {
                  // Ctrl/⌘+click a link row opens it in the system browser
                  // instead of toggling selection (direction 106)
                  if ((e.ctrlKey || e.metaKey) && it.kind === "link") {
                    e.stopPropagation();
                    invoke("open_url", { url: it.content }).catch(() => {});
                    return;
                  }
                  toggle(it.id);
                }}
                onDoubleClick={() => {
                  // rich/image rows open their detail overlay (direction 199);
                  // text rows keep the dblclick copy (direction 120)
                  if (it.rich_html || it.kind === "image") {
                    setRichView(it);
                    return;
                  }
                  navigator.clipboard
                    .writeText(it.content)
                    .then(() => {
                      setMsg(copiedMsg(it));
                    })
                    .catch(() => {});
                }}
                onMouseDown={(e) => {
                  // middle-click deletes the row (direction 195): mirrors the
                  // tray/card middle-click pin idiom; preventDefault keeps the
                  // WebView out of autoscroll mode
                  if (e.button === 1) {
                    e.preventDefault();
                    invoke<number>("delete_items", { ids: [it.id] }).then((n) => {
                      setMsg(`${t("lib.deleted")} ${n}`);
                      refresh();
                    }).catch(() => {});
                  }
                }}
              >
                <td className="w-check">
                  <input
                    type="checkbox"
                    checked={selected.has(it.id)}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => toggle(it.id)}
                  />
                </td>
                <td className="w-kind">
                  <span className={"badge " + it.kind}>
                    {kindLabel(it.kind)}
                  </span>
                </td>
                <td
                  className="w-content"
                  title={
                    it.sensitive && !revealed.has(it.id) ? undefined : it.content
                  }
                >
                  {it.sensitive && !revealed.has(it.id) ? (
                    // masked sensitive row (direction 123): click reveals for 5s
                    <span
                      className="lib-row-text lib-masked"
                      onClick={(e) => {
                        e.stopPropagation();
                        revealRow(it.id);
                      }}
                    >
                      •••••••• 🔒 {t("card.tapReveal")}
                    </span>
                  ) : (
                    <span className="lib-row-text">
                      {oneLine(it.kind === "image" ? it.content : it.content).slice(0, 80)}
                    </span>
                  )}
                  {it.kind !== "image" && (
                    <button
                      className="lib-row-copy"
                      title={t("lib.copyRow")}
                      aria-label={t("lib.copyRow")}
                      onClick={(e) => {
                        e.stopPropagation();
                        navigator.clipboard.writeText(it.content).catch(() => {});
                        setMsg(copiedMsg(it));
                      }}
                    >
                      ⧉
                    </button>
                  )}
                </td>
                <td className="w-src">{it.source_app || "—"}</td>
                <td className="w-folder" title={it.folder_id == null ? "" : folders.find((f) => f.id === it.folder_id)?.name}>
                  {it.folder_id == null ? "—" : (folders.find((f) => f.id === it.folder_id)?.name ?? "?")}
                </td>
                <td className="w-size">{fmtBytes(it.byte_size)}</td>
                <td className="w-time">{relTime(it.used_at)}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="lib-empty">
                  {query ? t("lib.noMatch") : t("lib.empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      )}
      <div className="lib-foot">
        <span>
          {t("lib.total")} {filtered.length} {t("lib.items")} · {t("lib.selected")} {selected.size} {t("lib.items")}
        </span>
        {msg && <span className="lib-msg">{msg}</span>}
        <div className="lib-actions">
          <label className="lib-pinonly" title={t("lib.pinnedOnlyHint")}>
            <input
              type="checkbox"
              checked={pinnedOnly}
              onChange={(e) => setPinnedOnly(e.target.checked)}
            />
            {t("lib.pinnedOnly")} ({pinnedIds.length})
          </label>
          <button
            className="btn ghost"
            onClick={exportText}
            disabled={exportTargets.length === 0}
          >
            {t("lib.export")}
          </button>
          <button
            className="btn ghost"
            onClick={exportMarkdown}
            disabled={exportTargets.length === 0}
          >
            {t("lib.exportMd")}
          </button>
          <button
            className="btn ghost"
            onClick={exportCsv}
            disabled={exportTargets.length === 0}
          >
            {t("lib.exportCsv")}
          </button>
          <button className="btn primary" onClick={del} disabled={selected.size === 0}>
            {t("lib.delete")}
          </button>
        </div>
      </div>
      {richView && <DetailOverlay item={richView} onClose={() => setRichView(null)} />}
    </div>
  );
}

function oneLine(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/** Copied-status line: never echo sensitive content into the status bar,
 * even while that row is revealed (direction 123). */
function copiedMsg(it: ClipItem): string {
  return `${t("lib.copied")} ${it.sensitive ? "🔒" : oneLine(it.content).slice(0, 24)}`;
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function relTime(unixSec: number): string {
  const diff = Math.floor(Date.now() / 1000 - unixSec);
  if (diff < 60) return t("rt.now");
  if (diff < 3600) return `${Math.floor(diff / 60)}${t("rt.min")}`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}${t("rt.hour")}`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}${t("rt.day")}`;
  return new Date(unixSec * 1000).toLocaleDateString();
}

/** Row-detail overlay (direction 199): rich rows render their captured HTML
 *  in a sandboxed iframe, image rows show the ORIGINAL PNG (not the b64
 *  thumbnail) — text rows never get here, they keep dblclick-copy. */
function DetailOverlay({ item, onClose }: { item: ClipItem; onClose: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let revoke: string | null = null;
    let alive = true;
    (async () => {
      if (item.rich_html) return; // rich rows need no fetch
      try {
        const bytes = await invoke<number[]>("get_item_image", { id: item.id });
        if (!alive) return;
        const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
        revoke = URL.createObjectURL(blob);
        setUrl(revoke);
      } catch {
        if (!alive || !item.preview) return;
        setUrl(`data:image/png;base64,${item.preview}`);
      }
    })();
    return () => {
      alive = false;
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [item.id, item.kind, item.rich_html, item.preview]);

  return (
    <div className="zoom-overlay" onClick={onClose}>
      <div className="zoom-stage" onClick={(e) => e.stopPropagation()}>
        {item.rich_html ? (
          <iframe
            className="rich-frame"
            sandbox=""
            srcDoc={`<meta charset="utf-8"><body style="margin:12px;font:13px/1.6 -apple-system,sans-serif">${item.rich_html}</body>`}
            title="rich"
          />
        ) : url ? (
          <img className="zoom-img" src={url} alt={item.content} />
        ) : (
          <div className="zoom-loading">…</div>
        )}
        <div className="zoom-meta">
          <span>{oneLine(item.content).slice(0, 60)}</span>
          <span>Esc</span>
        </div>
      </div>
    </div>
  );
}
