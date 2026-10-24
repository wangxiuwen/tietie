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
  const [msg, setMsg] = useState<string | null>(null);
  const [stats, setStats] = useState<ClipStats | null>(null);
  type SortKey = "time" | "kind" | "size" | "source";
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "time", dir: -1 });

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
  }, []);

  useEffect(() => {
    refresh();
    const unlistens: UnlistenFn[] = [];
    listen("clipboard-changed", refresh).then((u) => unlistens.push(u));
    listen("library-open", refresh).then((u) => unlistens.push(u));
    return () => unlistens.forEach((u) => u());
  }, [refresh]);

  const filtered = useMemo(() => {
    const base = query.trim()
      ? items.filter((x) => matchQuery(x.content, x.preview, query))
      : items;
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
  }, [items, query, sort]);

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

  const exportText = useCallback(async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    try {
      const path = await invoke<string>("export_selected_text", { ids });
      setMsg(`已导出: ${path}`);
    } catch (e) {
      setMsg(`导出失败: ${e}`);
    }
  }, [selected]);

  const exportMarkdown = useCallback(async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    try {
      const path = await invoke<string>("export_selected_markdown", { ids });
      setMsg(`已导出: ${path}`);
    } catch (e) {
      setMsg(`导出失败: ${e}`);
    }
  }, [selected]);

  return (
    <div className="lib">
      <div className="lib-head">
        <h2>{t("lib.title")}</h2>
        <input
          className="lib-search"
          placeholder={t("search.library")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
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
            {filtered.map((it) => (
              <tr
                key={it.id}
                className={selected.has(it.id) ? "sel" : ""}
                onClick={() => toggle(it.id)}
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
                <td className="w-content" title={it.content}>
                  {oneLine(it.kind === "image" ? it.content : it.content).slice(0, 80)}
                </td>
                <td className="w-src">{it.source_app || "—"}</td>
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
      <div className="lib-foot">
        <span>
          {t("lib.total")} {filtered.length} {t("lib.items")} · {t("lib.selected")} {selected.size} {t("lib.items")}
        </span>
        {msg && <span className="lib-msg">{msg}</span>}
        <div className="lib-actions">
          <button className="btn ghost" onClick={exportText} disabled={selected.size === 0}>
            {t("lib.export")}
          </button>
          <button className="btn ghost" onClick={exportMarkdown} disabled={selected.size === 0}>
            {t("lib.exportMd")}
          </button>
          <button className="btn primary" onClick={del} disabled={selected.size === 0}>
            {t("lib.delete")}
          </button>
        </div>
      </div>
    </div>
  );
}

function oneLine(s: string): string {
  return s.replace(/\s+/g, " ").trim();
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
