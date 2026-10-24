import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { check as checkUpdate, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { IS_MAC } from "./platform";
import { t, useLang, setPref, getPref, type LangPref } from "./i18n";

type UpdateStatus =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "uptodate" }
  | { kind: "available"; version: string; notes: string; update: Update }
  | { kind: "downloading"; pct: number }
  | { kind: "ready" }
  | { kind: "error"; msg: string };

function formatHotkey(s: string): string {
  // macOS: "Super+Shift+KeyV" → "⌘⇧V"; elsewhere → "Win+Shift+V" / "Ctrl+Alt+4".
  const parts = s.split("+").map((p) => p.trim()).filter(Boolean);
  if (IS_MAC) {
    const glyph: Record<string, string> = {
      Super: "⌘", Meta: "⌘", Cmd: "⌘", Command: "⌘",
      Shift: "⇧", Control: "⌃", Ctrl: "⌃", Alt: "⌥", Option: "⌥",
    };
    return parts.map((p) => glyph[p] ?? trimCode(p)).join("");
  }
  const name: Record<string, string> = {
    Super: "Win", Meta: "Win", Cmd: "Win", Command: "Win",
    Shift: "Shift", Control: "Ctrl", Ctrl: "Ctrl", Alt: "Alt", Option: "Alt",
  };
  const keys = parts.map((p) => name[p] ?? trimCode(p));
  const mods = keys.slice(0, -1);
  const last = keys[keys.length - 1];
  return `${mods.map((m) => m + "+").join("")}${last}`;
}

function trimCode(p: string): string {
  if (p.startsWith("Key")) return p.slice(3);
  if (p.startsWith("Digit")) return p.slice(5);
  return p;
}

interface HotkeysInfo {
  drawer: string;
  screenshot: string;
  clothesline: string;
  screenshot_registered: boolean;
  clothesline_registered: boolean;
}

