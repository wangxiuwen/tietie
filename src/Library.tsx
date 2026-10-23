import { useCallback, useEffect, useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { ClipItem } from "./types";
import { kindLabel } from "./types";
import { matchQuery } from "./search";
import { t, useLang } from "./i18n";

/**
 * 剪贴板库 — full-window management table over the whole history:
 * search (incl. pinyin initials), multi-select rows, batch delete and
 * text export. Opened from the tray menu; closing hides the window.
 */
export default function Library() {
  useLang();
  const [items, setItems] = useState<ClipItem[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [msg, setMsg] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setItems(await invoke<ClipItem[]>("list_items", { limit: 500 }));
  }, []);

  useEffect(() => {
    refresh();
    const unlistens: UnlistenFn[] = [];
    listen("clipboard-changed", refresh).then((u) => unlistens.push(u));
    listen("library-open", refresh).then((u) => unlistens.push(u));
    return () => unlistens.forEach((u) => u());
  }, [refresh]);

  const filtered = useMemo(
    () =>
      query.trim()
        ? items.filter((x) => matchQuery(x.content, x.preview, query))
        : items,
    [items, query],
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
      <div className="lib-table-wrap">
        <table className="lib-table">
          <thead>
            <tr>
              <th className="w-check">
                <input type="checkbox" checked={allSelected} onChange={toggleAll} />
              </th>
              <th className="w-kind">{t("lib.kind")}</th>
              <th>{t("lib.content")}</th>
              <th className="w-src">{t("lib.source")}</th>
              <th className="w-size">{t("lib.size")}</th>
              <th className="w-time">{t("lib.time")}</th>
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
