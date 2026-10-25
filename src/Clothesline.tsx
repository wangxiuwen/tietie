import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { Memo } from "./types";
import { kindLabel } from "./types";
import { ContextMenu, type MenuItem } from "./ContextMenu";
import { t, useLang } from "./i18n";
import { onFontScaleChange } from "./fontScale";
import { RopeSim } from "./ropePhysics";

// ─── take-off drag: one shared tracker, listeners live in Clothesline ───
// This window is never focused (focus:false) and Chromium does not honor
// DOM pointer capture on inactive windows, so tracking runs on window-level
// listeners (verified against WebView2). One mouse ⇒ one active drag — a
// single module record shared by every hanging card, with ONE listener set
// in Clothesline instead of one per card.
const lineDrag = {
  current: null as null | {
    memoId: number;
    startX: number;
    startY: number;
    moved: boolean;
    off: boolean;
    horizontal: boolean;
  },
};

/** Preset clothespin colors for the detail-view palette. */
const MEMO_COLORS = [
  "#007aff",
  "#34c759",
  "#ff9500",
  "#ff2d55",
  "#af52de",
  "#5856d6",
  "#8e8e93",
  "#ffcc00",
];

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
  useEffect(() => onFontScaleChange(() => setMemos((m) => [...m])), []);
  const [memos, setMemos] = useState<Memo[]>([]);
  // reminder tick (direction 53): re-evaluate due-flash every few seconds
  const [nowSec, setNowSec] = useState(() => Math.floor(Date.now() / 1000));
  useEffect(() => {
    const iv = setInterval(() => setNowSec(Math.floor(Date.now() / 1000)), 3000);
    return () => clearInterval(iv);
  }, []);
  // due → flash for the first minute, then hold a steady reminder marker
  const dueSet = useMemo(() => {
    const s = new Set<number>();
    for (const m of memos) {
      if (m.remind_at != null && nowSec >= m.remind_at) s.add(m.id);
    }
    return s;
  }, [memos, nowSec]);
  const flashSet = useMemo(() => {
    const s = new Set<number>();
    for (const m of memos) {
      if (
        m.remind_at != null &&
        nowSec >= m.remind_at &&
        nowSec < m.remind_at + 60
      )
        s.add(m.id);
    }
    return s;
  }, [memos, nowSec]);
  const [previewing, setPreviewing] = useState(false);
  const [viewing, setViewing] = useState<Memo | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  // take-off drag UI (ghost + lifted/dropping card), null when idle
  const [dragUI, setDragUI] = useState<{
    id: number;
    x: number;
    y: number;
    off: boolean;
    horizontal?: boolean;
  } | null>(null);
  // right-click context menu on hanging cards
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; memoId: number } | null>(null);
  const memosRef = useRef<Memo[]>([]);
  memosRef.current = memos;
  // live drag pointer (viewport coords) for the rope physics loop
  const dragPosRef = useRef<{ id: number; x: number; y: number } | null>(null);

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
      const dx = e.screenX - st.startX;
      if (!st.moved) {
        if (Math.abs(dy) < 14 && Math.abs(dx) < 14) return;
        st.moved = true;
        // grab the OS cursor so events keep flowing outside the 230px window
        getCurrentWindow().setCursorGrab(true).catch(() => {});
      }
      // horizontal-dominant drag = reorder; vertical-down = take off
      st.horizontal = Math.abs(dx) > Math.abs(dy);
      st.off = !st.horizontal && dy > 70;
      const vx = e.screenX - window.screenX;
      const vy = e.screenY - window.screenY;
      dragPosRef.current = { id: st.memoId, x: vx, y: vy };
      setDragUI({ id: st.memoId, x: vx, y: vy, off: st.off, horizontal: st.horizontal });
    };
    const onFinish = () => {
      const st = lineDrag.current;
      if (!st) return;
      lineDrag.current = null;
      dragPosRef.current = null;
      setDragUI(null);
      getCurrentWindow().setCursorGrab(false).catch(() => {});
      if (st.moved) {
        // horizontal drag = move this card to the slot nearest the pointer
        if (st.horizontal) {
          const cards = [
            ...document.querySelectorAll<HTMLElement>(".line-card[data-memo]"),
          ];
          const dropX = lastPointer.x;
          let target = cards.length - 1;
          for (let i = 0; i < cards.length; i++) {
            const r = cards[i].getBoundingClientRect();
            if (dropX < r.left + r.width / 2) {
              target = i;
              break;
            }
          }
          invoke("reorder_memo", { id: st.memoId, toIndex: target }).catch((err) =>
            console.warn("[tietie] reorder_memo failed:", err),
          );
          return;
        }
        // vertical drag — take it off when pulled past the rope zone
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
    const lastPointer = { x: 0, y: 0 };
    const onMoveTracked = (e: PointerEvent) => {
      lastPointer.x = e.clientX;
      lastPointer.y = e.clientY;
      onMove(e);
    };
    window.addEventListener("pointermove", onMoveTracked, true);
    window.addEventListener("pointerup", onFinish, true);
    window.addEventListener("pointercancel", onFinish, true);
    return () => {
      window.removeEventListener("pointermove", onMoveTracked, true);
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

  // ─── rope physics: verlet sim rendered via direct DOM writes ───
  const ropeSimRef = useRef<RopeSim | null>(null);
  const ropePathRef = useRef<SVGPathElement | null>(null);
  const lineWrapRef = useRef<HTMLDivElement | null>(null);
  const prevMemoCount = useRef(0);

  useEffect(() => {
    const wrap = lineWrapRef.current;
    if (!wrap) return;
    const W = wrap.clientWidth || 1920;
    const sim = new RopeSim(W, 30, 20);
    ropeSimRef.current = sim;

    let raf = 0;
    const loop = () => {
      const width = wrap.clientWidth || W;
      if (Math.abs(width - (sim.points[sim.n - 1].x)) > 2) sim.resize(width);

      // hanging weights: each card pulls the rope down at its pin position
      const cards = wrap.querySelectorAll<HTMLElement>(".line-card");
      const weights = new Map<number, number>();
      const cardY: { el: HTMLElement; dy: number }[] = [];
      cards.forEach((el) => {
        const cx = el.offsetLeft + el.offsetWidth / 2;
        const idx = sim.indexAt(cx, width);
        const isDragged = dragPosRef.current && el.dataset.memo === String(dragPosRef.current.id);
        if (isDragged) return; // its weight is replaced by the drag force
        weights.set(idx, (weights.get(idx) ?? 0) + 0.55);
        cardY.push({ el, dy: sim.yAt(idx) - 20 }); // rope sag under this card
      });

      // dragging a card stretches the rope toward the pointer
      let drag: { index: number; x: number; y: number } | undefined;
      if (dragPosRef.current) {
        const d = dragPosRef.current;
        drag = { index: sim.indexAt(d.x, width), x: d.x, y: Math.max(20, d.y - 40) };
      }

      sim.step(0.35, weights, drag);

      // paint rope + hang cards at their physical sag
      ropePathRef.current?.setAttribute("d", sim.path());
      for (const { el, dy } of cardY) {
        el.style.transform = `translateY(${dy.toFixed(1)}px)`;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  // a freshly hung card kicks the rope
  useEffect(() => {
    const sim = ropeSimRef.current;
    if (!sim || !lineWrapRef.current) return;
    if (memos.length > prevMemoCount.current && prevMemoCount.current >= 0) {
      const cards = lineWrapRef.current.querySelectorAll<HTMLElement>(".line-card");
      const last = cards[cards.length - 1];
      if (last) {
        const cx = last.offsetLeft + last.offsetWidth / 2;
        sim.impulse(sim.indexAt(cx, lineWrapRef.current.clientWidth), 16);
      }
    }
    prevMemoCount.current = memos.length;
  }, [memos.length]);

  const collapse = useCallback(async () => {
    await invoke("toggle_clothesline_cmd");
  }, []);

  // native window.prompt dialogs never open inside WebView2/WKWebView —
  // the composer is an inline card under the rope instead
  const [composing, setComposing] = useState(false);

  // open the detail view already in edit mode (context-menu 编辑)
  const [editOnOpen, setEditOnOpen] = useState(false);
  const openDetailEditing = useCallback((m: Memo) => {
    setEditOnOpen(true);
    setViewing(m);
  }, []);

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
    <div className={"line" + (previewing ? " line-hot" : "")} ref={lineWrapRef}>
      <Rope hot={previewing || !!viewing || composing} pathRef={ropePathRef} />
      {viewing ? (
        <MemoDetail
          memo={viewing}
          initialEditing={editOnOpen}
          copied={copiedId === viewing.id}
          onCopy={() => copy(viewing)}
          onClose={() => { setEditOnOpen(false); setViewing(null); }}
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
                  flash={flashSet.has(m.id)}
                  due={dueSet.has(m.id)}
                  onContext={(x, y) => setCtxMenu({ x, y, memoId: m.id })}
                  onEdit={() => openDetailEditing(m)}
                />
              ))
            )}
            {previewing && (
              <>
                <div className="line-insert-slot">{t("line.insertHere")}</div>
                <div className="line-ghost">{t("line.hang")}</div>
              </>
            )}
            {composing && (
              <NoteComposer
                onCancel={() => setComposing(false)}
                recentColors={recentPinColors(memos)}
                onCommit={async (content, remindIn, color) => {
                  setComposing(false);
                  const remindAt =
                    remindIn != null
                      ? Math.floor(Date.now() / 1000) + remindIn * 60
                      : null;
                  await invoke("add_memo_direct", { content, remindAt, color }).catch(
                    (e) => console.warn("add_memo_direct failed:", e),
                  );
                }}
              />
            )}
          </div>
          {memos.length > 15 && (
            <span className="line-cap" title={t("line.capHint")}>
              {t("line.cap")} {memos.length}
            </span>
          )}
          <button
            className="line-new"
            title={t("line.newNote")}
            onClick={() => setComposing((c) => !c)}
          >
            {t("line.newNote")}
          </button>
          <button
            className="line-new"
            title={t("line.exportNotes")}
            onClick={async () => {
              try {
                const path = await invoke<string>("export_memos");
                invoke("reveal_path", { path }).catch(() => {});
              } catch (e) {
                console.warn("export_memos:", e);
              }
            }}
          >
            {t("line.exportNotes")}
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
      {ctxMenu && (
        <ContextMenu
          x={ctxMenu.x}
          y={ctxMenu.y}
          items={buildMemoCtxItems({
            memo: memosRef.current.find((m) => m.id === ctxMenu.memoId),
            onCopy: copy,
            onPin: (id) => invoke("toggle_memo_pin", { id }).catch(() => {}),
            onEdit: openDetailEditing,
            onRemove: remove,
            onSink: (id) => invoke("sink_memo", { id }).catch(() => {}),
          })}
          onClose={() => setCtxMenu(null)}
        />
      )}
      {dragUI &&
        createPortal(
          <div className="drag-ghost" style={{ left: dragUI.x, top: dragUI.y }}>
            {dragUI.horizontal
              ? t("line.reorder")
              : dragUI.off
                ? t("line.takeoffNow")
                : t("line.takeoff")}
          </div>,
          document.body,
        )}
    </div>
  );
}

/** The 3 most recently used distinct clothespin colors (direction 81). */
function recentPinColors(memos: Memo[]): string[] {
  const seen: string[] = [];
  for (const m of memos) {
    // memos are newest-first from list_memos ordering
    if (m.color && !seen.includes(m.color)) seen.push(m.color);
    if (seen.length === 3) break;
  }
  return seen;
}

/** Inline sticky-note composer pinned under the rope. */
function NoteComposer({
  onCommit,
  onCancel,
  recentColors,
}: {
  onCommit: (content: string, remindIn: number | null, color: string | null) => void;
  onCancel: () => void;
  recentColors: string[];
}) {
  const [text, setText] = useState("");
  const [remindMin, setRemindMin] = useState("0");
  // quick-pick clothespin color (direction 81): null = default blue
  const [pin, setPin] = useState<string | null>(null);
  const submit = () => {
    if (text.trim()) {
      const m = Number(remindMin);
      onCommit(text, m > 0 ? m : null, pin);
    } else onCancel();
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
        {recentColors.length > 0 && (
          <span className="composer-recents" title={t("line.recentPins")}>
            {recentColors.map((c) => (
              <button
                key={c}
                className={"pal-dot" + (pin === c ? " active" : "")}
                style={{ background: c }}
                aria-label={c}
                onClick={() => setPin(pin === c ? null : c)}
              />
            ))}
          </span>
        )}
        <select
          className="line-remind"
          value={remindMin}
          aria-label={t("line.remind")}
          title={t("line.remind")}
          onChange={(e) => setRemindMin(e.target.value)}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <option value="0">⏰ {t("line.remindNone")}</option>
          <option value="5">{t("line.remindIn")} 5m</option>
          <option value="15">{t("line.remindIn")} 15m</option>
          <option value="30">{t("line.remindIn")} 30m</option>
          <option value="60">{t("line.remindIn")} 60m</option>
        </select>
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

function Rope({
  hot,
  pathRef,
}: {
  hot: boolean;
  pathRef: React.RefObject<SVGPathElement | null>;
}) {
  // the path d is rewritten every frame by the physics loop in Clothesline
  return (
    <svg className="line-rope">
      <path
        ref={(el) => { (pathRef as React.MutableRefObject<SVGPathElement | null>).current = el; }}
        d="M0,20 L1920,20"
        fill="none"
        className={"line-rope-path" + (hot ? " hot" : "")}
      />
      <circle cx="4" cy="20" r="4" className="line-rope-anchor" />
      <circle cx="1916" cy="20" r="4" className="line-rope-anchor" />
    </svg>
  );
}

/** Context-menu entries for a hanging memo: copy / pin / edit / take off. */
function buildMemoCtxItems({
  memo,
  onCopy,
  onPin,
  onEdit,
  onRemove,
  onSink,
}: {
  memo?: Memo;
  onCopy: (m: Memo) => void;
  onPin: (id: number) => void;
  onEdit: (m: Memo) => void;
  onRemove: (id: number) => void;
  onSink: (id: number) => void;
}): MenuItem[] {
  if (!memo) return [];
  return [
    { label: t("line.copy"), onClick: () => onCopy(memo) },
    { label: memo.pinned ? t("line.unpin") : t("line.pin"), onClick: () => onPin(memo.id) },
    { label: t("line.edit"), onClick: () => onEdit(memo) },
    { label: t("line.sink"), onClick: () => onSink(memo.id) },
    { label: t("line.takeOff"), onClick: () => onRemove(memo.id) },
  ];
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
  flash,
  due,
  onContext,
  onEdit,
}: {
  memo: Memo;
  swing: boolean;
  draggedOff: boolean;
  lifted: boolean;
  flash: boolean;
  due: boolean;
  onContext: (x: number, y: number) => void;
  onEdit: () => void;
}) {
  return (
    <div
      className={
        "line-card" +
        (swing ? " swing" : "") +
        (draggedOff ? " dropping" : "") +
        (lifted ? " lifted" : "") +
        (flash ? " due-flash" : "") +
        (due ? " due" : "")
      }
      data-memo={memo.id}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onContext(e.clientX, e.clientY);
      }}
      onDoubleClick={(e) => {
        e.stopPropagation();
        onEdit();
      }}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        lineDrag.current = {
          memoId: memo.id,
          startX: e.screenX,
          startY: e.screenY,
          moved: false,
          off: false,
          horizontal: false,
        };
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
        {due && <span className="line-due-mark" title={t("line.remind")}> ⏰</span>}
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

/** Spoken form of a pending reminder for the detail row (direction 65). */
function reminderLabel(at: number): string {
  const now = Math.floor(Date.now() / 1000);
  if (now >= at) return "⏰ " + t("line.remindDue");
  const mins = Math.max(1, Math.ceil((at - now) / 60));
  return `⏰ ${t("line.remindLeft")} ${mins}m`;
}

// session-level memo body zoom (direction 78): ⌘+/-/0 inside the detail
const detailZoom = { v: 1.0, subs: new Set<() => void>() };
function useDetailZoom() {
  const [zoom, setZoom] = useState(detailZoom.v);
  useEffect(() => {
    const fn = () => setZoom(detailZoom.v);
    detailZoom.subs.add(fn);
    return () => { detailZoom.subs.delete(fn); };
  }, []);
  return {
    zoom,
    onZoomKey: (e: React.KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        detailZoom.v = Math.min(2, detailZoom.v + 0.15);
      } else if (e.key === "-") {
        e.preventDefault();
        detailZoom.v = Math.max(0.7, detailZoom.v - 0.15);
      } else if (e.key === "0") {
        e.preventDefault();
        detailZoom.v = 1.0;
      } else {
        return;
      }
      detailZoom.subs.forEach((s) => s());
    },
  };
}

function MemoDetail({
  memo,
  initialEditing = false,
  copied,
  onCopy,
  onClose,
  onRemove,
  onSave,
  onTogglePin,
}: {
  memo: Memo;
  initialEditing?: boolean;
  copied: boolean;
  onCopy: () => void;
  onClose: () => void;
  onRemove: () => void;
  onSave: (content: string) => void;
  onTogglePin: () => void;
}) {
  const [editing, setEditing] = useState(initialEditing);
  const [draft, setDraft] = useState(memo.content);
  const { zoom, onZoomKey } = useDetailZoom();

  const canEdit = memo.kind !== "image"; // image memos carry no editable text

  // character/line counter for the detail head (direction 91); while editing
  // it reads the draft so it updates on every keystroke. Image/color memos
  // carry no meaningful text, so they show no counter. Character count is in
  // code points (surrogate pairs count once) and excludes line breaks —
  // lines are reported separately.
  const countSource = editing ? draft : memo.content;
  const counted = memo.kind !== "image" && memo.kind !== "color";
  const counter = counted
    ? {
        chars: [...countSource.replace(/\n/g, "")].length,
        lines: countSource === "" ? 0 : countSource.split("\n").length,
      }
    : null;

  return (
    <div
      className="line-detail"
      onClick={(e) => e.stopPropagation()}
      onKeyDown={onZoomKey}
      style={{ ["--memo-zoom" as string]: String(zoom) }}
    >
      {!editing && (
        <div className="line-palette" title={t("line.color")}>
          {MEMO_COLORS.map((c) => (
            <button
              key={c}
              className={"pal-dot" + (memo.color === c ? " active" : "")}
              style={{ background: c }}
              onClick={() =>
                invoke("set_memo_color", { id: memo.id, color: c }).catch(() => {})
              }
            />
          ))}
        </div>
      )}
      <div className="line-detail-head">
        <span className="line-badge" style={{ position: "static" }}>
          {kindLabel(memo.kind)}
        </span>
        <span className="line-detail-time">{relTime(memo.created_at)}</span>
        {counter && (
          <span className="line-detail-count" title={t("line.countTitle")}>
            {counter.chars} {t("line.chars")} · {counter.lines} {t("line.lines")}
          </span>
        )}
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
      {!editing && (
        <div className="line-remind-row">
          <span className="line-remind-state">
            {memo.remind_at == null
              ? "⏰ " + t("line.remindNone")
              : reminderLabel(memo.remind_at)}
          </span>
          <select
            className="line-remind"
            aria-label={t("line.remind")}
            defaultValue=""
            onChange={(e) => {
              const v = e.target.value;
              if (!v) return;
              const at =
                v === "off"
                  ? null
                  : Math.floor(Date.now() / 1000) + Number(v) * 60;
              invoke("set_memo_reminder", { id: memo.id, remindAt: at }).catch(
                () => {},
              );
              e.target.value = "";
            }}
          >
            <option value="">{t("line.remindChange")}</option>
            <option value="5">{t("line.remindIn")} 5m</option>
            <option value="15">{t("line.remindIn")} 15m</option>
            <option value="30">{t("line.remindIn")} 30m</option>
            <option value="60">{t("line.remindIn")} 60m</option>
            <option value="off">{t("line.remindCancel")}</option>
          </select>
        </div>
      )}
      {!editing && (
        <div className="line-remind-row">
          <span className="line-remind-state" title={memo.note ?? undefined}>
            {memo.note
              ? "📝 " + memo.note.slice(0, 24)
              : "📝 " + t("line.noteNone")}
          </span>
          <input
            className="line-note-input"
            aria-label={t("line.note")}
            placeholder={t("ctx.notePlaceholder")}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Enter") {
                e.preventDefault();
                const v = (e.target as HTMLInputElement).value;
                invoke("set_memo_note", { id: memo.id, note: v }).catch(() => {});
                (e.target as HTMLInputElement).blur();
              } else if (e.key === "Escape") {
                e.preventDefault();
                (e.target as HTMLInputElement).blur();
              }
            }}
          />
        </div>
      )}
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
  if (memo.kind === "image") {
    // thumbnail comes from the b64 preview captured at hang time; when it is
    // missing (legacy rows) show a neutral image placeholder instead of the
    // raw dimension string the content column carries (direction 95)
    if (memo.preview) {
      return (
        <div
          className="line-img"
          style={{ backgroundImage: `url(data:image/png;base64,${memo.preview})` }}
        />
      );
    }
    return (
      <div className="line-img empty" title={memo.content}>
        🖼️
      </div>
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
