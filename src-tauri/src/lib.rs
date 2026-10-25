mod clipboard;
mod crypt;
mod db;
mod filelog;
#[cfg(target_os = "windows")]
mod jumplist;
#[cfg(target_os = "macos")]
mod paste;
#[cfg(not(target_os = "macos"))]
mod paste_native;
#[cfg(target_os = "macos")]
mod richtext;

use parking_lot::Mutex;
use std::str::FromStr;
use std::sync::Arc;
use tauri::{
    image::Image,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, Runtime, WebviewWindow,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

/// Name of the app that most likely produced new clipboard content: the
/// frontmost app at the instant the poller spots it. Called from the polling
/// thread — the macOS hop to the main thread makes this ~ms-fast, never block.
pub(crate) fn frontmost_app_name<R: Runtime>(_app: &AppHandle<R>) -> Option<String> {
    #[cfg(target_os = "macos")]
    {
        paste::frontmost_app_name(_app)
    }
    #[cfg(not(target_os = "macos"))]
    {
        paste_native::frontmost_app_name()
    }
}

const DRAWER_HEIGHT: u32 = 380;
const TRAY_POPOVER_W: u32 = 320;
const TRAY_POPOVER_H: u32 = 460;
const CLOTHESLINE_H: u32 = 230;
const DEFAULT_DRAWER_HOTKEY: &str = "Super+Shift+KeyV";
const DEFAULT_SCREENSHOT_HOTKEY: &str = "Control+Alt+Digit4";
const DEFAULT_CLOTHESLINE_HOTKEY: &str = "Control+Alt+KeyH";

/// A hotkey kind the user can rebind: drawer / screenshot / clothesline.
pub const HOTKEY_KINDS: [&str; 3] = ["drawer", "screenshot", "clothesline"];

pub struct AppState {
    pub conn: Arc<Mutex<rusqlite::Connection>>,
    /// merge-history preference (re-copy bumps instead of adding rows)
    pub dedupe: Arc<std::sync::atomic::AtomicBool>,
    /// capture pause deadline (unix ts; 0 = recording). While now < deadline
    /// the poll loop records nothing — the password-manager scenario
    /// (direction 67).
    pub capture_paused_until: Arc<std::sync::atomic::AtomicI64>,
}

/// All three shortcuts live here. screenshot / clothesline are Option — when
/// the OS refuses registration (combo taken by another app) they stay None so
/// the settings panel can show a red "注册失败" instead of pretending.
pub struct HotkeyState {
    pub drawer: Mutex<Shortcut>,
    pub screenshot: Mutex<Option<Shortcut>>,
    pub clothesline: Mutex<Option<Shortcut>>,
}

/// Parse "Super+Shift+KeyV" → Shortcut. Last segment must be the Code.
fn parse_hotkey(s: &str) -> Option<Shortcut> {
    let mut mods = Modifiers::empty();
    let mut code: Option<Code> = None;
    for part in s.split('+').map(str::trim).filter(|p| !p.is_empty()) {
        match part {
            "Super" | "Meta" | "Cmd" | "Command" => mods |= Modifiers::SUPER,
            "Shift" => mods |= Modifiers::SHIFT,
            "Control" | "Ctrl" => mods |= Modifiers::CONTROL,
            "Alt" | "Option" => mods |= Modifiers::ALT,
            other => {
                code = Code::from_str(other).ok();
            }
        }
    }
    let c = code?;
    Some(Shortcut::new(
        if mods.is_empty() { None } else { Some(mods) },
        c,
    ))
}

fn settings_path<R: Runtime>(app: &AppHandle<R>) -> std::path::PathBuf {
    app.path()
        .app_local_data_dir()
        .expect("no app local data dir")
        .join("settings.json")
}

fn load_setting<R: Runtime>(app: &AppHandle<R>, key: &str, default: &str) -> String {
    let path = settings_path(app);
    std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.get(key).and_then(|x| x.as_str()).map(String::from))
        .unwrap_or_else(|| default.to_string())
}

fn save_setting<R: Runtime>(app: &AppHandle<R>, key: &str, value: &str) -> Result<(), String> {
    let path = settings_path(app);
    if let Some(p) = path.parent() {
        let _ = std::fs::create_dir_all(p);
    }
    let mut v: serde_json::Value = std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| serde_json::json!({}));
    v[key] = serde_json::Value::String(value.into());
    let body = serde_json::to_string_pretty(&v).map_err(|e| e.to_string())?;
    std::fs::write(&path, body).map_err(|e| e.to_string())
}

fn load_drawer_hotkey<R: Runtime>(app: &AppHandle<R>) -> String {
    load_setting(app, "drawer_hotkey", DEFAULT_DRAWER_HOTKEY)
}

fn save_drawer_hotkey<R: Runtime>(app: &AppHandle<R>, value: &str) -> Result<(), String> {
    save_setting(app, "drawer_hotkey", value)
}

/// The configured combo for a hotkey kind (drawer / screenshot / clothesline).
fn hotkey_default(kind: &str) -> &'static str {
    match kind {
        "screenshot" => DEFAULT_SCREENSHOT_HOTKEY,
        "clothesline" => DEFAULT_CLOTHESLINE_HOTKEY,
        _ => DEFAULT_DRAWER_HOTKEY,
    }
}

fn hotkey_settings_key(kind: &str) -> &'static str {
    match kind {
        "screenshot" => "screenshot_hotkey",
        "clothesline" => "clothesline_hotkey",
        _ => "drawer_hotkey",
    }
}

/// Register a fixed-kind hotkey (screenshot / clothesline) at its configured
/// combo with a couple of retries for shutdown races. No fallback chain —
/// users memorize these combos, so a silent swap would be worse than a
/// visible "注册失败" in settings.
#[cfg(desktop)]
fn register_simple_hotkey<R: Runtime>(app: &AppHandle<R>, kind: &str) -> Option<Shortcut> {
    let cfg = load_setting(app, hotkey_settings_key(kind), hotkey_default(kind));
    let shot = parse_hotkey(&cfg)?;
    for attempt in 0..3 {
        match app.global_shortcut().register(shot) {
            Ok(()) => return Some(shot),
            Err(e) => {
                log::warn!(
                    "register {kind} hotkey ({cfg}) attempt {}: {e}",
                    attempt + 1
                );
                if attempt < 2 {
                    std::thread::sleep(std::time::Duration::from_millis(700));
                }
            }
        }
    }
    None
}

