import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { Memo } from "./types";
import { kindLabel } from "./types";
import { t, useLang } from "./i18n";

// ─── take-off drag: one shared tracker, listeners live in Clothesline ───
// This window is never focused (focus:false) and Chromium does not honor
// DOM pointer capture on inactive windows, so tracking runs on window-level
// listeners (verified against WebView2). One mouse ⇒ one active drag — a
// single module record shared by every hanging card, with ONE listener set
// in Clothesline instead of one per card.
const lineDrag = {
  current: null as null | { memoId: number; startY: number; moved: boolean; off: boolean },
};

/**
 * 晾衣架 — a rope across the top of the screen with memo cards hanging
 * from clothespins.
 *
 * Interactions:
 * - 挂: drag a drawer card up to the top (drawer side drives this)
 * - 看: click a hanging card → full-content view with 复制/摘下
 * - 摘: drag a card down out of the rope zone (ghost follows) or ✕
 */
export default function Clothesline() {
  useLang(); // re-render on language switch
  const [memos, setMemos] = useState<Memo[]>([]);
  const [previewing, setPreviewing] = useState(false);
  const [viewing, setViewing] = useState<Memo | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  // take-off drag UI (ghost + lifted/dropping card), null when idle
  const [dragUI, setDragUI] = useState<{ id: number; x: number; y: number; off: boolean } | null>(
    null,
  );
  const memosRef = useRef<Memo[]>([]);
  memosRef.current = memos;

  const refresh = useCallback(async () => {
    const ms = await invoke<Memo[]>("list_memos");
    setMemos(ms);
    setPreviewing(false);
    // keep the open detail view in sync (pin flag may have flipped)
    setViewing((v) => (v ? (ms.find((m) => m.id === v.id) ?? v) : v));
  }, []);

  useEffect(() => {
    refresh();
    const unlistens: UnlistenFn[] = [];
    listen("memos-changed", refresh).then((u) => unlistens.push(u));
    listen<number | null>("hang-preview", (e) => setPreviewing(e.payload != null)).then((u) =>
      unlistens.push(u),
    );
    return () => unlistens.forEach((u) => u());
  }, [refresh]);

  // one window-level tracker for every hanging card (see lineDrag above)
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const st = lineDrag.current;
      if (!st || (e.buttons & 1) === 0) return;
      const dy = e.screenY - st.startY;
      if (!st.moved) {
        if (Math.abs(dy) < 14) return;
        st.moved = true;
        // grab the OS cursor so events keep flowing outside the 230px window
        getCurrentWindow().setCursorGrab(true).catch(() => {});
      }
      st.off = dy > 70;
      setDragUI({
        id: st.memoId,
        x: e.screenX - window.screenX,
        y: e.screenY - window.screenY,
        off: st.off,
      });
    };
    const onFinish = () => {
      const st = lineDrag.current;
      if (!st) return;
      lineDrag.current = null;
      setDragUI(null);
      getCurrentWindow().setCursorGrab(false).catch(() => {});
      if (st.moved) {
        // dragged — take it off when pulled past the rope zone, never a click
        if (st.off) {
          invoke("remove_memo", { id: st.memoId }).catch((err) =>
            console.warn("[tietie] remove_memo failed:", err),
          );
        }
        return;
      }
      const m = memosRef.current.find((x) => x.id === st.memoId);
      if (m) setViewing(m);
    };
    window.addEventListener("pointermove", onMove, true);
    window.addEventListener("pointerup", onFinish, true);
    window.addEventListener("pointercancel", onFinish, true);
    return () => {
      window.removeEventListener("pointermove", onMove, true);
      window.removeEventListener("pointerup", onFinish, true);
      window.removeEventListener("pointercancel", onFinish, true);
    };
  }, []);

  const copy = useCallback(
    async (m: Memo) => {
      await invoke("copy_memo", { id: m.id });
      setCopiedId(m.id);
      setTimeout(() => setCopiedId((cur) => (cur === m.id ? null : cur)), 1200);
    },
    [],
  );

  const remove = useCallback(async (id: number) => {
    setViewing((v) => (v?.id === id ? null : v));
    await invoke("remove_memo", { id });
  }, []);

  const collapse = useCallback(async () => {
    await invoke("toggle_clothesline_cmd");
  }, []);

  // native window.prompt dialogs never open inside WebView2/WKWebView —
  // the composer is an inline card under the rope instead
  const [composing, setComposing] = useState(false);

  const saveMemo = useCallback(async (id: number, content: string) => {
    await invoke("update_memo", { id, content }).catch((e) =>
      console.warn("update_memo failed:", e),
    );
    setViewing(null);
  }, []);

  useEffect(() => {
    if (!viewing) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setViewing(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [viewing]);

  return (
    <div className={"line" + (previewing ? " line-hot" : "")}>
      <Rope hot={previewing || !!viewing || composing} />
      {viewing ? (
        <MemoDetail
          memo={viewing}
          copied={copiedId === viewing.id}
          onCopy={() => copy(viewing)}
          onClose={() => setViewing(null)}
          onRemove={() => remove(viewing.id)}
          onSave={(content) => saveMemo(viewing.id, content)}
          onTogglePin={() => invoke("toggle_memo_pin", { id: viewing.id }).catch(() => {})}
        />
      ) : (
        <>
          <div className="line-cards">
            {memos.length === 0 && !previewing ? (
              <div className="line-empty">
                {t("line.empty")}
              </div>
            ) : (
              memos.map((m, i) => (
                <HangingCard
                  key={m.id}
                  memo={m}
                  swing={i % 2 === 1}
                  draggedOff={dragUI?.id === m.id && dragUI.off}
                  lifted={dragUI?.id === m.id}
                />
              ))
            )}
            {previewing && <div className="line-ghost">{t("line.hang")}</div>}
            {composing && (
              <NoteComposer
                onCancel={() => setComposing(false)}
                onCommit={async (content) => {
                  setComposing(false);
                  await invoke("add_memo_direct", { content }).catch((e) =>
                    console.warn("add_memo_direct failed:", e),
                  );
                }}
              />
            )}
          </div>
          <button
            className="line-new"
            title={t("line.newNote")}
            onClick={() => setComposing((c) => !c)}
          >
            {t("line.newNote")}
          </button>
          <button
            className="line-collapse"
            title={t("line.collapse")}
            onClick={collapse}
          >
            {t("line.collapse")}
          </button>
        </>
      )}
      {dragUI &&
        createPortal(
          <div className="drag-ghost" style={{ left: dragUI.x, top: dragUI.y }}>
            {dragUI.off ? t("line.takeoffNow") : t("line.takeoff")}
          </div>,
          document.body,
        )}
    </div>
  );
}

/** Inline sticky-note composer pinned under the rope. */
function NoteComposer({
  onCommit,
  onCancel,
}: {
  onCommit: (content: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState("");
  const submit = () => {
    if (text.trim()) onCommit(text);
    else onCancel();
  };
  return (
    <div className="line-card composer">
      <div className="line-pin" style={{ background: "#007aff" }} />
      <span className="line-badge">{t("line.composing")}</span>
      <textarea
        className="line-compose"
        autoFocus
        placeholder={t("line.composePlaceholder")}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            submit();
          }
        }}
      />
      <div className="line-compose-foot">
        <button className="btn ghost" onClick={onCancel}>
          {t("line.composeCancel")}
        </button>
        <button className="btn primary" onClick={submit} disabled={!text.trim()}>
          {t("line.commit")}
        </button>
      </div>
    </div>
  );
}

