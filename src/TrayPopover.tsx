import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { ClipItem } from "./types";
import { kindLabel } from "./types";
import { MOD } from "./platform";
import { matchQuery } from "./search";
import { HighlightText } from "./highlight";
import { t, useLang } from "./i18n";
import { onFontScaleChange } from "./fontScale";


export default function TrayPopover() {
  useLang();
  useEffect(() => onFontScaleChange(() => setItems((x) => [...x])), []);
  const [items, setItems] = useState<ClipItem[]>([]);
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(0); // arrow-key selection into `filtered`

  const refresh = useCallback(async () => {
    const is = await invoke<ClipItem[]>("list_items", { limit: 100 });
    setItems(is);
  }, []);

  useEffect(() => {
    refresh();
    const unlistens: UnlistenFn[] = [];
    listen("clipboard-changed", refresh).then((u) => unlistens.push(u));
    listen("show-tray", refresh).then((u) => unlistens.push(u));
    getCurrentWindow()
      .onFocusChanged(({ payload: focused }) => {
        if (!focused) getCurrentWindow().hide();
      })
      .then((u) => unlistens.push(u));
    return () => unlistens.forEach((u) => u());
  }, [refresh]);

  // keep the arrow-selected row visible in the scroll list
  useEffect(() => {
    document
      .querySelector<HTMLElement>(".po-row.active")
      ?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  const copyBack = async (it: ClipItem) => {
    await getCurrentWindow().hide();
    await invoke("paste_item", { id: it.id });
  };

  const filtered = query
    ? items.filter((x) => matchQuery(x.content, x.preview, query))
    : items; // full scrollable list — no 12-row cap


  return (
    <div className="popover">
      <div className="po-search">
        <input
          autoFocus
          placeholder={t("search.tray")}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSel(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              setSel((i) =>
                e.key === "ArrowDown"
                  ? Math.min(i + 1, Math.max(0, filtered.length - 1))
                  : Math.max(0, i - 1),
              );
            } else if (e.key === "Enter") {
              const it = filtered[sel] ?? filtered[0];
              if (it) copyBack(it);
            } else if (e.key === "Escape") {
              getCurrentWindow().hide();
            }
          }}
        />
      </div>

      <div className="po-scroll">
        <div className="po-section">
          <div className="po-title">
            <span>
              {query ? t("tray.results") : t("tray.recent")} · {filtered.length}
            </span>
            <button
              className="po-link"
              onClick={async () => {
                await invoke("show_drawer");
                await getCurrentWindow().hide();
              }}
            >
              {t("tray.viewAll")}
            </button>
          </div>
          {filtered.length === 0 ? (
            <div className="po-empty">{query ? t("tray.noMatch") : t("tray.none")}</div>
          ) : (
            <div className="po-list">
              {filtered.map((it, idx) => (
                <Row
                  key={it.id}
                  data-idx={idx}
                  item={it}
                  active={idx === sel}
                  query={query}
                  onClick={() => copyBack(it)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="po-foot">
        <span className="po-foot-hint">
          <span className="kbd">{MOD}</span><span className="kbd">⇧</span><span className="kbd">V</span> {t("tray.full")}
        </span>
        <button className="po-foot-btn" onClick={() => invoke("quit_app")}>
          {t("tray.quit")}
        </button>
      </div>
    </div>
  );
}

function Row({
  item,
  active,
  query,
  "data-idx": idx,
  onClick,
}: {
  item: ClipItem;
  active: boolean;
  query: string;
  "data-idx"?: number;
  onClick: () => void;
}) {
  return (
    <button
      className={"po-row" + (active ? " active" : "")}
      data-idx={idx}
      onClick={onClick}
    >
      <span className={"po-kind kind-" + item.kind}>{kindLabel(item.kind)}</span>
      <span className="po-text"><HighlightText text={trimOne(item.preview || item.content)} query={query} /></span>
    </button>
  );
}

function trimOne(s: string): string {
  const oneline = s.replace(/\s+/g, " ").trim();
  return oneline.length > 60 ? oneline.slice(0, 60) + "…" : oneline;
}