export default function Settings() {
  useLang();
  const close = () => getCurrentWindow().hide();
  const [version, setVersion] = useState<string>("");
  const [acc, setAcc] = useState<boolean | null>(null);
  const [upd, setUpd] = useState<UpdateStatus>({ kind: "idle" });
  const [hks, setHks] = useState<HotkeysInfo | null>(null);
  const [autostart, setAutostart] = useState<boolean>(false);
  const [langPref, setLangPref] = useState<LangPref>(() => getPref());

  const reloadHotkeys = useCallback(async () => {
    setHks(await invoke<HotkeysInfo>("get_hotkeys"));
  }, []);

  const recheck = useCallback(async () => {
    const ok = await invoke<boolean>("check_accessibility");
    setAcc(ok);
  }, []);

  const checkForUpdate = useCallback(async () => {
    setUpd({ kind: "checking" });
    try {
      const update = await checkUpdate();
      if (update) {
        setUpd({
          kind: "available",
          version: update.version,
          notes: update.body ?? "",
          update,
        });
      } else {
        setUpd({ kind: "uptodate" });
      }
    } catch (e: unknown) {
      setUpd({ kind: "error", msg: e instanceof Error ? e.message : String(e) });
    }
  }, []);

  useEffect(() => {
    invoke<string>("app_version").then(setVersion);
    reloadHotkeys();
    invoke<boolean>("autostart_enabled").then(setAutostart);
    recheck();
    checkForUpdate();
    const unlistens: UnlistenFn[] = [];
    listen("settings-open", () => {
      reloadHotkeys();
      invoke<boolean>("autostart_enabled").then(setAutostart);
      checkForUpdate();
    }).then((u) => unlistens.push(u));
    const t = setInterval(recheck, 1500);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      clearInterval(t);
      window.removeEventListener("keydown", onKey, true);
      unlistens.forEach((u) => u());
    };
  }, [recheck, checkForUpdate, reloadHotkeys]);

  const toggleAutostart = useCallback(async (on: boolean) => {
    setAutostart(on);
    try {
      await invoke("set_autostart", { enabled: on });
    } catch (e) {
      setAutostart(!on);
      console.warn("set_autostart failed:", e);
    }
  }, []);

  const [backupMsg, setBackupMsg] = useState<string | null>(null);
  const [lineOn, setLineOn] = useState(false);
  const [wayland, setWayland] = useState(false);
  const [dedupe, setDedupe] = useState(true);
  useEffect(() => {
    invoke<boolean>("dedupe_history").then(setDedupe);
  }, []);
  const toggleDedupe = useCallback(async () => {
    const next = !dedupe;
    setDedupe(next);
    await invoke("set_dedupe_history", { enabled: next }).catch(() => {});
  }, [dedupe]);
  useEffect(() => {
    invoke<boolean>("wayland_session").then(setWayland);
  }, []);
  useEffect(() => {
    invoke<boolean>("clothesline_visible").then(setLineOn);
  }, []);
  const toggleLine = useCallback(async () => {
    const next = await invoke<boolean>("toggle_clothesline_cmd");
    setLineOn(next);
  }, []);
  const doExportBackup = useCallback(async () => {
    setBackupMsg(t("settings.exporting"));
    try {
      const path = await invoke<string>("export_backup");
      setBackupMsg(`${t("settings.exported")} ${path}`);
    } catch (e) {
      setBackupMsg(`${t("settings.exportFail")} ${e}`);
    }
  }, []);
  const doImportBackup = useCallback(async () => {
    setBackupMsg(t("settings.importing"));
    try {
      const msg = await invoke<string>("import_backup");
      setBackupMsg(msg);
    } catch (e) {
      setBackupMsg(`${t("settings.importFail")} ${e}`);
    }
  }, []);

  const downloadAndInstall = useCallback(async () => {
    if (upd.kind !== "available") return;
    let total = 0;
    let downloaded = 0;
    setUpd({ kind: "downloading", pct: 0 });
    try {
      await upd.update.downloadAndInstall((ev) => {
        if (ev.event === "Started") {
          total = ev.data.contentLength ?? 0;
        } else if (ev.event === "Progress") {
          downloaded += ev.data.chunkLength;
          setUpd({
            kind: "downloading",
            pct: total > 0 ? Math.round((downloaded / total) * 100) : 0,
          });
        } else if (ev.event === "Finished") {
          setUpd({ kind: "ready" });
        }
      });
      await relaunch();
    } catch (e: unknown) {
      setUpd({ kind: "error", msg: e instanceof Error ? e.message : String(e) });
    }
  }, [upd]);

  const grant = useCallback(async () => {
    await invoke("request_accessibility");
    await invoke("open_accessibility_settings");
  }, []);

  return (
    <div className="settings-win">
      <div className="settings-section">
        <div className="settings-row">
          <span className="settings-label">{t("settings.version")}</span>
            <span className="settings-value">
              <span>{version || "..."}</span>
              {upd.kind === "checking" && <span className="settings-tag muted">{t("settings.checking")}</span>}
              {upd.kind === "uptodate" && (
                <>
                  <span className="settings-tag ok">{t("settings.uptodate")}</span>
                  <button className="btn ghost" onClick={checkForUpdate}>{t("settings.recheck")}</button>
                </>
              )}
              {upd.kind === "available" && (
                <button className="btn primary" onClick={downloadAndInstall}>
                  {t("settings.upgrade")} {upd.version}
                </button>
              )}
              {upd.kind === "downloading" && (
                <span className="settings-tag muted">{t("settings.download")} {upd.pct}%</span>
              )}
              {upd.kind === "ready" && <span className="settings-tag ok">{t("settings.restarting")}</span>}
              {(upd.kind === "error" || upd.kind === "idle") && (
                <button className="btn ghost" onClick={checkForUpdate}>{t("settings.checkUpdate")}</button>
              )}
            </span>
          </div>
          {upd.kind === "error" && (
            <pre className="settings-err">{t("settings.updateFailed")}:{upd.msg}</pre>
          )}
          {upd.kind === "available" && upd.notes && (
            <pre className="settings-notes">{upd.notes}</pre>
          )}

          <div className="settings-subhead">{t("settings.hotkeys")}</div>
          <HotkeyRow
            kind="drawer"
            label={t("settings.hk.drawer")}
            value={hks?.drawer ?? ""}
            onSaved={reloadHotkeys}
          />
          <HotkeyRow
            kind="screenshot"
            label={t("settings.hk.screenshot")}
            value={hks?.screenshot ?? ""}
            registered={hks?.screenshot_registered ?? true}
            onSaved={reloadHotkeys}
          />
          <HotkeyRow
            kind="clothesline"
            label={t("settings.hk.clothesline")}
            value={hks?.clothesline ?? ""}
            registered={hks?.clothesline_registered ?? true}
            onSaved={reloadHotkeys}
          />

          <div className="settings-subhead">{t("settings.general")}</div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.language")}</span>
            <span className="settings-value">
              <select
                className="lang-select"
                value={langPref}
                onChange={(e) => {
                  const v = e.target.value as "auto" | "zh" | "en";
                  setPref(v);
                  setLangPref(v);
                }}
              >
                <option value="auto">{t("settings.langAuto")}</option>
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.clothesline")}</span>
            <span className="settings-value">
              <button
                className={"btn " + (lineOn ? "primary" : "ghost")}
                onClick={toggleLine}
              >
                {lineOn ? t("settings.on") : t("settings.off")}
              </button>
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.autostart")}</span>
            <span className="settings-value">
              <button
                className={"btn " + (autostart ? "primary" : "ghost")}
                onClick={() => toggleAutostart(!autostart)}
              >
                {autostart ? t("settings.on") : t("settings.off")}
              </button>
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.backup")}</span>
            <span className="settings-value">
              <button className="btn ghost" onClick={doExportBackup}>
                {t("settings.export")}
              </button>
              <button className="btn ghost" onClick={doImportBackup}>
                {t("settings.import")}
              </button>
            </span>
          </div>
          {backupMsg && <pre className="settings-notes">{backupMsg}</pre>}

          <div className="settings-row">
            <span className="settings-label">{t("settings.dedupe")}</span>
            <span className="settings-value">
              <button className={"btn " + (dedupe ? "primary" : "ghost")} onClick={toggleDedupe}>
                {dedupe ? t("settings.on") : t("settings.off")}
              </button>
            </span>
          </div>
          <p className="settings-hint">{t("settings.dedupeHint")}</p>

          {wayland && (
            <div className="settings-row">
              <span className="settings-label">{t("settings.wayland")}</span>
              <span className="settings-value settings-tag muted">{t("settings.waylandHint")}</span>
            </div>
          )}

          {IS_MAC && (
            <>
              <div className="settings-row">
                <span className="settings-label">{t("settings.accessibility")}</span>
                <span className="settings-value">
                  {acc === null ? (
                    <span className="settings-tag muted">{t("settings.detecting")}</span>
                  ) : acc ? (
                    <span className="settings-tag ok">{t("settings.granted")}</span>
                  ) : (
                    <button className="btn primary" onClick={grant}>{t("settings.grant")}</button>
                  )}
                </span>
              </div>
              {acc === false && (
                <p className="settings-hint">
                  {t("settings.accHint")}
                </p>
              )}
            </>
          )}
      </div>
    </div>
  );
}

