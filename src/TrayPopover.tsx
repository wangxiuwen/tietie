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
import { ContextMenu } from "./ContextMenu";


export default function TrayPopover() {
  useLang();
  useEffect(() => onFontScaleChange(() => setItems((x) => [...x])), []);
  const [items, setItems] = useState<ClipItem[]>([]);
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(0); // arrow-key selection into `filtered`
  // search input handle: the × clear button (direction 92) returns focus here
  const poSearchRef = useRef<HTMLInputElement>(null);
  // cursor walking the drawer-shared search history on ↑ (direction 171)
  const [trayHistIdx, setTrayHistIdx] = useState(-1);
  // pinned-section expansion (direction 103): collapsed again per session
  const [pinExpanded, setPinExpanded] = useState(false);
  // row context menu (direction 140)
  const [rowMenu, setRowMenu] = useState<{ x: number; y: number; itemId: number } | null>(null);
  // inline note editor for a row (direction 176): opened from the context
  // menu's 备注 item, lives under the search box
  const [noteEdit, setNoteEdit] = useState<{ id: number; draft: string } | null>(null);
  // progressive list (direction 77): start at 30 rows; pressing ↓ on the
  // last visible row appends another page so long histories stay light.
  const PAGE = 30;
  const [pageCount, setPageCount] = useState(1);
  // pinned rows above this count collapse behind an expand link (direction 103)
  const PIN_MAX = 5;
  // scroll-to-top button (direction 146): appears once the list is scrolled
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);

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
    ? items.filter((x) => matchQuery(x.content, x.preview + " " + (x.note ?? ""), query, x.kind))
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
  // ⌘N badges cycle with the auto-loaded page (direction 181): the numbered
  // window sits at the newest page's first ten rows (0 before any paging)
  const pageBase = (pageCount - 1) * PAGE;


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
            setTrayHistIdx(-1); // typing leaves history recall (direction 171)
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              // ↑ on an empty query recalls the drawer's search history
              // (direction 171, mirrors 126); repeated ↑ walks older — typing
              // resets. Otherwise the arrows keep selecting rows as before.
              if (e.key === "ArrowUp" && (!query || trayHistIdx >= 0)) {
                const hist = JSON.parse(localStorage.getItem("tietie.searchHist") || "[]") as string[];
                if (hist.length) {
                  e.preventDefault();
                  const n = Math.min(trayHistIdx + 1, hist.length - 1);
                  setTrayHistIdx(n);
                  setQuery(hist[hist.length - 1 - n]);
                  return;
                }
              }
              e.preventDefault();
              if (e.key === "ArrowDown") setTrayHistIdx(-1); // leaves recall
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
              // badges cycle with the auto-loaded page (direction 181):
              // ⌘1..⌘0 target the newest page's first ten rows
              const it = shown[(pageCount - 1) * PAGE + i];
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

      {noteEdit && (
        <div className="po-note-edit">
          <input
            autoFocus
            maxLength={200}
            placeholder={t("tray.notePlaceholder")}
            value={noteEdit.draft}
            onChange={(e) => setNoteEdit((n) => (n ? { ...n, draft: e.target.value } : n))}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                setNoteEdit(null);
              } else if (e.key === "Enter") {
                e.preventDefault();
                const { id, draft } = noteEdit;
                setNoteEdit(null);
                invoke("set_item_note", { id, note: draft }).then(refresh).catch(() => {});
              }
            }}
          />
        </div>
      )}

      <div
        className="po-scroll"
        ref={scrollRef}
        onScroll={(e) => setScrolled((e.target as HTMLDivElement).scrollTop > 80)}
      >
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
                    onContext={(x, y) => setRowMenu({ x, y, itemId: it.id })}
                    badgeBase={pageBase}
                    onMiddle={() => {
                      invoke("toggle_pin", { id: it.id }).then(refresh).catch(() => {});
                    }}
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
                      onContext={(x, y) => setRowMenu({ x, y, itemId: it.id })}
                      badgeBase={pageBase}
                    onMiddle={() => {
                      invoke("toggle_pin", { id: it.id }).then(refresh).catch(() => {});
                    }}
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
                      onContext={(x, y) => setRowMenu({ x, y, itemId: it.id })}
                      badgeBase={pageBase}
                    onMiddle={() => {
                      invoke("toggle_pin", { id: it.id }).then(refresh).catch(() => {});
                    }}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {rowMenu && (
        <ContextMenu
          x={rowMenu.x}
          y={rowMenu.y}
          items={[
            { label: t("tray.mCopy"), onClick: () => {
              const it = shown.find((x) => x.id === rowMenu.itemId);
              if (it) copyBack(it);
            } },
            { label: items.find((x) => x.id === rowMenu.itemId)?.pinned
                ? t("tray.mUnpin") : t("tray.mPin"),
              onClick: () => { invoke("toggle_pin", { id: rowMenu.itemId }).then(refresh).catch(() => {}); } },
            // quick note entry (direction 176): swaps the menu for the
            // inline editor under the search box
            { label: t("tray.mNote"),
              onClick: () => {
                setNoteEdit({
                  id: rowMenu.itemId,
                  draft: items.find((x) => x.id === rowMenu.itemId)?.note ?? "",
                });
              } },
            { label: t("tray.mDel"), danger: true, separatorBefore: true,
              onClick: () => { invoke("delete_item", { id: rowMenu.itemId }).then(refresh).catch(() => {}); } },
          ]}
          onClose={() => setRowMenu(null)}
        />
      )}

      {scrolled && (
        <button
          className="po-top"
          aria-label={t("tray.toTop")}
          title={t("tray.toTop")}
          onClick={() => {
            scrollRef.current?.scrollTo({ top: 0 });
            setSel(0);
          }}
        >
          ↑
        </button>
      )}

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
  onContext,
  onMiddle,
  badgeBase = 0,
}: {
  item: ClipItem;
  active: boolean;
  query: string;
  "data-idx"?: number;
  onClick: () => void;
  onContext: (x: number, y: number) => void;
  /** middle-click toggles pin (direction 155) */
  onMiddle?: () => void;
  /** first row index carrying the ⌘N badges (direction 181) */
  badgeBase?: number;
}) {
  return (
    <button
      className={"po-row" + (active ? " active" : "")}
      data-idx={idx}
      // hover hint: note (direction 115) + entry byte size (direction 168)
      title={[item.note, fmtBytes(item.byte_size)].filter(Boolean).join(" · ") || undefined}
      onMouseDown={(e) => {
        if (e.button === 1) {
          // preventDefault keeps the WebView out of autoscroll mode
          e.preventDefault();
          onMiddle?.();
        }
      }}
      onClick={onClick}
      onContextMenu={(e) => {
        // row context menu (direction 140): copy / pin / delete
        e.preventDefault();
        e.stopPropagation();
        onContext(e.clientX, e.clientY);
      }}
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
      {/* ⌘N quick-copy hint (direction 124); the numbered window follows the
          auto-loaded page so the keys stay useful after paging (181) */}
      {idx != null && idx - badgeBase >= 0 && idx - badgeBase < 10 && (
        <span className="kbd">{MOD}{idx - badgeBase === 9 ? 0 : idx - badgeBase + 1}</span>
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

/** "1.2 KB" / "3.4 MB" / "567 B" — hover size hint (direction 168) */
function fmtBytes(n: number): string {
  if (!n || n <= 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
