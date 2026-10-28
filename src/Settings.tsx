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
  /** underlying register error for a refused combo (direction 193) */
  screenshot_error?: string | null;
  clothesline_error?: string | null;
}

function syncAgo(ts: number): string {
  if (!ts) return "—";
  const s = Math.floor(Date.now() / 1000) - ts;
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export default function Settings() {
  useLang();
  const close = () => getCurrentWindow().hide();
  const [version, setVersion] = useState<string>("");
  // click-to-copy feedback for the version number (direction 96)
  const [verCopied, setVerCopied] = useState(false);
  const [acc, setAcc] = useState<boolean | null>(null);
  const [upd, setUpd] = useState<UpdateStatus>({ kind: "idle" });
  const [hks, setHks] = useState<HotkeysInfo | null>(null);
  const [autostart, setAutostart] = useState<boolean>(false);
  // recent sync events (direction 141)
  // peer filter over the sync log (direction 184): null shows everything
  const [logPeer, setLogPeer] = useState<string | null>(null);
  const [syncLog, setSyncLog] = useState<
    { ts: number; dir: string; peer: string; note: string }[]
  >([]);
  const reloadSyncLog = useCallback(() => {
    invoke<{ ts: number; dir: string; peer: string; note: string }[]>("sync_events")
      .then(setSyncLog)
      .catch(() => {});
  }, []);
  // transient status line for export actions (direction 134)
  const [diagMsg, setMsg] = useState<string | null>(null);
  // LAN peers over _tietie-sync._tcp mDNS (direction 127)
  const [peers, setPeers] = useState<{ instance: string; hostname: string; addr: string }[]>([]);
  const reloadPeers = useCallback(() => {
    invoke<{ instance: string; hostname: string; addr: string }[]>("mdns_peers")
      .then(setPeers)
      .catch(() => {});
  }, []);
  // pairing state machine (direction 128): a pending 6-digit code and the
  // trusted-device list
  const [pairCode, setPairCode] = useState<string | null>(null);
  const [pairTarget, setPairTarget] = useState<string | null>(null);
  const [pairInput, setPairInput] = useState("");
  const [paired, setPaired] = useState<
    { instance: string; addr: string; created_at: number; name: string | null; last_sync_at: number }[]
  >([]);
  // typed-message flow (direction 148): which paired peer is being messaged
  const [msgTo, setMsgTo] = useState<string | null>(null);
  // file-transfer feedback (direction 148b)
  const [fileMsg, setFileMsg] = useState<string | null>(null);
  const [msgText, setMsgText] = useState("");
  const [syncOn, setSyncOn] = useState(false);
  const reloadPaired = useCallback(() => {
    invoke<
      { instance: string; addr: string; created_at: number; name: string | null; last_sync_at: number }[]
    >("pairing_list")
      .then(setPaired)
      .catch(() => {});
  }, []);
  const [langPref, setLangPref] = useState<LangPref>(() => getPref());
  const [fs, setFs] = useState<FontScale>(() => getFontScale());
  useEffect(() => onFontScaleChange(() => setFs(getFontScale())), []);
  // deep link: #sec-lan / #sec-hotkeys / #sec-general scrolls that section
  // into view on open (direction 188) — the window keeps its URL for life,
  // so also re-check when the settings-open event re-shows it
  useEffect(() => {
    const scroll = () => {
      const h = window.location.hash.replace("#", "");
      if (!h) return;
      document.getElementById(h)?.scrollIntoView({ block: "start" });
    };
    scroll();
    const un = listen("settings-open", scroll);
    return () => {
      un.then((u) => u()).catch(() => {});
    };
  }, []);
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

  // live occupancy re-probe (direction 71): retry any refused combo and
  // refresh the whole hotkey panel
  const recheckHotkeys = useCallback(async () => {
    setHks(await invoke<HotkeysInfo>("recheck_hotkeys"));
  }, []);

  // restore all three combos to factory values (direction 158); a factory
  // combo already taken (e.g. a stray registration) keeps the working combo
  // for that kind — the rest still restore, and the panel always refreshes
  const resetHotkeys = useCallback(async () => {
    const defs = await invoke<Record<string, string>>("hotkey_defaults");
    for (const [kind, value] of Object.entries(defs)) {
      await invoke("set_hotkey", { kind, value }).catch((e) =>
        console.warn(`reset ${kind} kept current combo:`, e));
    }
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
      reloadPeers();
      reloadPaired();
      invoke<boolean>("sync_state").then(setSyncOn).catch(() => {});
      reloadSyncLog();
      invoke<boolean>("autostart_enabled").then(setAutostart);
      checkForUpdate();
    }).then((u) => unlistens.push(u));
    const t = setInterval(recheck, 1500);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // while a hotkey capture is active, Esc belongs to the capture
        // input (cancel recording) — don't close the window over it
        if ((e.target as HTMLElement)?.closest?.(".hotkey-capture")) return;
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
  // drawer width preset (direction 87)
  const [dwidth, setDwidth] = useState<"full" | "80" | "60">("full");
  useEffect(() => {
    invoke<string>("drawer_width").then((w) => {
      if (w === "80" || w === "60") setDwidth(w);
    });
  }, []);
  const toggleDedupe = useCallback(async () => {
    const next = !dedupe;
    setDedupe(next);
    await invoke("set_dedupe_history", { enabled: next }).catch(() => {});
  }, [dedupe]);
  useEffect(() => {
    invoke<boolean>("wayland_session").then(setWayland);
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
              <button
                className="ver-copy"
                title={t("settings.copyVersion")}
                onClick={() => {
                  if (!version) return;
                  navigator.clipboard.writeText(version).catch(() => {});
                  setVerCopied(true);
                  window.setTimeout(() => setVerCopied(false), 1200);
                }}
              >
                {version || "..."}{verCopied ? " ✓" : ""}
              </button>
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

          <div id="sec-lan" className="settings-subhead">{t("settings.lan")}</div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.lanDevices")}</span>
            <span className="settings-value lan-peers">
              {peers.length === 0 ? (
                <span className="settings-tag muted">{t("settings.lanNone")}</span>
              ) : (
                peers.map((p) => (
                  <span key={p.instance} className="lan-peer" title={p.addr}>
                    {p.instance} · {p.addr}
                  </span>
                ))
              )}
              <button className="btn ghost" onClick={reloadPeers}>
                {t("settings.lanRefresh")}
              </button>
            </span>
          </div>

          <div className="settings-row">
            <span className="settings-label">{t("settings.pairing")}</span>
            <span className="settings-value lan-peers">
              {peers.length === 0 && (
                <span className="settings-tag muted">{t("settings.lanNone")}</span>
              )}
              {peers.map((p) => (
                <span key={p.instance} className="lan-peer">
                  {p.instance}
                  <button
                    className="btn ghost"
                    onClick={() => {
                      invoke<string>("pairing_begin", { instance: p.instance })
                        .then((code) => {
                          setPairCode(code);
                          setPairTarget(p.instance);
                          setPairInput("");
                        })
                        .catch(() => {});
                    }}
                  >
                    {t("settings.pair")}
                  </button>
                </span>
              ))}
              {pairCode && (
                <span className="settings-tag warn" title={t("settings.pairHint")}>
                  {t("settings.pairCodeFor")} {pairTarget}: <b>{pairCode}</b>
                  <input
                    className="pair-input"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder={t("settings.pairEnter")}
                    value={pairInput}
                    onChange={(e) => setPairInput(e.target.value.replace(/\D/g, ""))}
                    onKeyDown={(e) => {
                      if (e.key !== "Enter") return;
                      e.preventDefault();
                      invoke("pairing_join", {
                        instance: pairTarget,
                        code: pairInput,
                      })
                        .then(() => {
                          setPairCode(null);
                          setPairTarget(null);
                          setPairInput("");
                          reloadPaired();
                        })
                        .catch(() => {});
                    }}
                  />
                </span>
              )}
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.syncOn")}</span>
            <span className="settings-value">
              <input
                type="checkbox"
                checked={syncOn}
                onChange={(e) => {
                  const on = e.target.checked;
                  setSyncOn(on);
                  invoke("sync_set", { on }).catch(() => {});
                }}
              />
              <span className="settings-tag muted">{t("settings.syncHint")}</span>
            </span>
          </div>
          <div className="settings-row">
            <span className="settings-label">{t("settings.paired")}</span>
            <span className="settings-value lan-peers">
              {paired.length === 0 ? (
                <span className="settings-tag muted">{t("settings.pairedNone")}</span>
              ) : (
                // most-recently-synced first (direction 203): never-synced
                // peers (0) keep their pairing-time order behind synced ones
                [...paired]
                .sort((a, b) => (b.last_sync_at || 0) - (a.last_sync_at || 0))
                .map((p) => (
                  <span key={p.instance} className="lan-peer" title={p.addr}>
                    <input
                      className="pair-name"
                      defaultValue={p.name ?? p.instance}
                      aria-label={t("settings.rename")}
                      onKeyDown={(e) => {
                        if (e.key !== "Enter") return;
                        e.preventDefault();
                        invoke("pairing_rename", {
                          instance: p.instance,
                          name: (e.target as HTMLInputElement).value,
                        })
                          .then(() => {
                            (e.target as HTMLInputElement).blur();
                            reloadPaired();
                          })
                          .catch(() => {});
                      }}
                    />
                    · {t("settings.lastSync")} {syncAgo(p.last_sync_at)}
                    <button
                      className="btn ghost"
                      title={t("settings.msg")}
                      onClick={() =>
                        setMsgTo(msgTo === p.instance ? null : p.instance)
                      }
                    >
                      💬
                    </button>
                    <button
                      className="btn ghost"
                      title={t("settings.sendFile")}
                      onClick={() => {
                        invoke<string>("file_pick_and_send", { instance: p.instance })
                          .then((r) => setFileMsg(r))
                          .catch((e) => setFileMsg(String(e)));
                        window.setTimeout(() => setFileMsg(null), 4000);
                      }}
                    >
                      📎
                    </button>
                    <button
                      className="btn ghost"
                      onClick={() => {
                        invoke("pairing_unpair", { instance: p.instance })
                          .then(reloadPaired)
                          .catch(() => {});
                      }}
                    >
                      {t("settings.unpair")}
                    </button>
                  </span>
                ))
              )}
              {fileMsg && (
                <span className="settings-tag ok">{fileMsg}</span>
              )}
              {msgTo && (
                <span className="lan-peer msg-row">
                  <span className="settings-tag muted">{msgTo}</span>
                  <input
                    className="pair-input"
                    autoFocus
                    maxLength={2000}
                    placeholder={t("settings.msgPlaceholder")}
                    value={msgText}
                    onChange={(e) => setMsgText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key !== "Enter") return;
                      e.preventDefault();
                      const text = msgText.trim();
                      if (!text) return;
                      invoke("msg_send", { instance: msgTo, text })
                        .then(() => {
                          setMsgText("");
                          setMsgTo(null);
                          reloadPaired();
                        })
                        .catch(() => {});
                    }}
                  />
                </span>
              )}
            </span>
          </div>

          <div className="settings-row">
            <span className="settings-label">{t("settings.syncLog")}</span>
            <span className="settings-value sync-log">
              {syncLog.length === 0 ? (
                <span className="settings-tag muted">{t("settings.syncLogEmpty")}</span>
              ) : (
                [...syncLog]
                .filter((e) => logPeer === null || e.peer === logPeer)
                .reverse()
                .map((e, i) => (
                  <button
                    key={i}
                    className={"sync-ev sync-ev" + e.dir + (logPeer === e.peer ? " on" : "")}
                    title={`${t("settings.logFilter")}\n${new Date(e.ts * 1000).toLocaleString()}`}
                    onClick={() => setLogPeer((p) => (p === e.peer ? null : e.peer))}
                  >
                    {new Date(e.ts * 1000).toLocaleTimeString()} {e.dir === "in" ? "⇦" : e.dir === "out" ? "⇨" : "⚠"}{" "}
                    {e.peer} · {e.note}
                  </button>
                ))
              )}
              <button className="btn ghost" onClick={reloadSyncLog}>
                {t("settings.lanRefresh")}
              </button>
            </span>
          </div>

          <div id="sec-hotkeys" className="settings-subhead">{t("settings.hotkeys")}</div>
          <HotkeyRow
            kind="drawer"
            order={1}
            label={t("settings.hk.drawer")}
            value={hks?.drawer ?? ""}
            others={[hks?.screenshot ?? "", hks?.clothesline ?? ""]}
            onSaved={reloadHotkeys}
          />
          <HotkeyRow
            kind="screenshot"
            order={2}
            label={t("settings.hk.screenshot")}
            value={hks?.screenshot ?? ""}
            others={[hks?.drawer ?? "", hks?.clothesline ?? ""]}
            registered={hks?.screenshot_registered ?? true}
            regDetail={hks?.screenshot_error}
            onSaved={reloadHotkeys}
          />
          <div className="settings-row">
            <span className="settings-label">{t("settings.hkRecheck")}</span>
            <span className="settings-value">
              <button className="btn ghost" onClick={recheckHotkeys}>
                {t("settings.hkRecheckBtn")}
              </button>
              <button className="btn ghost" onClick={resetHotkeys}>
                {t("settings.hkResetBtn")}
              </button>
            </span>
          </div>

          <div className="settings-row">
            <span className="settings-label">{t("settings.diag")}</span>
            <span className="settings-value">
              <button
                className="btn ghost"
                title={t("settings.diagPath")}
                onClick={async () => {
                  try {
                    const path = await invoke<string>("export_diagnostics");
                    setMsg(`已导出: ${path}`);
                    invoke("reveal_path", { path }).catch(() => {});
                  } catch (e) {
                    setMsg(`导出失败: ${e}`);
                  }
                }}
              >
                {t("settings.diagBtn")}
              </button>
              <span className="settings-tag muted">{t("settings.diagHint")}</span>
              {diagMsg && <span className="settings-tag ok">{diagMsg}</span>}
            </span>
          </div>

          <div id="sec-general" className="settings-subhead">{t("settings.general")}</div>
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
                onKeyDown={(e) => {
                  // letter jumps while focused (direction 197): a=跟随系统 /
                  // z=中文 / e=English — deterministic, unlike the native
                  // select's first-letter search which can't match pinyin
                  const map: Record<string, "auto" | "zh" | "en"> = {
                    a: "auto",
                    z: "zh",
                    e: "en",
                  };
                  const v = map[e.key.toLowerCase()];
                  if (!v) return;
                  e.preventDefault();
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

          <div className="settings-row">
            <span className="settings-label">{t("settings.drawerWidth")}</span>
            <span className="settings-value">
              <select
                className="lang-select"
                value={dwidth}
                aria-label={t("settings.drawerWidth")}
                onChange={async (e) => {
                  const v = e.target.value as "full" | "80" | "60";
                  setDwidth(v);
                  await invoke("set_drawer_width", { preset: v }).catch(() => {});
                }}
              >
                <option value="full">{t("settings.wFull")}</option>
                <option value="80">{t("settings.w80")}</option>
                <option value="60">{t("settings.w60")}</option>
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
/**
 * Combos the OS tends to claim itself — capturable by our recorder but
 * shadowed system-wide, so we warn before saving (direction 101).
 * Meta = Super/⌘. Keys use the KeyboardEvent.code form the recorder emits.
 */
const SYS_HOTKEY_CONFLICTS: Record<string, string> = {
  "Alt+F4": "close window",
  "Meta+KeyL": "lock screen",
  "Meta+KeyD": "show desktop",
  "Meta+KeyE": "file explorer",
  "Meta+KeyV": "clipboard history",
  "Meta+KeyQ": "quit app (macOS)",
  "Meta+Space": "input method switch",
  // Win11 新版把它绑成了「声音输出」快速面板：RegisterHotKey 探测不到这种
  // 占用（注册照常成功），只有真实按键才会被系统吃掉——真实事故，见迭代记录
  "Control+Alt+KeyV": "sound output panel (Win11)",
};

function hotkeyWarning(pending: string, others: string[]): string | null {
  if (others.filter(Boolean).includes(pending)) return t("settings.hkDup");
  if (SYS_HOTKEY_CONFLICTS[pending]) return t("settings.hkSys");
  return null;
}

function HotkeyRow({
  kind,
  label,
  value,
  others = [],
  registered = true,
  regDetail,
  order,
  onSaved,
}: {
  kind: string;
  label: string;
  value: string;
  others?: string[];
  registered?: boolean;
  /** last register error from the backend (direction 193 tooltip) */
  regDetail?: string | null;
  /** 1-based position badge (direction 206) */
  order?: number;
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
      <span className="settings-label">
        {order != null && <span className="hk-order" aria-hidden="true">{order}</span>}
        {label}
      </span>
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
            {pending && hotkeyWarning(pending, others) && (
              <span className="settings-tag warn" title={hotkeyWarning(pending, others) ?? undefined}>
                ⚠ {hotkeyWarning(pending, others)}
              </span>
            )}
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
            {/* saved combo sits on a system-claimed combination → standing
                red mark on the row (direction 152; 101 only warned mid-capture) */}
            {SYS_HOTKEY_CONFLICTS[value] && (
              <span className="settings-tag err" title={SYS_HOTKEY_CONFLICTS[value]}>
                {t("settings.hkSys")}
              </span>
            )}
            {!registered && (
              <span
                className="settings-tag err"
                title={regDetail ?? t("settings.regFail")}
              >
                {t("settings.regFail")}
              </span>
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