function Rope({ hot }: { hot: boolean }) {
  return (
    <svg className="line-rope" preserveAspectRatio="none" viewBox="0 0 1000 26">
      <path
        d="M0,2 C 250,26 750,26 1000,2"
        fill="none"
        className={"line-rope-path" + (hot ? " hot" : "")}
      />
      <circle cx="0" cy="2" r="5" className="line-rope-anchor" />
      <circle cx="1000" cy="2" r="5" className="line-rope-anchor" />
    </svg>
  );
}

/**
 * A hanging memo card. Click opens the detail view; dragging down past the
 * rope zone takes the memo off the line. Tracking (window listeners + ghost)
 * lives in Clothesline — see lineDrag; the card only registers the start.
 */
function HangingCard({
  memo,
  swing,
  draggedOff,
  lifted,
}: {
  memo: Memo;
  swing: boolean;
  draggedOff: boolean;
  lifted: boolean;
}) {
  return (
    <div
      className={
        "line-card" +
        (swing ? " swing" : "") +
        (draggedOff ? " dropping" : "") +
        (lifted ? " lifted" : "")
      }
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        lineDrag.current = { memoId: memo.id, startY: e.screenY, moved: false, off: false };
      }}
      title={t("line.view")}
    >
      <div
        className="line-pin"
        style={{ background: memo.pinned ? "#ff9500" : memo.color }}
        title={memo.pinned ? t("line.pinned") : undefined}
      />
      <span className="line-badge">
        {kindLabel(memo.kind)}
      </span>
      <CardBody memo={memo} />
      <button
        className="line-x"
        onClick={(e) => {
          e.stopPropagation();
          invoke("remove_memo", { id: memo.id }).catch(() => {});
        }}
        title={t("line.takeOff")}
      >
        ✕
      </button>
    </div>
  );
}

