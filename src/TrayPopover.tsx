import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { writeText } from "@tauri-apps/plugin-clipboard-manager";
import type { ClipItem } from "./types";
import { KIND_LABEL } from "./types";

const RECENT_COUNT = 12;

export default function TrayPopover() {
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
    if (it.kind === "image") {
      await invoke("show_drawer");
      await getCurrentWindow().hide();
      return;
    }
    await writeText(it.content);
    await invoke("touch_item", { id: it.id });
    await getCurrentWindow().hide();
    // Auto-paste into the previously-focused app.
    await invoke("paste_back");
  };

  const filtered = (
    query
      ? items.filter(
          (x) =>
            x.preview.toLowerCase().includes(query.toLowerCase()) ||
            x.content.toLowerCase().includes(query.toLowerCase()),
        )
      : items
  ).slice(0, RECENT_COUNT);

  const pinned = filtered.filter((x) => x.pinned);
  const recent = filtered.filter((x) => !x.pinned);

  return (
    <div className="popover">
      <div className="po-search">
        <input
          autoFocus
          placeholder="搜索 …"
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
            <div className="po-title">📌 置顶</div>
            <div className="po-list">
              {pinned.map((it) => (
                <Row key={it.id} item={it} onClick={() => copyBack(it)} />
              ))}
            </div>
          </div>
        )}

        <div className="po-section">
          <div className="po-title">
            <span>{query ? "搜索结果" : "最近"}</span>
            <button
              className="po-link"
              onClick={async () => {
                await invoke("show_drawer");
                await getCurrentWindow().hide();
              }}
            >
              查看全部 →
            </button>
          </div>
          {recent.length === 0 ? (
            <div className="po-empty">{query ? "没找到匹配项" : "暂无内容"}</div>
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
          <span className="kbd">⌘⇧V</span> 唤起完整面板
        </span>
        <button className="po-foot-btn" onClick={() => invoke("quit_app")}>
          退出
        </button>
      </div>
    </div>
  );
}

function Row({ item, onClick }: { item: ClipItem; onClick: () => void }) {
  return (
    <button className="po-row" onClick={onClick}>
      <span className={"po-kind kind-" + item.kind}>{KIND_LABEL[item.kind]}</span>
      <span className="po-text">{trimOne(item.preview || item.content)}</span>
    </button>
  );
}

function trimOne(s: string): string {
  const oneline = s.replace(/\s+/g, " ").trim();
  return oneline.length > 60 ? oneline.slice(0, 60) + "…" : oneline;
}