/// Try to register the configured drawer hotkey; if it is taken (other app
/// holds it, or a dying previous instance hasn't released it yet), retry a
/// few times, then walk a fallback chain. The winner is persisted so tray /
/// settings / docs all agree on the combo that actually fires. A clipboard
/// manager with a silently dead hotkey is indistinguishable from broken.
#[cfg(desktop)]
fn register_drawer_with_fallback<R: Runtime>(app: &AppHandle<R>) -> (Shortcut, String) {
    let mut candidates: Vec<String> = vec![load_drawer_hotkey(app), DEFAULT_DRAWER_HOTKEY.into()];
    let extra = ["Control+Alt+KeyV", "Control+Shift+KeyV", "Alt+Shift+KeyV"];
    for e in extra {
        if !candidates.iter().any(|c| c == e) {
            candidates.push(e.to_string());
        }
    }

    for (i, cand) in candidates.iter().enumerate() {
        let Some(shot) = parse_hotkey(cand) else {
            continue;
        };
        // three attempts with backoff: the most common failure is RegisterHotKey
        // racing a previous instance that is still shutting down
        for attempt in 0..3 {
            match app.global_shortcut().register(shot) {
                Ok(()) => {
                    let first = i == 0;
                    if first {
                        return (shot, cand.clone());
                    }
                    log::warn!(
                        "configured hotkey unavailable, fell back to {cand} \
                         (settings updated)"
                    );
                    if let Err(e) = save_drawer_hotkey(app, cand) {
                        log::warn!("persist fallback hotkey failed: {e}");
                    }
                    return (shot, cand.clone());
                }
                Err(e) => {
                    log::warn!("register {cand} attempt {} failed: {e}", attempt + 1);
                    if attempt < 2 {
                        std::thread::sleep(std::time::Duration::from_millis(700));
                    }
                }
            }
        }
    }
    // Every candidate failed — keep the default parsed so state exists; the
    // settings panel will still let the user pick a fresh combo.
    log::error!("all drawer hotkey candidates failed to register");
    (
        parse_hotkey(DEFAULT_DRAWER_HOTKEY).expect("DEFAULT_DRAWER_HOTKEY must parse"),
        DEFAULT_DRAWER_HOTKEY.to_string(),
    )
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // cold-start clock: run() entry ≈ process entry after CRT init; setup
    // writes the checkpoints to the log (direction 41)
    let boot = std::time::Instant::now();
    let mut builder = tauri::Builder::default()
        // single-instance must be first: secondary launches (e.g. jump-list
        // paste) exit immediately after forwarding their args to us
        .plugin(tauri_plugin_single_instance::init(|_app, _args, _cwd| {
            #[cfg(target_os = "windows")]
            jumplist::handle_launch_args(_app, &_args);
        }))
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init());

    #[cfg(desktop)]
    {
        builder = builder.plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state() != ShortcutState::Pressed {
                        return;
                    }
                    let Some(state) = app.try_state::<HotkeyState>() else {
                        return;
                    };
                    if let Some(shot) = &*state.screenshot.lock() {
                        if shot == shortcut {
                            trigger_screenshot();
                            return;
                        }
                    }
                    if let Some(shot) = &*state.clothesline.lock() {
                        if shot == shortcut {
                            toggle_clothesline(app);
                            return;
                        }
                    }
                    if &*state.drawer.lock() == shortcut {
                        toggle_drawer(app);
                    }
                })
                .build(),
        );
    }

    builder
        .setup(move |app| {
            // File logger with rotation — releases have no console, so keep a
            // small diagnostic trail in the app local data dir.
            match filelog::FileLogger::open(
                app.path()
                    .app_local_data_dir()
                    .expect("no app local data dir")
                    .join("tietie.log"),
                log::LevelFilter::Info,
            ) {
                Ok(l) => {
                    let _ = log::set_boxed_logger(Box::new(l))
                        .map(|()| log::set_max_level(log::LevelFilter::Info));
                }
                Err(e) => {
                    // fall back to stderr rather than run blind
                    env_logger::Builder::from_env(
                        env_logger::Env::default().default_filter_or("info"),
                    )
                    .init();
                    eprintln!("file logger unavailable ({e}), falling back to stderr");
                }
            }
            // Panics go to the same trail (direction 40): release runs with
            // panic=abort, so the hook is the only trace we ever get.
            filelog::install_panic_hook();
            log::info!("panic hook installed");
            log::info!("boot: pre-setup {}ms", boot.elapsed().as_millis());

            // Hide from Dock + Cmd-Tab — clipboard utility lives in the tray,
            // not in the foreground app list. Tray icon + hotkey are the
            // only entry points needed.
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            // open db in app local data dir
            let dir = app
                .path()
                .app_local_data_dir()
                .expect("no app local data dir");
            let db_path = dir.join("tietie.sqlite");
            let conn = db::open(&db_path).expect("open sqlite");
            let conn = Arc::new(Mutex::new(conn));

            let dedupe = Arc::new(std::sync::atomic::AtomicBool::new(
                load_setting(app.handle(), "dedupe_history", "true") == "true",
            ));
            let capture_paused_until = Arc::new(std::sync::atomic::AtomicI64::new(0));
            app.manage(AppState {
                conn: conn.clone(),
                dedupe: dedupe.clone(),
                capture_paused_until: capture_paused_until.clone(),
            });

            // start clipboard polling (retention: 0=forever, else days;
            // history cap: 200/500/1000/3000 rows before trimming)
            let retention = load_setting(app.handle(), "retention_days", "0")
                .parse::<i64>()
                .unwrap_or(0);
            let max_history = load_setting(app.handle(), "max_history", "500")
                .parse::<i64>()
                .unwrap_or(500);
            // Windows: pin the AUMID and build the taskbar jump list before
            // polling starts (the poll thread refreshes it after inserts).
            #[cfg(target_os = "windows")]
            {
                jumplist::init_aumid(app.handle());
                jumplist::refresh(&conn);
            }
            clipboard::start_polling(
                app.handle().clone(),
                conn,
                dedupe,
                capture_paused_until,
                retention,
                max_history,
            );

            // Register all hotkeys FIRST so the tray tooltip can show the
            // combos that actually took. Drawer walks a fallback chain (a
            // clipboard manager with a dead primary hotkey is broken);
            // screenshot / clothesline stay at their configured combo and
            // surface registration failure to the settings panel instead.
            #[cfg(desktop)]
            {
                let (drawer, effective_str) = register_drawer_with_fallback(app.handle());
                let shot = register_simple_hotkey(app.handle(), "screenshot");
                let line = register_simple_hotkey(app.handle(), "clothesline");
                app.manage(HotkeyState {
                    drawer: Mutex::new(drawer),
                    screenshot: Mutex::new(shot),
                    clothesline: Mutex::new(line),
                });
                // startup self-check: any hotkey the OS refused?
                let failed = [
                    ("screenshot", shot.is_none()),
                    ("clothesline", line.is_none()),
                ]
                .iter()
                .filter(|(_, f)| *f)
                .count();
                log::info!(
                    "self-check: drawer hotkey {effective_str}, screenshot {}, clothesline {}",
                    if shot.is_some() { "ok" } else { "FAILED" },
                    if line.is_some() { "ok" } else { "FAILED" },
                );
                if failed > 0 {
                    log::warn!("self-check: {failed} hotkey(s) failed to register (combo taken)");
                }
                // create tray after hotkeys so the tooltip shows the real combo
                create_tray(app.handle(), &effective_str, failed)?;
            }
            #[cfg(not(desktop))]
            {
                let _ = app;
            }

            // configure drawer window
            if let Some(win) = app.get_webview_window("drawer") {
                position_drawer(&win);
                #[cfg(target_os = "macos")]
                {
                    let _ = win.set_visible_on_all_workspaces(true);
                }
            }

            // clothesline spans the top of the screen — shown only when the
            // user hasn't turned it off (persisted; some users don't want it)
            if let Some(win) = app.get_webview_window("clothesline") {
                let want = load_setting(app.handle(), "clothesline_visible", "true") == "true";
                if want {
                    position_clothesline(&win);
                    let _ = win.show();
                }
                #[cfg(target_os = "macos")]
                {
                    let _ = win.set_visible_on_all_workspaces(true);
                }
            }

            // Request Accessibility permission early — without it, synthesized
            // ⌘V key events won't be accepted by other apps, so auto-paste fails
            // silently with no UI hint.
            #[cfg(target_os = "macos")]
            {
                let trusted = paste::ensure_accessibility_trust();
                log::info!("Accessibility trusted: {trusted}");
            }

            log::info!(
                "boot: setup complete {}ms (cold start)",
                boot.elapsed().as_millis()
            );
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_items,
            list_folders,
            create_folder,
            delete_folder,
            toggle_pin,
            delete_item,
            touch_item,
            update_item_content,
            set_item_folder,
            set_item_sensitive,
            pause_capture,
            capture_paused_remaining,
            get_item_image,
            get_item_rich,
            clip_stats,
            list_memos,
            hang_item,
            hang_items,
            remove_memo,
            add_memo_direct,
            update_memo,
            toggle_memo_pin,
            reorder_memo,
            set_memo_color,
            set_memo_reminder,
            copy_memo,
            hang_preview,
            toggle_clothesline_cmd,
            clothesline_visible,
            wayland_session,
            dedupe_history,
            set_dedupe_history,
            retention_days,
            set_retention_days,
            max_history,
            set_max_history,
            get_source_blacklist,
            set_source_blacklist,
            open_library,
            delete_items,
            export_selected_text,
            export_selected_markdown,
            reveal_path,
            autostart_enabled,
            set_autostart,
            export_backup,
            last_backup_at,
            import_backup,
            show_drawer,
            hide_window,
            paste_back,
            paste_item,
            screenshot,
            open_settings,
            check_accessibility,
            request_accessibility,
            open_accessibility_settings,
            app_version,
            get_hotkeys,
            set_hotkey,
            begin_hotkey_capture,
            cancel_hotkey_capture,
            quit_app,
        ])
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. })
                && (window.label() == "drawer"
                    || window.label() == "tray-popover"
                    || window.label() == "clothesline"
                    || window.label() == "library"
                    || window.label() == "settings")
            {
                let _ = window.hide();
            }
            // DPI/scale hop (monitor move or zoom change): re-run the
            // cursor-following placement so the drawer / clothesline fit
            // the new monitor geometry instead of straddling or clipping.
            if let tauri::WindowEvent::ScaleFactorChanged { scale_factor, .. } = event {
                let label = window.label();
                if label == "drawer" || label == "clothesline" {
                    if let Some(win) = window.get_webview_window(label) {
                        if label == "drawer" {
                            position_drawer(&win);
                        } else {
                            position_clothesline(&win);
                        }
                        log::info!("scale → {scale_factor:.2}: repositioned {label}");
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Convert the stored hotkey string ("Super+Shift+KeyV") into a menu
/// accelerator ("Super+Shift+V") so the tray shows what actually triggers.
fn hotkey_to_accel(s: &str) -> String {
    s.split('+')
        .map(str::trim)
        .filter(|p| !p.is_empty())
        .map(|p| {
            if let Some(k) = p.strip_prefix("Key") {
                k.to_string()
            } else if let Some(d) = p.strip_prefix("Digit") {
                d.to_string()
            } else {
                p.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("+")
}

#[cfg(desktop)]
fn create_tray<R: Runtime>(
    app: &AppHandle<R>,
    effective_drawer_hotkey: &str,
    failed_hotkeys: usize,
) -> tauri::Result<()> {
    // muda menu accelerators can't bind the Win/Super key on Windows/Linux —
    // that combo would panic the setup hook. On macOS "Super+Shift+V" renders
    // natively as ⌘⇧V; elsewhere the combo goes into the item text instead.
    let (show_label, show_accel_src): (String, Option<String>) = if cfg!(target_os = "macos") {
        (
            "唤起剪切板".into(),
            Some(hotkey_to_accel(effective_drawer_hotkey)),
        )
    } else {
        (
            format!("唤起剪切板 ({})", hotkey_to_accel(effective_drawer_hotkey)),
            None,
        )
    };
    let show = MenuItem::with_id(
        app,
        "show",
        show_label.as_str(),
        true,
        show_accel_src.as_deref(),
    )?;
    let recent = MenuItem::with_id(app, "recent", "查看最近剪切板", true, None::<&str>)?;
    // screenshot / clothesline labels follow their configured combos
    let shot_cfg = load_setting(app, "screenshot_hotkey", DEFAULT_SCREENSHOT_HOTKEY);
    let shot = MenuItem::with_id(
        app,
        "screenshot",
        format!("截图到剪切板 ({})", hotkey_to_accel(&shot_cfg)),
        true,
        None::<&str>,
    )?;
    let line_cfg = load_setting(app, "clothesline_hotkey", DEFAULT_CLOTHESLINE_HOTKEY);
    let line = MenuItem::with_id(
        app,
        "clothesline",
        format!("晾衣架 ({})", hotkey_to_accel(&line_cfg)),
        true,
        None::<&str>,
    )?;
    let library = MenuItem::with_id(app, "library", "剪贴板库（管理窗）", true, None::<&str>)?;
    let pause = MenuItem::with_id(
        app,
        "pause_capture",
        "暂停捕获 10 分钟（口令场景）",
        true,
        None::<&str>,
    )?;
    let resume = MenuItem::with_id(app, "resume_capture", "恢复捕获", true, None::<&str>)?;
    let sep = PredefinedMenuItem::separator(app)?;
    // on Wayland, auto-paste is impossible — say so right in the tray
    #[cfg(all(unix, not(target_os = "macos")))]
    let wayland_note = if is_wayland_session() {
        Some(MenuItem::with_id(
            app,
            "wayland_note",
            "Wayland 会话：回车仅复制，不自动粘贴",
            false,
            None::<&str>,
        )?)
    } else {
        None
    };
    let about = MenuItem::with_id(app, "about", "关于贴贴", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    #[cfg(all(unix, not(target_os = "macos")))]
    let menu = if let Some(ref note) = wayland_note {
        Menu::with_items(
            app,
            &[
                &show, &recent, &shot, &line, &library, &pause, &resume, note, &sep, &about, &quit,
            ],
        )?
    } else {
        Menu::with_items(
            app,
            &[
                &show, &recent, &shot, &line, &library, &pause, &resume, &sep, &about, &quit,
            ],
        )?
    };
    #[cfg(not(all(unix, not(target_os = "macos"))))]
    let menu = Menu::with_items(
        app,
        &[
            &show, &recent, &shot, &line, &library, &pause, &resume, &sep, &about, &quit,
        ],
    )?;

    let mut tooltip = format!(
        "贴贴 — {} 唤起剪切板 · {} 晾衣架",
        hotkey_to_accel(effective_drawer_hotkey),
        hotkey_to_accel(&line_cfg)
    );
    if failed_hotkeys > 0 {
        tooltip.push_str(&format!(" ⚠ {failed_hotkeys} 个热键未注册(被占用)"));
    }

    let _tray = TrayIconBuilder::with_id("main")
        .icon(tray_icon_image())
        // macOS: template icon — the menu bar re-colors our glyph from its
        // alpha channel in both light & dark mode (direction 46; the icon is
        // a solid stroke on a transparent background, i.e. a valid template).
        // Other platforms must NOT enable it: Windows picks its own stroke
        // from the theme registry and template semantics don't exist there.
        .icon_as_template(cfg!(target_os = "macos"))
        .tooltip(tooltip)
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => toggle_drawer(app),
            "recent" => toggle_tray_popover(app),
            "screenshot" => trigger_screenshot(),
            "clothesline" => {
                toggle_clothesline(app);
            }
            "library" => {
                if let Some(win) = app.get_webview_window("library") {
                    let _ = win.show();
                    let _ = win.set_focus();
                    let _ = app.emit_to("library", "library-open", ());
                }
            }
            "about" => {
                let _ = app.emit("show-about", ());
            }
            "pause_capture" => {
                if let Some(state) = app.try_state::<AppState>() {
                    let until = db::now_unix() + 10 * 60;
                    state
                        .capture_paused_until
                        .store(until, std::sync::atomic::Ordering::Relaxed);
                    log::info!("capture paused 10m from tray (until {until})");
                }
            }
            "resume_capture" => {
                if let Some(state) = app.try_state::<AppState>() {
                    state
                        .capture_paused_until
                        .store(0, std::sync::atomic::Ordering::Relaxed);
                    log::info!("capture resumed from tray");
                }
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                position,
                ..
            } = event
            {
                position_tray_popover(tray.app_handle(), position);
                toggle_tray_popover(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

/// Windows taskbar stroke color: dark glyphs on the default light theme,
/// white glyphs on dark theme. macOS uses template icons (system-adaptive),
/// Linux taskbars are dark by convention — both keep the white original.
#[cfg(windows)]
fn tray_stroke() -> [u8; 4] {
    use windows::core::PCWSTR;
    use windows::Win32::System::Registry::{RegGetValueW, HKEY_CURRENT_USER, RRF_RT_REG_DWORD};
    let subkey: Vec<u16> = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect();
    let value: Vec<u16> = "SystemUsesLightTheme"
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect();
    let mut data: u32 = 0;
    let mut size = 4u32;
    let ok = unsafe {
        RegGetValueW(
            HKEY_CURRENT_USER,
            PCWSTR(subkey.as_ptr()),
            PCWSTR(value.as_ptr()),
            RRF_RT_REG_DWORD,
            None,
            Some(&mut data as *mut u32 as _),
            Some(&mut size as *mut u32),
        )
        .is_ok()
    };
    let light = ok && data == 1;
    let c: u8 = if light { 26 } else { 255 };
    [c, c, c, 255]
}

#[cfg(not(windows))]
fn tray_stroke() -> [u8; 4] {
    [255, 255, 255, 255]
}

fn tray_icon_image() -> Image<'static> {
    // 32x32 line-art clipboard on transparent — one outlined shape in a
    // stroke color that contrasts the taskbar (macOS: template auto-adapts;
    // Windows: registry light/dark theme; the old 16x16 hairline glyph was
    // near-invisible on hi-DPI taskbars).
    const W: i32 = 32;
    const H: i32 = 32;
    let mut buf = vec![0u8; (W * H * 4) as usize];
    let on = tray_stroke();
    log::info!(
        "tray icon stroke rgba({},{},{},{})",
        on[0],
        on[1],
        on[2],
        on[3]
    );

    let set = |buf: &mut [u8], x: i32, y: i32| {
        if (0..32).contains(&x) && (0..32).contains(&y) {
            let i = ((y * 32 + x) * 4) as usize;
            buf[i..i + 4].copy_from_slice(&on);
        }
    };
    fn clear(buf: &mut [u8], x: i32, y: i32) {
        if (0..32).contains(&x) && (0..32).contains(&y) {
            let i = ((y * 32 + x) * 4) as usize;
            buf[i..i + 4].copy_from_slice(&[0, 0, 0, 0]);
        }
    }

    // clipboard body outline, 2px strokes
    for x in 7..=26 {
        set(&mut buf, x, 6);
        set(&mut buf, x, 7);
        set(&mut buf, x, 27);
        set(&mut buf, x, 28);
    }
    for y in 6..=28 {
        set(&mut buf, 7, y);
        set(&mut buf, 8, y);
        set(&mut buf, 25, y);
        set(&mut buf, 26, y);
    }
    // open the top edge where the clip sits, then draw the clip (open bottom)
    for x in 13..=19 {
        clear(&mut buf, x, 6);
        clear(&mut buf, x, 7);
    }
    for x in 12..=20 {
        set(&mut buf, x, 2);
        set(&mut buf, x, 3);
    }
    for y in 2..=8 {
        set(&mut buf, 12, y);
        set(&mut buf, 13, y);
        set(&mut buf, 19, y);
        set(&mut buf, 20, y);
    }
    Image::new_owned(buf, W as u32, H as u32)
}

/// Logical-pt margin between the drawer's bottom edge and the dock /
/// screen bottom. The drawer rests flush against the dock (or screen
/// bottom when the dock is hidden) — no gap.
const DRAWER_BOTTOM_MARGIN: f64 = 0.0;

/// The monitor the mouse cursor is on — multi-display layouts should keep
/// the drawer / clothesline on the screen the user is actually looking at.
/// Falls back to the window's current monitor when the cursor can't be read
/// or sits outside every known monitor.
fn monitor_with_cursor<R: Runtime>(win: &WebviewWindow<R>) -> Option<tauri::Monitor> {
    let cursor = win.cursor_position().ok()?;
    let monitors = win.available_monitors().ok()?;
    monitors
        .into_iter()
        .find(|m| {
            let p = m.position();
            let s = m.size();
            cursor.x >= p.x as f64
                && cursor.x < (p.x + s.width as i32) as f64
                && cursor.y >= p.y as f64
                && cursor.y < (p.y + s.height as i32) as f64
        })
        .or_else(|| win.current_monitor().ok().flatten())
}

fn position_drawer<R: Runtime>(win: &WebviewWindow<R>) {
    if let Some(m) = monitor_with_cursor(win) {
        let size = m.size();
        let scale = m.scale_factor();
        let target_w = size.width;
        let target_h = (DRAWER_HEIGHT as f64 * scale) as u32;

        // dock_inset_px = points-of-dock × scale; 0 on non-mac
        let dock_inset_px = mac_dock_inset_px(scale);
        let margin_px = (DRAWER_BOTTOM_MARGIN * scale) as i32;

        let _ = win.set_size(PhysicalSize::new(target_w, target_h));
        let _ = win.set_position(PhysicalPosition::new(
            m.position().x,
            m.position().y + size.height as i32 - target_h as i32 - dock_inset_px - margin_px,
        ));
    }
}

#[cfg(target_os = "macos")]
fn mac_dock_inset_px(scale: f64) -> i32 {
    use objc2::MainThreadMarker;
    use objc2_app_kit::NSScreen;
    let Some(mtm) = MainThreadMarker::new() else {
        return 0;
    };
    let Some(screen) = NSScreen::mainScreen(mtm) else {
        return 0;
    };
    let frame = screen.frame();
    let visible = screen.visibleFrame();
    // Cocoa Y points up. Dock at bottom = visible.origin.y - frame.origin.y (in points).
    let dock_pt = visible.origin.y - frame.origin.y;
    if dock_pt <= 0.0 {
        return 0;
    }
    (dock_pt * scale) as i32
}

#[cfg(not(target_os = "macos"))]
fn mac_dock_inset_px(_scale: f64) -> i32 {
    0
}

/// Span the clothesline across the very top of the screen, full width.
fn position_clothesline<R: Runtime>(win: &WebviewWindow<R>) {
    if let Some(m) = monitor_with_cursor(win) {
        let size = m.size();
        let scale = m.scale_factor();
        let target_w = size.width;
        let target_h = (CLOTHESLINE_H as f64 * scale) as u32;
        let _ = win.set_size(PhysicalSize::new(target_w, target_h));
        let _ = win.set_position(PhysicalPosition::new(m.position().x, m.position().y));
    }
}

/// Show/hide the clothesline window. Returns the new visibility.
/// The choice is persisted — hidden stays hidden across restarts.
fn toggle_clothesline<R: Runtime>(app: &AppHandle<R>) -> bool {
    if let Some(win) = app.get_webview_window("clothesline") {
        let now = match win.is_visible() {
            Ok(true) => {
                let _ = win.hide();
                false
            }
            _ => {
                position_clothesline(&win);
                let _ = win.show();
                true
            }
        };
        let _ = save_setting(
            app,
            "clothesline_visible",
            if now { "true" } else { "false" },
        );
        now
    } else {
        false
    }
}

/// Whether the clothesline is currently shown (settings panel toggle).
#[tauri::command]
fn clothesline_visible(app: AppHandle) -> bool {
    app.get_webview_window("clothesline")
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false)
}

fn position_tray_popover<R: Runtime>(app: &AppHandle<R>, click: PhysicalPosition<f64>) {
    if let Some(win) = app.get_webview_window("tray-popover") {
        let scale = win.scale_factor().unwrap_or(1.0);
        let w = (TRAY_POPOVER_W as f64 * scale) as u32;
        let h = (TRAY_POPOVER_H as f64 * scale) as u32;

        // Anchor at the click, then clamp into the monitor. On Windows/KDE the
        // tray sits in a bottom taskbar — pop upward, and keep the popover's
        // bottom edge above the taskbar (the click point is INSIDE it, so
        // anchoring at click.y would overlap the bar).
        let mut x = (click.x as i32) - (w as i32 / 2);
        let mut y = (click.y as i32) + 8;
        // conservative taskbar guard (mac menu bar is at the top; no guard)
        let bottom_guard = if cfg!(target_os = "macos") { 8 } else { 52 };
        if let Ok(Some(m)) = win.current_monitor() {
            let (mx, my) = (m.position().x, m.position().y);
            let (mw, mh) = (m.size().width as i32, m.size().height as i32);
            if click.y as i32 > my + mh * 2 / 3 {
                // upward: bottom edge stays clear of the taskbar
                y = (my + mh - bottom_guard - h as i32).min(click.y as i32 - h as i32 - 8);
            }
            x = x.clamp(mx + 8, mx + mw - w as i32 - 8);
            y = y.clamp(my + 8, my + mh - h as i32 - bottom_guard);
        } else {
            x = x.max(0);
            y = y.max(0);
        }
        let _ = win.set_size(PhysicalSize::new(w, h));
        let _ = win.set_position(PhysicalPosition::new(x, y));
    }
}

/// Unconditionally show + focus the drawer (the tray popover's 查看全部).
/// toggle_drawer is wrong here: if the drawer is already visible the toggle
/// would HIDE it, and focus contention with the closing popover can flash.
fn open_drawer<R: Runtime>(app: &AppHandle<R>) {
    if let Some(win) = app.get_webview_window("drawer") {
        #[cfg(target_os = "macos")]
        {
            let mtm = unsafe { objc2::MainThreadMarker::new_unchecked() };
            paste::snapshot_frontmost(mtm);
        }
        #[cfg(not(target_os = "macos"))]
        paste_native::snapshot_frontmost();
        position_drawer(&win);
        let _ = win.show();
        let _ = win.set_focus();
        let _ = app.emit("show-drawer", ());
    }
}

fn toggle_drawer<R: Runtime>(app: &AppHandle<R>) {
    if let Some(win) = app.get_webview_window("drawer") {
        match win.is_visible() {
            Ok(true) => {
                let _ = app.emit("hide-drawer", ());
                let _ = win.hide();
            }
            _ => {
                // Snapshot frontmost app BEFORE we steal focus, so paste-back
                // can return to it and synth ⌘V into its frontmost text field.
                #[cfg(target_os = "macos")]
                {
                    let mtm = unsafe { objc2::MainThreadMarker::new_unchecked() };
                    paste::snapshot_frontmost(mtm);
                }
                #[cfg(not(target_os = "macos"))]
                paste_native::snapshot_frontmost();
                position_drawer(&win);
                let _ = win.show();
                let _ = win.set_focus();
                let _ = app.emit("show-drawer", ());
            }
        }
    }
}

fn toggle_tray_popover<R: Runtime>(app: &AppHandle<R>) {
    if let Some(win) = app.get_webview_window("tray-popover") {
        match win.is_visible() {
            Ok(true) => {
                let _ = win.hide();
            }
            _ => {
                // Snapshot frontmost app BEFORE we steal focus, so paste-back
                // can return to it. Without this, clicking a tray row writes to
                // the clipboard but the synthesized ⌘V goes to the wrong place.
                #[cfg(target_os = "macos")]
                {
                    let mtm = unsafe { objc2::MainThreadMarker::new_unchecked() };
                    paste::snapshot_frontmost(mtm);
                }
                #[cfg(not(target_os = "macos"))]
                paste_native::snapshot_frontmost();
                let _ = win.show();
                let _ = win.set_focus();
                let _ = app.emit("show-tray", ());
            }
        }
    }
}

// ─────────────────────────── IPC commands ───────────────────────────

#[tauri::command]
fn list_items(
    state: tauri::State<'_, AppState>,
    limit: Option<i64>,
) -> Result<Vec<db::ClipItem>, String> {
    let conn = state.conn.lock();
    db::list_items(&conn, limit.unwrap_or(500)).map_err(|e| e.to_string())
}

#[tauri::command]
fn list_folders(state: tauri::State<'_, AppState>) -> Result<Vec<db::Folder>, String> {
    let conn = state.conn.lock();
    db::list_folders(&conn).map_err(|e| e.to_string())
}

#[tauri::command]
fn create_folder(
    state: tauri::State<'_, AppState>,
    name: String,
    color: String,
) -> Result<i64, String> {
    let conn = state.conn.lock();
    db::create_folder(&conn, &name, &color).map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_folder(state: tauri::State<'_, AppState>, id: i64) -> Result<(), String> {
    let conn = state.conn.lock();
    db::delete_folder(&conn, id).map_err(|e| e.to_string())
}

#[tauri::command]
fn toggle_pin(state: tauri::State<'_, AppState>, id: i64) -> Result<(), String> {
    let conn = state.conn.lock();
    db::toggle_pin(&conn, id).map_err(|e| e.to_string())
}

/// Pause clipboard capture for N minutes (0 = resume now). While paused the
/// poll loop records nothing — the password-manager scenario (direction 67).
#[tauri::command]
fn pause_capture(state: tauri::State<'_, AppState>, minutes: i64) -> Result<(), String> {
    use std::sync::atomic::Ordering;
    let until = if minutes > 0 {
        db::now_unix() + minutes * 60
    } else {
        0
    };
    state.capture_paused_until.store(until, Ordering::Relaxed);
    if until > 0 {
        log::info!("capture paused for {minutes}m (until {until})");
    } else {
        log::info!("capture resumed");
    }
    Ok(())
}

/// Remaining capture-pause seconds (0 = recording normally).
#[tauri::command]
fn capture_paused_remaining(state: tauri::State<'_, AppState>) -> i64 {
    use std::sync::atomic::Ordering;
    let until = state.capture_paused_until.load(Ordering::Relaxed);
    (until - db::now_unix()).max(0)
}

/// Mark/unmark an item sensitive: AES-seals its content at rest (direction
/// 54 — protects a leaked DB file, not this machine; the app decrypts
/// transparently for display/search/copy).
#[tauri::command]
fn set_item_sensitive(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    id: i64,
    on: bool,
) -> Result<(), String> {
    {
        let conn = state.conn.lock();
        db::set_sensitive(&conn, id, on).map_err(|e| e.to_string())?;
    }
    let _ = app.emit("clipboard-changed", ());
    Ok(())
}

#[tauri::command]
fn delete_item(state: tauri::State<'_, AppState>, id: i64) -> Result<(), String> {
    let conn = state.conn.lock();
    db::delete_item(&conn, id).map_err(|e| e.to_string())
}

#[tauri::command]
fn touch_item(state: tauri::State<'_, AppState>, id: i64) -> Result<(), String> {
    let conn = state.conn.lock();
    db::touch_item(&conn, id).map_err(|e| e.to_string())
}

#[tauri::command]
fn update_item_content(
    state: tauri::State<'_, AppState>,
    id: i64,
    content: String,
) -> Result<(), String> {
    let conn = state.conn.lock();
    db::update_content(&conn, id, &content).map_err(|e| e.to_string())
}

#[tauri::command]
fn set_item_folder(
    state: tauri::State<'_, AppState>,
    id: i64,
    folder_id: Option<i64>,
) -> Result<(), String> {
    let conn = state.conn.lock();
    db::set_folder(&conn, id, folder_id).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_item_image(state: tauri::State<'_, AppState>, id: i64) -> Result<Vec<u8>, String> {
    let conn = state.conn.lock();
    match db::get_image_blob(&conn, id).map_err(|e| e.to_string())? {
        Some(b) => Ok(b),
        None => Err("no image blob".into()),
    }
}

// ─────────────────────── clothesline (晾衣架) commands ───────────────────────

/// Card color per item kind, matching the drawer's category palette.
fn kind_color(kind: &str) -> &'static str {
    match kind {
        "link" => "#34c759",
        "image" => "#ff9500",
        "code" => "#5856d6",
        "color" => "#ff2d55",
        _ => "#007aff",
    }
}

fn emit_memos_changed<R: Runtime>(app: &AppHandle<R>) {
    use tauri::Emitter;
    let _ = app.emit_to("clothesline", "memos-changed", ());
}

#[tauri::command]
fn list_memos(state: tauri::State<'_, AppState>) -> Result<Vec<db::Memo>, String> {
    let conn = state.conn.lock();
    db::list_memos(&conn).map_err(|e| e.to_string())
}

/// Hang a clip item on the clothesline (called at drag-drop from the drawer).
/// Shows the line window if it was hidden so the drop is never lost.
#[tauri::command]
fn hang_item(app: AppHandle, state: tauri::State<'_, AppState>, id: i64) -> Result<i64, String> {
    let memo_id = {
        let conn = state.conn.lock();
        let kind: String = conn
            .query_row(
                "SELECT kind FROM clip_item WHERE id = ?1",
                rusqlite::params![id],
                |r| r.get(0),
            )
            .map_err(|e| e.to_string())?;
        db::hang_memo(&conn, id, kind_color(&kind)).map_err(|e| e.to_string())?
    };
    if let Some(win) = app.get_webview_window("clothesline") {
        if !win.is_visible().unwrap_or(false) {
            position_clothesline(&win);
            let _ = win.show();
        }
    }
    emit_memos_changed(&app);
    Ok(memo_id)
}

/// Hang several clip items on the clothesline in one go (multi-select batch).
/// Shows the line if hidden; returns how many actually hung.
#[tauri::command]
fn hang_items(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    ids: Vec<i64>,
) -> Result<usize, String> {
    let mut hung = 0usize;
    {
        let conn = state.conn.lock();
        for id in &ids {
            let kind: Option<String> = conn
                .query_row(
                    "SELECT kind FROM clip_item WHERE id = ?1",
                    rusqlite::params![id],
                    |r| r.get(0),
                )
                .ok();
            let Some(kind) = kind else { continue };
            if db::hang_memo(&conn, *id, kind_color(&kind)).is_ok() {
                hung += 1;
            }
        }
    }
    if hung > 0 {
        if let Some(win) = app.get_webview_window("clothesline") {
            if !win.is_visible().unwrap_or(false) {
                position_clothesline(&win);
                let _ = win.show();
            }
        }
        emit_memos_changed(&app);
    }
    Ok(hung)
}

#[tauri::command]
fn remove_memo(app: AppHandle, state: tauri::State<'_, AppState>, id: i64) -> Result<(), String> {
    {
        let conn = state.conn.lock();
        db::remove_memo(&conn, id).map_err(|e| e.to_string())?;
    }
    emit_memos_changed(&app);
    Ok(())
}

/// Create a brand-new text memo straight on the line — a sticky note that
/// never passed through the clipboard.
#[tauri::command]
fn add_memo_direct(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    content: String,
    remind_at: Option<i64>,
) -> Result<i64, String> {
    let trimmed = content.trim().to_string();
    if trimmed.is_empty() {
        return Err("内容为空".into());
    }
    let memo_id = {
        let conn = state.conn.lock();
        conn.execute(
            "INSERT INTO memo (kind, content, preview, color, source_item_id, created_at, sort, remind_at)
             VALUES ('text', ?1, ?2, '#007aff', NULL, ?3,
                     (SELECT COALESCE(MAX(sort), -1) + 1 FROM memo), ?4)",
            rusqlite::params![
                trimmed,
                trimmed.chars().take(120).collect::<String>(),
                db::now_unix(),
                remind_at
            ],
        )
        .map_err(|e| e.to_string())?;
        conn.last_insert_rowid()
    };
    emit_memos_changed(&app);
    Ok(memo_id)
}

/// Edit a memo's text in place.
#[tauri::command]
fn update_memo(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    id: i64,
    content: String,
) -> Result<(), String> {
    let trimmed = content.trim().to_string();
    if trimmed.is_empty() {
        return Err("内容为空".into());
    }
    {
        let conn = state.conn.lock();
        conn.execute(
            "UPDATE memo SET content = ?1, preview = ?2 WHERE id = ?3",
            rusqlite::params![trimmed, trimmed.chars().take(120).collect::<String>(), id],
        )
        .map_err(|e| e.to_string())?;
    }
    emit_memos_changed(&app);
    Ok(())
}

/// Recolor a memo's clothespin from the detail-view palette.
#[tauri::command]
fn set_memo_color(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    id: i64,
    color: String,
) -> Result<(), String> {
    {
        let conn = state.conn.lock();
        conn.execute(
            "UPDATE memo SET color = ?1 WHERE id = ?2",
            rusqlite::params![color, id],
        )
        .map_err(|e| e.to_string())?;
    }
    emit_memos_changed(&app);
    Ok(())
}

/// Change or clear a memo's reminder timestamp (direction 65); null clears.
#[tauri::command]
fn set_memo_reminder(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    id: i64,
    remind_at: Option<i64>,
) -> Result<(), String> {
    {
        let conn = state.conn.lock();
        conn.execute(
            "UPDATE memo SET remind_at = ?1 WHERE id = ?2",
            rusqlite::params![remind_at, id],
        )
        .map_err(|e| e.to_string())?;
    }
    emit_memos_changed(&app);
    Ok(())
}

/// Drag-to-reorder a hanging memo to a new index (0-based).
#[tauri::command]
fn reorder_memo(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    id: i64,
    to_index: usize,
) -> Result<(), String> {
    {
        let conn = state.conn.lock();
        db::reorder_memo(&conn, id, to_index).map_err(|e| e.to_string())?;
    }
    emit_memos_changed(&app);
    Ok(())
}

/// Pin / unpin a memo — pinned notes sort to the front of the clothesline.
#[tauri::command]
fn toggle_memo_pin(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    id: i64,
) -> Result<(), String> {
    {
        let conn = state.conn.lock();
        db::toggle_memo_pin(&conn, id).map_err(|e| e.to_string())?;
    }
    emit_memos_changed(&app);
    Ok(())
}

/// Copy a memo back to the clipboard (text or the original image blob).
#[tauri::command]
fn copy_memo(state: tauri::State<'_, AppState>, id: i64) -> Result<(), String> {
    let (kind, content, source_item_id) = {
        let conn = state.conn.lock();
        conn.query_row(
            "SELECT kind, content, source_item_id FROM memo WHERE id = ?1",
            rusqlite::params![id],
            |r| {
                Ok((
                    r.get::<_, String>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, Option<i64>>(2)?,
                ))
            },
        )
        .map_err(|e| e.to_string())?
    };

    let mut cb = arboard::Clipboard::new().map_err(|e| e.to_string())?;
    if kind == "image" {
        if let Some(src) = source_item_id {
            let png = {
                let conn = state.conn.lock();
                db::get_image_blob(&conn, src).map_err(|e| e.to_string())?
            };
            if let Some(png) = png {
                let (w, h, rgba) = decode_png_rgba(&png)?;
                cb.set_image(arboard::ImageData {
                    width: w,
                    height: h,
                    bytes: std::borrow::Cow::Owned(rgba),
                })
                .map_err(|e| e.to_string())?;
                return Ok(());
            }
        }
        // source item purged from history — fall through to text copy
    }
    cb.set_text(&content).map_err(|e| e.to_string())
}

/// Drag hover hint: while a drawer card is dragged near the screen top, the
/// clothesline highlights the drop zone. None clears it.
#[tauri::command]
fn hang_preview(app: AppHandle, id: Option<i64>) {
    use tauri::Emitter;
    let _ = app.emit_to("clothesline", "hang-preview", id);
}

#[tauri::command]
fn toggle_clothesline_cmd(app: AppHandle) -> bool {
    toggle_clothesline(&app)
}

// ─────────────────────── library window commands ───────────────────────

/// Open (show + focus) the full-screen clipboard library window.
#[tauri::command]
fn open_library(app: AppHandle) {
    if let Some(win) = app.get_webview_window("library") {
        let _ = win.show();
        let _ = win.set_focus();
        let _ = app.emit_to("library", "library-open", ());
    }
}

/// Batch-delete clip items from the library table.
#[tauri::command]
fn delete_items(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    ids: Vec<i64>,
) -> Result<usize, String> {
    let n = {
        let conn = state.conn.lock();
        let mut n = 0;
        for id in &ids {
            if db::delete_item(&conn, *id).is_ok() {
                n += 1;
            }
        }
        n
    };
    let _ = app.emit("clipboard-changed", ());
    Ok(n)
}

/// Dump the selected items as Markdown: kind-grouped headings, links as
/// lists, code wrapped in fenced blocks, colors as hex, images as
/// dimension placeholders. Documents/tietie-export-<ts>.md.
#[tauri::command]
fn export_selected_markdown(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    ids: Vec<i64>,
) -> Result<String, String> {
    let mut rows: Vec<(String, String)> = Vec::new();
    {
        let conn = state.conn.lock();
        for id in &ids {
            if let Ok(row) = conn.query_row(
                "SELECT kind, content FROM clip_item WHERE id = ?1",
                rusqlite::params![id],
                |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)),
            ) {
                rows.push(row);
            }
        }
    }
    if rows.is_empty() {
        return Err("没有可导出的条目".into());
    }

    let render = |kind: &str, title: &str, items: &[(String, String)]| -> Option<String> {
        let got: Vec<&(String, String)> = items.iter().filter(|(k, _)| k == kind).collect();
        if got.is_empty() {
            return None;
        }
        let mut out = format!("## {title}\n\n");
        for (_, content) in got {
            match kind {
                "link" => out.push_str(&format!("- [{}]({})\n", content, content)),
                "code" => out.push_str(&format!("```\n{content}\n```\n")),
                "image" => out.push_str(&format!("- [图片 {content}]\n")),
                "color" => out.push_str(&format!("- `{content}`\n")),
                _ => out.push_str(&format!("- {}\n", content.replace('\n', " "))),
            }
        }
        Some(out)
    };

    let mut md = format!("# 贴贴导出（{} 条）\n\n", rows.len());
    for (kind, title) in [
        ("text", "文本"),
        ("link", "链接"),
        ("code", "代码"),
        ("color", "颜色"),
        ("image", "图片"),
    ] {
        if let Some(sec) = render(kind, title, &rows) {
            md.push_str(&sec);
            md.push('\n');
        }
    }

    let dir = app
        .path()
        .document_dir()
        .or_else(|_| app.path().app_local_data_dir())
        .map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join(format!("tietie-export-{}.md", time_fmt(db::now_unix())));
    std::fs::write(&path, md).map_err(|e| e.to_string())?;
    Ok(path.to_string_lossy().into_owned())
}

/// Reveal an exported file in the platform file manager (direction 66):
/// Explorer with the file selected on Windows, Finder reveal on macOS,
/// the parent folder on Linux desktops.
#[tauri::command]
fn reveal_path(path: String) -> Result<(), String> {
    if !std::path::Path::new(&path).exists() {
        return Err("file not found".into());
    }
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer")
            .arg(format!("/select,{path}"))
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg("-R")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let parent = std::path::Path::new(&path)
            .parent()
            .map(|p| p.to_path_buf())
            .unwrap_or_default();
        std::process::Command::new("xdg-open")
            .arg(parent)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    log::info!("revealed export: {path}");
    Ok(())
}

/// Dump the selected items' text content to Documents/tietie-export-<ts>.txt.
#[tauri::command]
fn export_selected_text(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    ids: Vec<i64>,
) -> Result<String, String> {
    let mut parts = Vec::new();
    {
        let conn = state.conn.lock();
        for id in &ids {
            if let Ok(row) = conn.query_row(
                "SELECT kind, content FROM clip_item WHERE id = ?1",
                rusqlite::params![id],
                |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)),
            ) {
                if row.0 == "image" {
                    parts.push(format!("[图片 {}]", row.1));
                } else {
                    parts.push(row.1);
                }
                parts.push("\n─".repeat(24).to_string());
            }
        }
    }
    if parts.is_empty() {
        return Err("没有可导出的条目".into());
    }
    let dir = app
        .path()
        .document_dir()
        .or_else(|_| app.path().app_local_data_dir())
        .map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join(format!("tietie-export-{}.txt", time_fmt(db::now_unix())));
    std::fs::write(&path, parts.join("\n")).map_err(|e| e.to_string())?;
    Ok(path.to_string_lossy().into_owned())
}

/// Clipboard usage stats for the Library stats panel.
#[derive(serde::Serialize)]
struct ClipStats {
    total: i64,
    today: i64,
    pinned: i64,
    by_kind: Vec<(String, i64)>,
    top_sources: Vec<(String, i64)>,
}

#[tauri::command]
fn clip_stats(state: tauri::State<'_, AppState>) -> Result<ClipStats, String> {
    let conn = state.conn.lock();
    let day_start = db::now_unix() - (db::now_unix() % 86400);
    let total: i64 = conn
        .query_row("SELECT COUNT(*) FROM clip_item", [], |r| r.get(0))
        .map_err(|e| e.to_string())?;
    let today: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM clip_item WHERE used_at >= ?1",
            rusqlite::params![day_start],
            |r| r.get(0),
        )
        .map_err(|e| e.to_string())?;
    let pinned: i64 = conn
        .query_row("SELECT COUNT(*) FROM clip_item WHERE pinned = 1", [], |r| {
            r.get(0)
        })
        .map_err(|e| e.to_string())?;
    let mut stmt = conn
        .prepare("SELECT kind, COUNT(*) FROM clip_item GROUP BY kind ORDER BY COUNT(*) DESC")
        .map_err(|e| e.to_string())?;
    let by_kind = stmt
        .query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?)))
        .map_err(|e| e.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| e.to_string())?;
    let mut stmt = conn
        .prepare(
            "SELECT source_app, COUNT(*) FROM clip_item
             WHERE source_app IS NOT NULL AND source_app != ''
             GROUP BY source_app ORDER BY COUNT(*) DESC LIMIT 5",
        )
        .map_err(|e| e.to_string())?;
    let top_sources = stmt
        .query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?)))
        .map_err(|e| e.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| e.to_string())?;
    Ok(ClipStats {
        total,
        today,
        pinned,
        by_kind,
        top_sources,
    })
}