/** One rebindable hotkey row: current combo, 修改 → capture → 确定/取消. */
function HotkeyRow({
  kind,
  label,
  value,
  registered = true,
  onSaved,
}: {
  kind: string;
  label: string;
  value: string;
  registered?: boolean;
  onSaved: () => void;
}) {
  const [recording, setRecording] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const startRecording = useCallback(async () => {
    setErr(null);
    setPending(null);
    // suspend the current global combo so pressing it during capture
    // doesn't fire the OS handler (e.g. close the drawer)
    await invoke("begin_hotkey_capture", { kind }).catch(() => {});
    setRecording(true);
  }, [kind]);

  const cancelRecording = useCallback(async () => {
    setRecording(false);
    setPending(null);
    setErr(null);
    await invoke("cancel_hotkey_capture", { kind }).catch(() => {});
  }, [kind]);

  const confirmRecording = useCallback(async () => {
    if (!pending) {
      cancelRecording();
      return;
    }
    try {
      await invoke("set_hotkey", { kind, value: pending });
      setRecording(false);
      setPending(null);
      setErr(null);
      onSaved();
    } catch (e) {
      setErr(String(e));
      await invoke("cancel_hotkey_capture", { kind }).catch(() => {});
      setRecording(false);
      setPending(null);
    }
  }, [pending, cancelRecording, kind, onSaved]);

  // restore the global combo if the row unmounts mid-capture
  useEffect(() => {
    return () => {
      if (recording) {
        invoke("cancel_hotkey_capture", { kind }).catch(() => {});
      }
    };
  }, [recording, kind]);

  const captureHotkey = useCallback(
    (e: React.KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.key === "Escape") {
        cancelRecording();
        return;
      }
      if (e.key === "Enter") {
        confirmRecording();
        return;
      }
      const mods: string[] = [];
      if (e.metaKey) mods.push("Super");
      if (e.ctrlKey) mods.push("Control");
      if (e.altKey) mods.push("Alt");
      if (e.shiftKey) mods.push("Shift");
      const c = e.code;
      const isKey =
        c.startsWith("Key") || c.startsWith("Digit") || /^F\d+$/.test(c) || c === "Space";
      if (!isKey) return; // wait for a real key, ignore standalone modifier presses
      if (mods.length === 0) {
        setErr(t("settings.needMod"));
        return;
      }
      setPending([...mods, c].join("+"));
      setErr(null);
    },
    [cancelRecording, confirmRecording],
  );

  return (
    <div className="settings-row">
      <span className="settings-label">{label}</span>
      <span className="settings-value">
        {recording ? (
          <>
            <input
              className="hotkey-capture"
              autoFocus
              readOnly
              placeholder={t("settings.capturePlaceholder")}
              value={pending ? formatHotkey(pending) : ""}
              onKeyDown={captureHotkey}
            />
            <button className="btn primary" onClick={confirmRecording} disabled={!pending}>
              {t("settings.ok")}
            </button>
            <button className="btn ghost" onClick={cancelRecording}>
              {t("settings.cancel")}
            </button>
          </>
        ) : (
          <>
            <span className="hotkey-badge">{value ? formatHotkey(value) : "..."}</span>
            {!registered && (
              <span className="settings-tag err">{t("settings.regFail")}</span>
            )}
            <button className="btn ghost" onClick={startRecording}>
              {t("settings.modify")}
            </button>
          </>
        )}
      </span>
      {err && <pre className="settings-err">{err}</pre>}
    </div>
  );
}


