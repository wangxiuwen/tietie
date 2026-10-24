import { useEffect, useRef } from "react";
import { t } from "./i18n";

export interface MenuItem {
  label: string;
  onClick: () => void;
  danger?: boolean;
  separatorBefore?: boolean;
}

/**
 * Custom div context menu (native menus can't be styled / don't work the
 * same across the three platforms). Renders at viewport coords, clamps to
 * the window, closes on Esc / outside click / scroll.
 */
export function ContextMenu({
  x,
  y,
  items,
  onClose,
}: {
  x: number;
  y: number;
  items: MenuItem[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("mousedown", onDown, true);
    window.addEventListener("wheel", onClose, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("mousedown", onDown, true);
      window.removeEventListener("wheel", onClose, true);
    };
  }, [onClose]);

  // clamp so the menu never leaves the window
  const style: React.CSSProperties = {
    left: Math.min(x, window.innerWidth - 190),
    top: Math.min(y, window.innerHeight - items.length * 30 - 16),
  };

  return (
    <div ref={ref} className="ctx-menu" style={style}>
      {items.map((it, i) => (
        <button
          key={i}
          className={"ctx-item" + (it.danger ? " danger" : "") + (it.separatorBefore ? " sep" : "")}
          onClick={() => {
            onClose();
            it.onClick();
          }}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function ctxLabel(key: string): string {
  return t(key);
}
