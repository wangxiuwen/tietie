import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { writeText } from "@tauri-apps/plugin-clipboard-manager";
import type { ClipItem } from "./types";
import { KIND_LABEL } from "./types";

interface Slot {
  id: number;
  slot_index: number;
  label: string;
  target: string;
  icon_path: string | null;
}

const SLOT_COUNT = 8;

export default function TrayPopover() {
  const [items, setItems] = useState<ClipItem[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);

  const refresh = useCallback(async () => {
    const [is, ss] = await Promise.all([
      invoke<ClipItem[]>("list_items", { limit: 5 }),
      invoke<Slot[]>("list_slots"),
    ]);
    setItems(is.slice(0, 5));
    setSlots(ss);
  }, []);

  useEffect(() => {
    refresh();
    const unlistens: UnlistenFn[] = [];
    listen("clipboard-changed", refresh).then((u) => unlistens.push(u));
    listen("show-tray", refresh).then((u) => unlistens.push(u));
    getCurrentWindow().onFocusChanged(({ payload: focused }) => {
      if (!focused) {
        getCurrentWindow().hide();
      }
    }).then((u) => unlistens.push(u));
    return () => unlistens.forEach((u) => u());
  }, [refresh]);

  const copyBack = async (it: ClipItem) => {
    if (it.kind === "image") {
      // images: open full drawer instead
      await invoke("show_drawer");
      await getCurrentWindow().hide();
      return;
    }
    await writeText(it.content);
    await invoke("touch_item", { id: it.id });
    await getCurrentWindow().hide();
  };

  const editSlot = async (idx: number) => {
    const target = prompt(
      "粘贴要启动的目标：\n• 应用绝对路径（/Applications/Foo.app）\n• 文件夹路径\n• URL（https://...）",
    );
    if (!target) return;
    const label = prompt("显示名称", guessLabel(target)) || guessLabel(target);
    await invoke("upsert_slot", {
      slotIndex: idx,
      label,
      target,
      iconPath: null,
    });
    refresh();
  };

  const removeSlot = async (idx: number) => {
    if (!confirm("移除这个槽位？")) return;
    await invoke("delete_slot", { slotIndex: idx });
    refresh();
  };

  const launch = async (slot: Slot) => {
    await invoke("launch_target", { target: slot.target });
    await getCurrentWindow().hide();
  };

  return (
    <div className="popover">
      <div className="po-section">
        <div className="po-title">
          <span>剪切板</span>
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
        {items.length === 0 ? (
          <div className="po-empty">暂无内容</div>
        ) : (
          <div className="po-list">
            {items.map((it) => (
              <button key={it.id} className="po-row" onClick={() => copyBack(it)}>
                <span className={"po-kind kind-" + it.kind}>{KIND_LABEL[it.kind]}</span>
                <span className="po-text">{trimOne(it.preview || it.content)}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="po-divider" />

      <div className="po-section">
        <div className="po-title">
          <span>收纳 / 启动器</span>
          <span className="po-hint">点空槽设置</span>
        </div>
        <div className="po-grid">
          {Array.from({ length: SLOT_COUNT }, (_, i) => {
            const slot = slots.find((s) => s.slot_index === i);
            return slot ? (
              <button
                key={i}
                className="po-slot filled"
                onClick={() => launch(slot)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  removeSlot(i);
                }}
                title={`左键启动 · 右键移除\n${slot.target}`}
              >
                <div className="po-slot-ic">{slot.label.slice(0, 1)}</div>
                <div className="po-slot-label">{slot.label}</div>
              </button>
            ) : (
              <button key={i} className="po-slot empty" onClick={() => editSlot(i)} title="点击设置">
                <span>+</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="po-foot">
        <button className="po-foot-btn" onClick={() => invoke("show_drawer").then(() => getCurrentWindow().hide())}>
          ⌘⇧V 唤起
        </button>
        <button className="po-foot-btn" onClick={() => invoke("quit_app")}>
          退出
        </button>
      </div>
    </div>
  );
}

function trimOne(s: string): string {
  const oneline = s.replace(/\s+/g, " ").trim();
  return oneline.length > 60 ? oneline.slice(0, 60) + "…" : oneline;
}

function guessLabel(target: string): string {
  if (target.startsWith("http")) {
    try {
      return new URL(target).hostname;
    } catch {
      return target;
    }
  }
  const parts = target.split("/").filter(Boolean);
  const last = parts.pop() || target;
  return last.replace(/\.app$/, "");
}