function MemoDetail({
  memo,
  copied,
  onCopy,
  onClose,
  onRemove,
  onSave,
  onTogglePin,
}: {
  memo: Memo;
  copied: boolean;
  onCopy: () => void;
  onClose: () => void;
  onRemove: () => void;
  onSave: (content: string) => void;
  onTogglePin: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(memo.content);

  const canEdit = memo.kind !== "image"; // image memos carry no editable text

  return (
    <div className="line-detail" onClick={(e) => e.stopPropagation()}>
      <div className="line-detail-head">
        <span className="line-badge" style={{ position: "static" }}>
          {kindLabel(memo.kind)}
        </span>
        <span className="line-detail-time">{relTime(memo.created_at)}</span>
        <div className="line-detail-actions">
          {canEdit && !editing && (
            <button className="btn ghost" onClick={() => setEditing(true)}>
              {t("line.edit")}
            </button>
          )}
          {editing ? (
            <>
              <button className="btn primary" onClick={() => onSave(draft)}>
                {t("line.save")}
              </button>
              <button className="btn ghost" onClick={() => setEditing(false)}>
                {t("line.cancelEdit")}
              </button>
            </>
          ) : (
            <>
              <button className="btn ghost" onClick={onTogglePin}>
                {memo.pinned ? t("line.unpin") : t("line.pin")}
              </button>
              <button className="btn primary" onClick={onCopy}>
                {copied ? t("line.copied") : t("line.copy")}
              </button>
              <button className="btn ghost" onClick={onRemove}>
                {t("line.takeOff")}
              </button>
            </>
          )}
          <button className="btn ghost" onClick={onClose}>
            {t("line.close")}
          </button>
        </div>
      </div>
      {editing ? (
        <div className="line-detail-body">
          <textarea
            className="line-detail-edit"
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                setEditing(false);
                setDraft(memo.content);
              } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                e.preventDefault();
                onSave(draft);
              }
            }}
          />
        </div>
      ) : (
        <DetailBody memo={memo} />
      )}
    </div>
  );
}

function DetailBody({ memo }: { memo: Memo }) {
  if (memo.kind === "image") {
    return <ImageDetail memo={memo} />;
  }
  if (memo.kind === "color") {
    return (
      <div className="line-detail-body line-color">
        <span className="line-swatch big" style={{ background: memo.content }} />
        <code>{memo.content}</code>
      </div>
    );
  }
  return (
    <div className="line-detail-body">
      <pre className="line-detail-text">{memo.content}</pre>
    </div>
  );
}

/**
 * Image memo detail: prefer the original clip blob (via source_item_id,
 * same path copy_memo uses) rendered as a blob URL; fall back to the
 * stored thumbnail when the source item was trimmed from history.
 */
function ImageDetail({ memo }: { memo: Memo }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let revoke: string | null = null;
    let alive = true;
    (async () => {
      if (memo.source_item_id != null) {
        try {
          const bytes = await invoke<number[]>("get_item_image", { id: memo.source_item_id });
          if (!alive) return;
          const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
          revoke = URL.createObjectURL(blob);
          setUrl(revoke);
          return;
        } catch {
          // source trimmed — fall through to thumbnail
        }
      }
      if (alive && memo.preview) {
        setUrl(`data:image/png;base64,${memo.preview}`);
      }
    })();
    return () => {
      alive = false;
      if (revoke && revoke.startsWith("blob:")) URL.revokeObjectURL(revoke);
    };
  }, [memo.source_item_id, memo.preview]);

  return (
    <div className="line-detail-body">
      {url ? (
        <img className="line-detail-img" src={url} alt={memo.content} />
      ) : (
        <div className="zoom-loading">{t("line.loading")}</div>
      )}
    </div>
  );
}

function CardBody({ memo }: { memo: Memo }) {
  if (memo.kind === "image" && memo.preview) {
    return (
      <div
        className="line-img"
        style={{ backgroundImage: `url(data:image/png;base64,${memo.preview})` }}
      />
    );
  }
  if (memo.kind === "color") {
    return (
      <div className="line-color">
        <span className="line-swatch" style={{ background: memo.content }} />
        <code>{memo.content}</code>
      </div>
    );
  }
  const text = memo.content.replace(/\s+/g, " ").trim();
  return <div className="line-text">{text.length > 90 ? text.slice(0, 90) + "…" : text}</div>;
}

function relTime(unixSec: number): string {
  const diff = Math.floor(Date.now() / 1000 - unixSec);
  if (diff < 60) return t("line.justNow");
  if (diff < 3600) return `${Math.floor(diff / 60)}${t("line.minAgo")}`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}${t("line.hourAgo")}`;
  return new Date(unixSec * 1000).toLocaleDateString();
}
