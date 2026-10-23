import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { ClipItem } from "./types";
import { kindLabel } from "./types";
import { MOD } from "./platform";
import { matchQuery } from "./search";
import { t, useLang } from "./i18n";

const RECENT_COUNT = 12;

export default function TrayPopover() {
  useLang();
  const [items, setItems] = useState<ClipItem[]>([]);
  const [query, setQuery] = useState("");

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

  const copyBack = async (it: ClipItem) => {
    await getCurrentWindow().hide();
    await invoke("paste_item", { id: it.id });
  };

  const filtered = (
    query ? items.filter((x) => matchQuery(x.content, x.preview, query)) : items
  ).slice(0, RECENT_COUNT);

  const pinned = filtered.filter((x) => x.pinned);
  const recent = filtered.filter((x) => !x.pinned);

  return (
    <div className="popover">
      <div className="po-search">
        <input
          autoFocus
          placeholder={t("search.tray")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const first = filtered[0];
              if (first) copyBack(first);
            } else if (e.key === "Escape") {
              getCurrentWindow().hide();
            }
          }}
        />
      </div>

      <div className="po-scroll">
        {pinned.length > 0 && (
          <div className="po-section">
            <div className="po-title">{t("tray.pinned")}</div>
            <div className="po-list">
              {pinned.map((it) => (
                <Row key={it.id} item={it} onClick={() => copyBack(it)} />
              ))}
            </div>
          </div>
        )}

        <div className="po-section">
          <div className="po-title">
            <span>{query ? t("tray.results") : t("tray.recent")}</span>
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
          {recent.length === 0 ? (
            <div className="po-empty">{query ? t("tray.noMatch") : t("tray.none")}</div>
          ) : (
            <div className="po-list">
              {recent.map((it) => (
                <Row key={it.id} item={it} onClick={() => copyBack(it)} />
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

function Row({ item, onClick }: { item: ClipItem; onClick: () => void }) {
  return (
    <button className="po-row" onClick={onClick}>
      <span className={"po-kind kind-" + item.kind}>{kindLabel(item.kind)}</span>
      <span className="po-text">{trimOne(item.preview || item.content)}</span>
    </button>
  );
}

function trimOne(s: string): string {
  const oneline = s.replace(/\s+/g, " ").trim();
  return oneline.length > 60 ? oneline.slice(0, 60) + "…" : oneline;
}
