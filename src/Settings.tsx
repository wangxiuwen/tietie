import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { check as checkUpdate, type Update } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { IS_MAC } from "./platform";
import { t, useLang, setPref, getPref, type LangPref } from "./i18n";
import { getFontScale, setFontScale, onFontScaleChange, type FontScale } from "./fontScale";
import { getAccent, setAccent, onAccentChange, type Accent } from "./accent";

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
  const [fs, setFs] = useState<FontScale>(() => getFontScale());
  useEffect(() => onFontScaleChange(() => setFs(getFontScale())), []);
  const [accent, setAccentState] = useState<Accent>(() => getAccent());
  useEffect(() => onAccentChange(() => setAccentState(getAccent())), []);
  const [retention, setRetention] = useState(0);
  useEffect(() => {
    invoke<number>("retention_days").then(setRetention);
  }, []);
  const [maxHist, setMaxHist] = useState(500);
  useEffect(() => {
    invoke<number>("max_history").then(setMaxHist);
  }, []);
  // known source apps from history (for the blacklist picker) + current list
  const [sources, setSources] = useState<string[]>([]);
  const [blacklist, setBlacklist] = useState<string[]>([]);
  useEffect(() => {
    invoke<string[]>("get_source_blacklist").then(setBlacklist);
    invoke<{ source_app: string | null }[]>("list_items", { limit: 500 }).then((is) => {
      const set = new Set<string>();
      for (const it of is) if (it.source_app) set.add(it.source_app);
      setSources([...set].sort());
    });
  }, []);
  const toggleBl = useCallback((app: string) => {
    setBlacklist((cur) => {
      const next = cur.includes(app) ? cur.filter((a) => a !== app) : [...cur, app];
      invoke("set_source_blacklist", { apps: next }).catch(() => {});
      return next;
    });
  }, []);
  const addBl = useCallback(() => {
    const name = window.prompt?.("应用进程名（如 1Password）");
    if (name && name.trim()) {
      const n = name.trim();
      setBlacklist((cur) => {
        if (cur.includes(n)) return cur;
        const next = [...cur, n];
        invoke("set_source_blacklist", { apps: next }).catch(() => {});
        return next;
      });
    }
  }, []);

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
  // stale-backup banner (direction 63): >7 days since the last export
  const [lastBackup, setLastBackup] = useState(0);
  useEffect(() => {
    invoke<number>("last_backup_at").then(setLastBackup);
  }, []);
  const backupStale = Date.now() / 1000 - lastBackup > 7 * 86400;
  const exportNow = useCallback(async () => {
    try {
      const path = await invoke<string>("export_backup");
      setLastBackup(Math.floor(Date.now() / 1000));
      setBackupMsg(`已导出: ${path}`);
    } catch (e) {
      setBackupMsg(`导出失败: ${e}`);
    }
  }, []);
  useEffect(() => {
    invoke<boolean>("dedupe_history").then(setDedupe);
  }, []);
  const [dbl, setDbl] = useState<"paste" | "copy" | "edit">("paste");
  useEffect(() => {
    invoke<string>("dblclick_action").then((a) => {
      if (a === "copy" || a === "edit") setDbl(a);
    });
  }, []);
  // startup db integrity verdict (direction 70); assume ok until told
  const [dbBad, setDbBad] = useState(false);
  useEffect(() => {
    invoke<boolean>("db_integrity_ok").then((ok) => setDbBad(!ok));
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
      {dbBad && (
        <div className="backup-banner db-bad" role="alert">
          <span>🚨 {t("db.badBanner")}</span>
          <button className="btn ghost" onClick={exportNow}>
            {t("backup.exportNow")}
          </button>
        </div>
      )}
      {backupStale && (
        <div className="backup-banner" role="status">
          <span>⚠️ {t("backup.banner")}</span>
          <button className="btn ghost" onClick={exportNow}>
            {t("backup.exportNow")}
          </button>
        </div>
      )}
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
            <span className="settings-label">{t("settings.fontScale")}</span>
            <span className="settings-value">
              <select
                className="lang-select"
                value={fs}
                onChange={(e) => setFontScale(e.target.value as FontScale)}
              >
                <option value="compact">{t("settings.fsCompact")}</option>
                <option value="standard">{t("settings.fsStandard")}</option>
                <option value="large">{t("settings.fsLarge")}</option>
              </select>
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.accent")}</span>
            <span className="settings-value accent-row">
              {(["blue", "green", "purple", "orange"] as const).map((a) => (
                <button
                  key={a}
                  className={"accent-dot" + (accent === a ? " active" : "")}
                  style={{ background: { blue: "#007aff", green: "#34c759", purple: "#af52de", orange: "#ff9500" }[a] }}
                  title={t("settings.accent_" + a)}
                  onClick={() => setAccent(a)}
                />
              ))}
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
            <span className="settings-label">{t("settings.retention")}</span>
            <span className="settings-value">
              <select
                className="lang-select"
                value={String(retention)}
                onChange={(e) => {
                  const d = Number(e.target.value);
                  setRetention(d);
                  invoke("set_retention_days", { days: d }).catch(() => {});
                }}
              >
                <option value="0">{t("settings.retForever")}</option>
                <option value="7">{t("settings.ret7")}</option>
                <option value="30">{t("settings.ret30")}</option>
              </select>
            </span>
          </div>
          <p className="settings-hint">{t("settings.retHint")}</p>
          <div className="settings-row">
            <span className="settings-label">{t("settings.maxHistory")}</span>
            <span className="settings-value">
              <select
                className="lang-select"
                value={String(maxHist)}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setMaxHist(v);
                  invoke("set_max_history", { value: v }).catch(() => {});
                }}
              >
                {[200, 500, 1000, 3000].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </span>
          </div>

          {sources.length > 0 && (
            <div className="settings-row bl-row">
              <span className="settings-label">{t("settings.blacklist")}</span>
              <span className="settings-value bl-list">
                {sources.map((s) => (
                  <button
                    key={s}
                    className={"chip small" + (blacklist.includes(s) ? " active" : "")}
                    onClick={() => toggleBl(s)}
                  >
                    {s}
                  </button>
                ))}
                <button className="chip small ghost" onClick={addBl}>
                  + 手动添加
                </button>
              </span>
            </div>
          )}

          <div className="settings-row">
            <span className="settings-label">{t("settings.dedupe")}</span>
            <span className="settings-value">
              <button className={"btn " + (dedupe ? "primary" : "ghost")} onClick={toggleDedupe}>
                {dedupe ? t("settings.on") : t("settings.off")}
              </button>
            </span>
          </div>
          <p className="settings-hint">{t("settings.dedupeHint")}</p>

          <div className="settings-row">
            <span className="settings-label">{t("settings.dblclick")}</span>
            <span className="settings-value">
              <select
                className="lang-select"
                value={dbl}
                aria-label={t("settings.dblclick")}
                onChange={async (e) => {
                  const v = e.target.value as "paste" | "copy" | "edit";
                  setDbl(v);
                  await invoke("set_dblclick_action", { action: v }).catch(() => {});
                }}
              >
                <option value="paste">{t("settings.dblPaste")}</option>
                <option value="copy">{t("settings.dblCopy")}</option>
                <option value="edit">{t("settings.dblEdit")}</option>
              </select>
            </span>
          </div>

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