/// Rich HTML captured at copy time (for the rendered preview overlay).
#[tauri::command]
fn get_item_rich(state: tauri::State<'_, AppState>, id: i64) -> Result<Option<String>, String> {
    let conn = state.conn.lock();
    conn.query_row(
        "SELECT rich_html FROM clip_item WHERE id = ?1",
        rusqlite::params![id],
        |r| r.get::<_, Option<String>>(0),
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn show_drawer(app: AppHandle) {
    open_drawer(&app);
}

#[tauri::command]
fn hide_window(window: tauri::Window) {
    let _ = window.hide();
    if window.label() == "drawer" {
        let _ = window.app_handle().emit("hide-drawer", ());
    }
}

/// Hide drawer + restore focus to the app that was frontmost before drawer opened
/// + synthesize ⌘V. Frontend should already have written the desired content to
/// the clipboard via plugin-clipboard-manager.
#[tauri::command]
fn paste_back(app: AppHandle) -> Result<bool, String> {
    if let Some(win) = app.get_webview_window("drawer") {
        let _ = win.hide();
        let _ = app.emit("hide-drawer", ());
    }
    if let Some(win) = app.get_webview_window("tray-popover") {
        let _ = win.hide();
    }
    #[cfg(target_os = "macos")]
    {
        let (tx, rx) = std::sync::mpsc::channel();
        let _ = app.run_on_main_thread(move || {
            let mtm = unsafe { objc2::MainThreadMarker::new_unchecked() };
            let ok = paste::paste_back(mtm);
            let _ = tx.send(ok);
        });
        Ok(rx.recv().unwrap_or(false))
    }
    #[cfg(not(target_os = "macos"))]
    {
        Ok(paste_native::paste_back())
    }
}

/// One-call paste: read item from DB, write the right pasteboard types
/// (plain text + RTF/HTML for rich text; image for image; etc.), then
/// hide drawer + restore focus + synth ⌘V. Replaces JS-side writeText/writeImage.
#[tauri::command]
fn paste_item(state: tauri::State<'_, AppState>, app: AppHandle, id: i64) -> Result<bool, String> {
    let full = {
        let conn = state.conn.lock();
        db::get_full(&conn, id).map_err(|e| e.to_string())?
    };

    #[cfg(target_os = "macos")]
    {
        match full.kind.as_str() {
            "image" => {
                if let Some(png) = full.image_blob.as_deref() {
                    write_image_pasteboard(png);
                }
            }
            _ => {
                richtext::write_rich(
                    &full.content,
                    full.rich_html.as_deref(),
                    full.rich_rtf.as_deref(),
                );
            }
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        // Windows/Linux 用 arboard 落剪切板:文本直接写,图片把 PNG 解回 RGBA。
        // 没有这一步,回车"粘贴"就只是关窗口。
        write_clipboard_native(&full)?;
    }

    // Bump usage and trigger paste.
    {
        let conn = state.conn.lock();
        let _ = db::touch_item(&conn, id);
    }
    paste_back(app)
}

#[cfg(not(target_os = "macos"))]
fn write_clipboard_native(full: &db::FullItem) -> Result<(), String> {
    use arboard::{Clipboard, ImageData};
    let mut cb = Clipboard::new().map_err(|e| e.to_string())?;
    if full.kind == "image" {
        if let Some(png) = full.image_blob.as_deref() {
            let (w, h, rgba) = decode_png_rgba(png)?;
            cb.set_image(ImageData {
                width: w,
                height: h,
                bytes: std::borrow::Cow::Owned(rgba),
            })
            .map_err(|e| e.to_string())?;
        }
    } else {
        cb.set_text(&full.content).map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn decode_png_rgba(png: &[u8]) -> Result<(usize, usize, Vec<u8>), String> {
    use std::io::Cursor;
    let decoder = png::Decoder::new(Cursor::new(png));
    let mut reader = decoder.read_info().map_err(|e| e.to_string())?;
    let mut buf = vec![0u8; reader.output_buffer_size()];
    let info = reader.next_frame(&mut buf).map_err(|e| e.to_string())?;
    buf.truncate(info.buffer_size());
    Ok((info.width as usize, info.height as usize, buf))
}

#[cfg(target_os = "macos")]
fn write_image_pasteboard(png: &[u8]) {
    use objc2_app_kit::NSPasteboard;
    use objc2_foundation::{NSData, NSString};
    let pb = NSPasteboard::generalPasteboard();
    pb.clearContents();
    let data = NSData::with_bytes(png);
    pb.setData_forType(Some(&data), &NSString::from_str("public.png"));
}

#[tauri::command]
fn open_settings(app: AppHandle) {
    if let Some(win) = app.get_webview_window("settings") {
        let _ = win.show();
        let _ = win.set_focus();
        let _ = app.emit_to("settings", "settings-open", ());
    }
}

#[tauri::command]
fn check_accessibility() -> bool {
    #[cfg(target_os = "macos")]
    {
        paste::is_accessibility_trusted()
    }
    #[cfg(not(target_os = "macos"))]
    {
        true
    }
}

#[tauri::command]
fn request_accessibility() -> bool {
    #[cfg(target_os = "macos")]
    {
        paste::ensure_accessibility_trust()
    }
    #[cfg(not(target_os = "macos"))]
    {
        true
    }
}

#[tauri::command]
fn open_accessibility_settings() {
    #[cfg(target_os = "macos")]
    {
        let _ = std::process::Command::new("open")
            .arg("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
            .spawn();
    }
}

#[tauri::command]
fn app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[derive(serde::Serialize)]
struct Hotkeys {
    drawer: String,
    screenshot: String,
    clothesline: String,
    /// false when the OS refused the combo (taken by another app) — the
    /// settings panel shows a warning instead of a dead key
    screenshot_registered: bool,
    clothesline_registered: bool,
}

#[tauri::command]
fn get_hotkeys(app: AppHandle) -> Hotkeys {
    let state = app.try_state::<HotkeyState>();
    let configured = |key: &str, default: &str| load_setting(&app, key, default);
    Hotkeys {
        drawer: configured("drawer_hotkey", DEFAULT_DRAWER_HOTKEY),
        screenshot: configured("screenshot_hotkey", DEFAULT_SCREENSHOT_HOTKEY),
        clothesline: configured("clothesline_hotkey", DEFAULT_CLOTHESLINE_HOTKEY),
        screenshot_registered: state
            .as_ref()
            .map(|s| s.screenshot.lock().is_some())
            .unwrap_or(false),
        clothesline_registered: state
            .as_ref()
            .map(|s| s.clothesline.lock().is_some())
            .unwrap_or(false),
    }
}

/// Rebind one hotkey kind ("drawer" | "screenshot" | "clothesline").
/// Registers the new combo first, rolls back to the old one on failure.
#[tauri::command]
fn set_hotkey(app: AppHandle, kind: String, value: String) -> Result<(), String> {
    if !HOTKEY_KINDS.contains(&kind.as_str()) {
        return Err(format!("未知热键类型: {kind}"));
    }
    let new = parse_hotkey(&value).ok_or_else(|| format!("无法解析快捷键: {value}"))?;
    let state = app
        .try_state::<HotkeyState>()
        .ok_or_else(|| "未初始化 HotkeyState".to_string())?;

    let old = match kind.as_str() {
        "screenshot" => *state.screenshot.lock(),
        "clothesline" => *state.clothesline.lock(),
        _ => Some(*state.drawer.lock()),
    };
    // begin_hotkey_capture may have already unregistered; unregister is idempotent here.
    if let Some(old) = old {
        let _ = app.global_shortcut().unregister(old);
    }
    if let Err(e) = app.global_shortcut().register(new) {
        if let Some(old) = old {
            let _ = app.global_shortcut().register(old);
        }
        return Err(format!("注册失败: {e}"));
    }
    match kind.as_str() {
        "screenshot" => *state.screenshot.lock() = Some(new),
        "clothesline" => *state.clothesline.lock() = Some(new),
        _ => *state.drawer.lock() = new,
    }
    save_setting(&app, hotkey_settings_key(&kind), &value)?;
    // keep the tray tooltip in sync with the combos that now actually fire
    if let Some(tray) = app.tray_by_id("main") {
        let _ = tray.set_tooltip(Some(format!(
            "贴贴 — {} 唤起剪切板 · {} 晾衣架",
            hotkey_to_accel(&load_setting(&app, "drawer_hotkey", DEFAULT_DRAWER_HOTKEY)),
            hotkey_to_accel(&load_setting(
                &app,
                "clothesline_hotkey",
                DEFAULT_CLOTHESLINE_HOTKEY,
            ))
        )));
    }
    Ok(())
}

/// Pause the given hotkey so the user can press its current value during
/// capture without the OS intercepting it.
#[tauri::command]
fn begin_hotkey_capture(app: AppHandle, kind: String) -> Result<(), String> {
    let state = app
        .try_state::<HotkeyState>()
        .ok_or_else(|| "未初始化 HotkeyState".to_string())?;
    let cur = match kind.as_str() {
        "screenshot" => *state.screenshot.lock(),
        "clothesline" => *state.clothesline.lock(),
        _ => Some(*state.drawer.lock()),
    };
    if let Some(cur) = cur {
        let _ = app.global_shortcut().unregister(cur);
    }
    Ok(())
}

/// Re-register the previous hotkey — used when the user cancels capture
/// without choosing a new combo.
#[tauri::command]
fn cancel_hotkey_capture(app: AppHandle, kind: String) -> Result<(), String> {
    let state = app
        .try_state::<HotkeyState>()
        .ok_or_else(|| "未初始化 HotkeyState".to_string())?;
    let cur = match kind.as_str() {
        "screenshot" => *state.screenshot.lock(),
        "clothesline" => *state.clothesline.lock(),
        _ => Some(*state.drawer.lock()),
    };
    if let Some(cur) = cur {
        let _ = app.global_shortcut().register(cur);
    }
    Ok(())
}

#[tauri::command]
fn screenshot() {
    trigger_screenshot();
}

#[tauri::command]
fn quit_app(app: AppHandle) {
    app.exit(0);
}

// ─────────────────────── backup export / import ───────────────────────

/// Dump folders + memos + clip items to Documents/tietie-backup-<ts>.json.
/// Returns the file path written (shown in the settings panel).
#[tauri::command]
fn export_backup(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<String, String> {
    let bak = {
        let conn = state.conn.lock();
        db::dump_backup(&conn).map_err(|e| e.to_string())?
    };
    let dir = app
        .path()
        .document_dir()
        .or_else(|_| app.path().app_local_data_dir())
        .map_err(|e| e.to_string())?;
    let name = format!("tietie-backup-{}.json", time_fmt(db::now_unix()));
    let path = dir.join(name);
    let body = serde_json::to_string(&bak).map_err(|e| e.to_string())?;
    std::fs::write(&path, body).map_err(|e| e.to_string())?;
    // remember when the last backup left this machine (direction 63)
    let _ = save_setting(&app, "last_backup_at", &db::now_unix().to_string());
    Ok(path.to_string_lossy().into_owned())
}

/// Unix ts of the last successful backup export (0 = never) — the settings
/// page turns this into a stale-backup banner after 7 days.
#[tauri::command]
fn last_backup_at(app: AppHandle) -> i64 {
    load_setting(&app, "last_backup_at", "0")
        .parse::<i64>()
        .unwrap_or(0)
}

/// Merge the most recent backup file in Documents back into the database.
/// (A full file-picker needs the dialog plugin; scanning Documents for
/// tietie-backup-*.json keeps this dependency-free — pick newest.)
#[tauri::command]
fn import_backup(app: AppHandle, state: tauri::State<'_, AppState>) -> Result<String, String> {
    let dir = app
        .path()
        .document_dir()
        .or_else(|_| app.path().app_local_data_dir())
        .map_err(|e| e.to_string())?;
    let mut newest: Option<(i64, std::path::PathBuf)> = None;
    let entries = std::fs::read_dir(&dir).map_err(|e| e.to_string())?;
    for e in entries.flatten() {
        let name = e.file_name().to_string_lossy().into_owned();
        if let Some(ts) = name
            .strip_prefix("tietie-backup-")
            .and_then(|s| s.strip_suffix(".json"))
            // filename is yyyymmdd-hhmmss — drop the dash to compare as one int
            .and_then(|s| s.replace('-', "").parse::<i64>().ok())
        {
            if newest.as_ref().map(|(t, _)| ts > *t).unwrap_or(true) {
                newest = Some((ts, e.path()));
            }
        }
    }
    let (_, path) = newest.ok_or_else(|| "Documents 里没有 tietie-backup-*.json".to_string())?;
    let body = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let bak: db::BackupV1 =
        serde_json::from_str(&body).map_err(|e| format!("备份文件无效: {e}"))?;
    if bak.version != 1 {
        return Err(format!("不支持的备份版本: {}", bak.version));
    }
    let stats = {
        let conn = state.conn.lock();
        db::restore_backup(&conn, &bak).map_err(|e| e.to_string())?
    };
    let _ = app.emit("clipboard-changed", ());
    let _ = app.emit_to("clothesline", "memos-changed", ());
    Ok(format!(
        "已从 {} 恢复：条目 +{}/{}，文件夹 +{}/{}，便签 +{}/{}",
        path.file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default(),
        stats.items,
        bak.items.len(),
        stats.folders,
        bak.folders.len(),
        stats.memos,
        bak.memos.len(),
    ))
}

/// yyyymmdd-hhmmss for backup filenames.
fn time_fmt(unix: i64) -> String {
    let secs = unix;
    let days = secs / 86400;
    let rem = secs % 86400;
    let (h, mi, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
    // civil-from-days (Howard Hinnant's algorithm)
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z.rem_euclid(146097);
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    format!("{y:04}{m:02}{d:02}-{h:02}{mi:02}{s:02}")
}

// ─────────────────────── retention preference ───────────────────────

// ─────────────────────── source-app blacklist ───────────────────────

/// Apps whose clipboard writes are ignored (e.g. password managers).
/// Stored as a comma-separated list in settings.json; case-insensitive.
fn load_source_blacklist<R: Runtime>(app: &AppHandle<R>) -> Vec<String> {
    load_setting(app, "source_blacklist", "")
        .split(',')
        .map(|s| s.trim().to_lowercase())
        .filter(|s| !s.is_empty())
        .collect()
}

pub(crate) fn source_blacked<R: Runtime>(app: &AppHandle<R>, name: &Option<String>) -> bool {
    match name {
        Some(n) => load_source_blacklist(app)
            .iter()
            .any(|b| n.to_lowercase() == *b),
        None => false,
    }
}

#[tauri::command]
fn get_source_blacklist(app: AppHandle) -> Vec<String> {
    load_source_blacklist(&app)
}

/// Full replace with the given list.
#[tauri::command]
fn set_source_blacklist(app: AppHandle, apps: Vec<String>) -> Result<(), String> {
    let cleaned: Vec<String> = apps
        .into_iter()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();
    save_setting(&app, "source_blacklist", &cleaned.join(","))
}

/// History row cap (200 / 500 / 1000 / 3000 unpinned items).
#[tauri::command]
fn max_history(app: AppHandle) -> i64 {
    load_setting(&app, "max_history", "500")
        .parse()
        .unwrap_or(500)
}

#[tauri::command]
fn set_max_history(app: AppHandle, value: i64) -> Result<(), String> {
    if ![200, 500, 1000, 3000].contains(&value) {
        return Err(format!("无效的条目上限: {value}"));
    }
    save_setting(&app, "max_history", &value.to_string())
}

/// Days an unpinned item survives (7 / 30 / 0 = forever).
#[tauri::command]
fn retention_days(app: AppHandle) -> i64 {
    load_setting(&app, "retention_days", "0")
        .parse()
        .unwrap_or(0)
}

#[tauri::command]
fn set_retention_days(app: AppHandle, days: i64) -> Result<(), String> {
    if ![0, 7, 30].contains(&days) {
        return Err(format!("无效的保留天数: {days}"));
    }
    save_setting(&app, "retention_days", &days.to_string())
}

// ─────────────────────── dedupe preference ───────────────────────

#[tauri::command]
fn dedupe_history(state: tauri::State<'_, AppState>) -> bool {
    state.dedupe.load(std::sync::atomic::Ordering::Relaxed)
}

#[tauri::command]
fn set_dedupe_history(
    app: AppHandle,
    state: tauri::State<'_, AppState>,
    enabled: bool,
) -> Result<(), String> {
    state
        .dedupe
        .store(enabled, std::sync::atomic::Ordering::Relaxed);
    save_setting(
        &app,
        "dedupe_history",
        if enabled { "true" } else { "false" },
    )
}

// ─────────────────────── wayland session notice ───────────────────────

/// True on a Wayland desktop session (Linux) — synthetic keyboard events
/// are forbidden there, so auto-paste falls back to copy-only. The UI
/// surfaces this so users don't wonder why Enter only copies.
#[cfg(all(unix, not(target_os = "macos")))]
fn is_wayland_session() -> bool {
    std::env::var_os("WAYLAND_DISPLAY").is_some()
}

#[cfg(not(all(unix, not(target_os = "macos"))))]
fn is_wayland_session() -> bool {
    false
}

#[tauri::command]
fn wayland_session() -> bool {
    is_wayland_session()
}

// ─────────────────────────── autostart ───────────────────────────
#[tauri::command]
fn autostart_enabled(app: AppHandle) -> bool {
    use tauri_plugin_autostart::ManagerExt;
    app.autolaunch().is_enabled().unwrap_or(false)
}

#[tauri::command]
fn set_autostart(app: AppHandle, enabled: bool) -> Result<(), String> {
    use tauri_plugin_autostart::ManagerExt;
    let autolaunch = app.autolaunch();
    if enabled {
        autolaunch.enable().map_err(|e| e.to_string())
    } else {
        autolaunch.disable().map_err(|e| e.to_string())
    }
}

/// Trigger a screenshot straight to clipboard.
/// - macOS: native interactive area select (`screencapture -i -c -x`).
/// - Windows: full virtual-screen capture via PowerShell GDI (no extra deps);
///   the clipboard poller picks the bitmap up as a new image item.
/// - Linux: shell out to whatever screenshot tool the desktop has, then
///   push the PNG to the X11 clipboard with xclip.
fn trigger_screenshot() {
    #[cfg(target_os = "macos")]
    {
        // -i: interactive area select; -c: to clipboard; -x: silent (no shutter sound)
        let _ = std::process::Command::new("/usr/sbin/screencapture")
            .args(["-i", "-c", "-x"])
            .spawn();
    }
    #[cfg(windows)]
    {
        // -STA is required for the WinForms clipboard; VirtualScreen covers
        // every monitor in one bitmap.
        let script = "\
Add-Type -AssemblyName System.Windows.Forms; \
Add-Type -AssemblyName System.Drawing; \
$vs=[System.Windows.Forms.SystemInformation]::VirtualScreen; \
$bmp=New-Object System.Drawing.Bitmap $vs.Width,$vs.Height; \
$g=[System.Drawing.Graphics]::FromImage($bmp); \
$g.CopyFromScreen($vs.X,$vs.Y,0,0,$bmp.Size); \
$g.Dispose(); \
[System.Windows.Forms.Clipboard]::SetImage($bmp)";
        let _ = std::process::Command::new("powershell")
            .args([
                "-NoProfile",
                "-STA",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ])
            .spawn();
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let tmp = std::env::temp_dir().join("tietie-shot.png");
        let tmp_s = tmp.to_string_lossy().into_owned();
        let attempts: Vec<Vec<&str>> = vec![
            vec!["gnome-screenshot", "-c"],
            vec!["spectacle", "-b", "-c", "-n"],
            vec!["maim", "-u", tmp_s.as_str()],
            vec!["scrot", "-u", "-o", tmp_s.as_str()],
            vec!["import", "-window", "root", tmp_s.as_str()],
        ];
        let mut captured = false;
        for a in &attempts {
            if let Ok(st) = std::process::Command::new(a[0]).args(&a[1..]).status() {
                if st.success() {
                    captured = true;
                    break;
                }
            }
        }
        if captured && tmp.exists() {
            let _ = std::process::Command::new("xclip")
                .args(["-selection", "clipboard", "-t", "image/png", "-i"])
                .arg(&tmp)
                .status();
        } else {
            log::warn!(
                "[screenshot] 未找到可用的截图工具(gnome-screenshot/spectacle/maim/scrot/import)"
            );
        }
    }
}
