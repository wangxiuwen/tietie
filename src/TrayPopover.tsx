import { useCallback, useEffect, useRef, useState } from "react";
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
  // search input handle: the × clear button (direction 92) returns focus here
  const poSearchRef = useRef<HTMLInputElement>(null);
  // pinned-section expansion (direction 103): collapsed again per session
  const [pinExpanded, setPinExpanded] = useState(false);
  // progressive list (direction 77): start at 30 rows; pressing ↓ on the
  // last visible row appends another page so long histories stay light.
  const PAGE = 30;
  const [pageCount, setPageCount] = useState(1);
  // pinned rows above this count collapse behind an expand link (direction 103)
  const PIN_MAX = 5;

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

  const matched = query
    ? items.filter((x) => matchQuery(x.content, x.preview + " " + (x.note ?? ""), query))
    : items; // full history, no cap
  const filtered = matched.slice(0, pageCount * PAGE);
  // pinned section collapse (direction 103): without a query the pinned rows
  // sit in their own section capped at PIN_MAX until expanded; `shown` is the
  // array actually rendered, so keyboard selection never lands on hidden rows
  const pinnedAll = query ? [] : filtered.filter((x) => x.pinned);
  const collapsePinned = pinnedAll.length > PIN_MAX && !pinExpanded;
  const shown = collapsePinned
    ? [...pinnedAll.slice(0, PIN_MAX), ...filtered.filter((x) => !x.pinned)]
    : filtered;
  const cut = shown.findIndex((x) => !x.pinned); // pinned render first
  const pinnedShown = cut === -1 ? shown : shown.slice(0, cut);
  const restShown = cut === -1 ? [] : shown.slice(cut);
  // reset paging when the query changes or the panel refetches
  useEffect(() => {
    setPageCount(1);
  }, [query]);


  return (
    <div className="popover">
      <div className="po-search">
        <div className="po-search-box">
        <input
          ref={poSearchRef}
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
              if (e.key === "ArrowDown" && sel === shown.length - 1 && sel < matched.length - 1) {
                // hit the bottom of the visible page → auto-load more
                setPageCount((p) => p + 1);
                setSel((i) => i + 1);
                return;
              }
              setSel((i) =>
                e.key === "ArrowDown"
                  ? Math.min(i + 1, Math.max(0, shown.length - 1))
                  : Math.max(0, i - 1),
              );
            } else if ((e.metaKey || e.ctrlKey) && /^[0-9]$/.test(e.key)) {
              // ⌘N quick-copies the Nth visible row (direction 124); plain
              // digits keep typing into the search box
              e.preventDefault();
              const i = e.key === "0" ? 9 : Number(e.key) - 1;
              const it = shown[i];
              if (it) copyBack(it);
            } else if (e.key === "Enter") {
              const it = shown[sel] ?? shown[0];
              if (it) copyBack(it);
            } else if (e.key === "Escape") {
              getCurrentWindow().hide();
            }
          }}
        />
        {query && (
          <button
            className="po-clear"
            aria-label={t("tray.clearSearch")}
            title={t("tray.clearSearch")}
            onClick={() => {
              setQuery("");
              setSel(0);
              poSearchRef.current?.focus();
            }}
          >
            ×
          </button>
        )}
        </div>
      </div>

      <div className="po-scroll">
        {query ? (
          <div className="po-section">
            <div className="po-title">
              <span>{t("tray.results")} · {filtered.length}</span>
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
              <div className="po-empty">{t("tray.noMatch")}</div>
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
        ) : (
          <>
            {pinnedAll.length > 0 && (
              <div className="po-section">
                <div className="po-title">
                  <span>{t("tray.pinned")} · {pinnedAll.length}</span>
                  {collapsePinned && (
                    <button className="po-link" onClick={() => setPinExpanded(true)}>
                      {t("tray.expand")} +{pinnedAll.length - PIN_MAX}
                    </button>
                  )}
                </div>
                <div className="po-list">
                  {pinnedShown.map((it, idx) => (
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
              </div>
            )}
            <div className="po-section">
              <div className="po-title">
                <span>{t("tray.recent")} · {restShown.length}</span>
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
              {shown.length === 0 ? (
                <div className="po-empty">{t("tray.none")}</div>
              ) : (
                <div className="po-list">
                  {restShown.map((it, idx) => (
                    <Row
                      key={it.id}
                      data-idx={idx + pinnedShown.length}
                      item={it}
                      active={idx + pinnedShown.length === sel}
                      query={query}
                      onClick={() => copyBack(it)}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <div className="po-foot">
        <button
          className="po-foot-hint po-foot-open"
          title={t("tray.full")}
          onClick={async () => {
            await getCurrentWindow().hide();
            await invoke("show_drawer");
          }}
        >
          <span className="kbd">{MOD}</span><span className="kbd">⇧</span><span className="kbd">V</span> {t("tray.full")}
        </button>
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
      // annotated items surface their note on hover (direction 115)
      title={item.note ?? undefined}
      onClick={onClick}
    >
      <span className={"po-kind kind-" + item.kind}>{kindLabel(item.kind)}</span>
      {item.kind === "image" && item.preview && (
        // the stored preview IS the b64 thumbnail — show it instead of
        // leaking base64 text into the row (direction 61)
        <img
          className="po-thumb"
          alt=""
          decoding="async"
          src={"data:image/png;base64," + item.preview}
        />
      )}
      <span className="po-text"><HighlightText text={trimOne(rowText(item))} query={query} /></span>
      {/* first 10 visible rows show their ⌘N quick-copy hint (direction 124) */}
      {idx != null && idx < 10 && (
        <span className="kbd">{MOD}{idx === 9 ? 0 : idx + 1}</span>
      )}
    </button>
  );
}

/** Image rows read the dimensions (content) — never base64 text. */
function rowText(item: ClipItem): string {
  return item.kind === "image" ? item.content : (item.preview || item.content);
}

function trimOne(s: string): string {
  const oneline = s.replace(/\s+/g, " ").trim();
  return oneline.length > 60 ? oneline.slice(0, 60) + "…" : oneline;
}
