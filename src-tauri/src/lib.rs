mod clipboard;
mod db;
#[cfg(target_os = "macos")]
mod paste;
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

const DRAWER_HEIGHT: u32 = 380;
const TRAY_POPOVER_W: u32 = 320;
const TRAY_POPOVER_H: u32 = 460;
const DEFAULT_DRAWER_HOTKEY: &str = "Super+Shift+KeyV";
const SCREENSHOT_HOTKEY: &str = "Control+Alt+Digit4";

pub struct AppState {
    pub conn: Arc<Mutex<rusqlite::Connection>>,
}

pub struct HotkeyState {
    pub drawer: Mutex<Shortcut>,
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
    Some(Shortcut::new(if mods.is_empty() { None } else { Some(mods) }, c))
}

fn settings_path<R: Runtime>(app: &AppHandle<R>) -> std::path::PathBuf {
    app.path()
        .app_local_data_dir()
        .expect("no app local data dir")
        .join("settings.json")
}

fn load_drawer_hotkey<R: Runtime>(app: &AppHandle<R>) -> String {
    let path = settings_path(app);
    std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.get("drawer_hotkey").and_then(|x| x.as_str()).map(String::from))
        .unwrap_or_else(|| DEFAULT_DRAWER_HOTKEY.to_string())
}

fn save_drawer_hotkey<R: Runtime>(app: &AppHandle<R>, value: &str) -> Result<(), String> {
    let path = settings_path(app);
    if let Some(p) = path.parent() {
        let _ = std::fs::create_dir_all(p);
    }
    let mut v: serde_json::Value = std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| serde_json::json!({}));
    v["drawer_hotkey"] = serde_json::Value::String(value.into());
    let body = serde_json::to_string_pretty(&v).map_err(|e| e.to_string())?;
    std::fs::write(&path, body).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    let mut builder = tauri::Builder::default()
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
                    let shot = parse_hotkey(SCREENSHOT_HOTKEY);
                    if shot.as_ref() == Some(shortcut) {
                        trigger_screenshot();
                        return;
                    }
                    if let Some(state) = app.try_state::<HotkeyState>() {
                        if &*state.drawer.lock() == shortcut {
                            toggle_drawer(app);
                        }
                    }
                })
                .build(),
        );
    }

    builder
        .setup(|app| {
            // Hide from Dock + Cmd-Tab — clipboard utility lives in the tray,
            // not in the foreground app list. Tray icon + ⌘⇧V hotkey are the
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

            app.manage(AppState { conn: conn.clone() });

            // start clipboard polling
            clipboard::start_polling(app.handle().clone(), conn);

            // create tray
            #[cfg(desktop)]
            create_tray(app.handle())?;

            // register hotkeys (drawer is user-configurable; screenshot is fixed)
            #[cfg(desktop)]
            {
                let drawer_str = load_drawer_hotkey(&app.handle());
                let drawer = parse_hotkey(&drawer_str)
                    .or_else(|| parse_hotkey(DEFAULT_DRAWER_HOTKEY))
                    .expect("DEFAULT_DRAWER_HOTKEY must parse");
                app.manage(HotkeyState {
                    drawer: Mutex::new(drawer),
                });
                if let Err(e) = app.global_shortcut().register(drawer) {
                    log::warn!("register drawer hotkey failed: {e}");
                }
                if let Some(shot) = parse_hotkey(SCREENSHOT_HOTKEY) {
                    if let Err(e) = app.global_shortcut().register(shot) {
                        log::warn!("register screenshot hotkey failed: {e}");
                    }
                }
            }

            // configure drawer window
            if let Some(win) = app.get_webview_window("drawer") {
                position_drawer(&win);
                #[cfg(target_os = "macos")]
                {
                    let _ = win.set_visible_on_all_workspaces(true);
                    round_drawer_window_corners(&win, 22.0);
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
            get_item_image,
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
            get_drawer_hotkey,
            set_drawer_hotkey,
            begin_hotkey_capture,
            cancel_hotkey_capture,
            quit_app,
        ])
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. })
                && (window.label() == "drawer" || window.label() == "tray-popover")
            {
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(desktop)]
fn create_tray<R: Runtime>(app: &AppHandle<R>) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "唤起剪切板", true, Some("CmdOrCtrl+Shift+V"))?;
    let recent = MenuItem::with_id(app, "recent", "查看最近剪切板", true, None::<&str>)?;
    let shot = MenuItem::with_id(
        app,
        "screenshot",
        "截图到剪切板",
        true,
        Some("CmdOrCtrl+Ctrl+4"),
    )?;
    let sep = PredefinedMenuItem::separator(app)?;
    let about = MenuItem::with_id(app, "about", "关于贴贴", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &recent, &shot, &sep, &about, &quit])?;

    let _tray = TrayIconBuilder::with_id("main")
        .icon(tray_icon_image())
        .icon_as_template(true)
        .tooltip("贴贴 — ⌘⇧V 唤起剪切板")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => toggle_drawer(app),
            "recent" => toggle_tray_popover(app),
            "screenshot" => trigger_screenshot(),
            "about" => {
                let _ = app.emit("show-about", ());
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

fn tray_icon_image() -> Image<'static> {
    // 16x16 monochrome clipboard icon (RGBA)
    const W: u32 = 16;
    const H: u32 = 16;
    let mut buf = vec![0u8; (W * H * 4) as usize];
    // simple clipboard glyph: outline rectangle with clip top
    let on = [255, 255, 255, 255];
    let put = |buf: &mut [u8], x: u32, y: u32, c: [u8; 4]| {
        if x < W && y < H {
            let i = ((y * W + x) * 4) as usize;
            buf[i..i + 4].copy_from_slice(&c);
        }
    };
    // body 3..12 horizontally, 3..14 vertically
    for y in 3..14 {
        for x in 3..13 {
            let edge = x == 3 || x == 12 || y == 3 || y == 13;
            if edge {
                put(&mut buf, x, y, on);
            }
        }
    }
    // clip
    for x in 6..10 {
        put(&mut buf, x, 2, on);
        put(&mut buf, x, 4, on);
    }
    put(&mut buf, 5, 3, on);
    put(&mut buf, 10, 3, on);
    Image::new_owned(buf, W, H)
}

/// Round only the top corners of the drawer NSWindow content via a
/// CAShapeLayer mask. A `mask` layer clips every descendant (including the
/// out-of-process WKWebView), unlike `cornerRadius` + `masksToBounds` which
/// can leak past out-of-process compositor sublayers and leave a square
/// white wedge at the corners.
#[cfg(target_os = "macos")]
fn round_drawer_window_corners<R: Runtime>(win: &WebviewWindow<R>, radius: f64) {
    use objc2::msg_send;
    use objc2::runtime::AnyObject;
    use std::ffi::c_void;

    #[repr(C)]
    struct CGSize {
        width: f64,
        height: f64,
    }
    #[repr(C)]
    struct CGPoint {
        x: f64,
        y: f64,
    }
    #[repr(C)]
    struct CGRect {
        origin: CGPoint,
        size: CGSize,
    }

    #[link(name = "CoreGraphics", kind = "framework")]
    extern "C" {
        fn CGPathCreateMutable() -> *mut c_void;
        fn CGPathMoveToPoint(path: *mut c_void, m: *const c_void, x: f64, y: f64);
        fn CGPathAddLineToPoint(path: *mut c_void, m: *const c_void, x: f64, y: f64);
        fn CGPathAddQuadCurveToPoint(
            path: *mut c_void,
            m: *const c_void,
            cpx: f64,
            cpy: f64,
            x: f64,
            y: f64,
        );
        fn CGPathCloseSubpath(path: *mut c_void);
        fn CGPathRelease(path: *const c_void);
    }

    let scale = win.scale_factor().unwrap_or(1.0);
    let outer = match win.outer_size() {
        Ok(s) => s,
        Err(_) => return,
    };
    let w = outer.width as f64 / scale;
    let h = outer.height as f64 / scale;
    let r = radius.min(w / 2.0).min(h / 2.0);

    let Ok(ns_window_ptr) = win.ns_window() else {
        return;
    };
    if ns_window_ptr.is_null() {
        return;
    }
    unsafe {
        let ns_window = ns_window_ptr as *mut AnyObject;
        let content_view: *mut AnyObject = msg_send![ns_window, contentView];
        if content_view.is_null() {
            return;
        }
        let _: () = msg_send![content_view, setWantsLayer: true];
        let layer: *mut AnyObject = msg_send![content_view, layer];
        if layer.is_null() {
            return;
        }

        // Build path: rect with only top two corners rounded.
        // contentView layer uses bottom-left origin → "top" = MaxY = `h`.
        let path = CGPathCreateMutable();
        CGPathMoveToPoint(path, std::ptr::null(), 0.0, 0.0);
        CGPathAddLineToPoint(path, std::ptr::null(), 0.0, h - r);
        // Top-left corner: control at (0, h), end at (r, h)
        CGPathAddQuadCurveToPoint(path, std::ptr::null(), 0.0, h, r, h);
        CGPathAddLineToPoint(path, std::ptr::null(), w - r, h);
        // Top-right corner: control at (w, h), end at (w, h - r)
        CGPathAddQuadCurveToPoint(path, std::ptr::null(), w, h, w, h - r);
        CGPathAddLineToPoint(path, std::ptr::null(), w, 0.0);
        CGPathCloseSubpath(path);

        let shape_layer: *mut AnyObject =
            msg_send![objc2::class!(CAShapeLayer), new];
        let _: () = msg_send![shape_layer, setPath: path];
        let _: () = msg_send![layer, setMask: shape_layer];

        CGPathRelease(path);

        // Discard the no-longer-needed cornerRadius (from the previous strategy).
        let _: () = msg_send![layer, setCornerRadius: 0.0f64];
        let _: () = msg_send![layer, setMasksToBounds: false];

        // Suggest a CGRect type bind so the encoder sees a known shape — not
        // actually used, just keeping the structs above warning-quiet.
        let _ = std::mem::size_of::<CGRect>();
    }
}

fn position_drawer<R: Runtime>(win: &WebviewWindow<R>) {
    if let Ok(Some(m)) = win.current_monitor() {
        let size = m.size();
        let scale = m.scale_factor();
        let target_w = size.width;
        let target_h = (DRAWER_HEIGHT as f64 * scale) as u32;

        // dock_inset_px = points-of-dock × scale; 0 on non-mac
        let dock_inset_px = mac_dock_inset_px(scale);

        let _ = win.set_size(PhysicalSize::new(target_w, target_h));
        let _ = win.set_position(PhysicalPosition::new(
            m.position().x,
            m.position().y + size.height as i32 - target_h as i32 - dock_inset_px,
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

fn position_tray_popover<R: Runtime>(app: &AppHandle<R>, click: PhysicalPosition<f64>) {
    if let Some(win) = app.get_webview_window("tray-popover") {
        let scale = win.scale_factor().unwrap_or(1.0);
        let w = (TRAY_POPOVER_W as f64 * scale) as u32;
        let h = (TRAY_POPOVER_H as f64 * scale) as u32;
        let _ = win.set_size(PhysicalSize::new(w, h));
        let x = (click.x as i32) - (w as i32 / 2);
        // place just below tray (mac tray is at top)
        let y = (click.y as i32) + 8;
        let _ = win.set_position(PhysicalPosition::new(x.max(0), y.max(0)));
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
                position_drawer(&win);
                let _ = win.show();
                let _ = win.set_focus();
                #[cfg(target_os = "macos")]
                round_drawer_window_corners(&win, 22.0);
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

#[tauri::command]
fn show_drawer(app: AppHandle) {
    toggle_drawer(&app);
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
        Ok(false)
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
        let _ = &full;
    }

    // Bump usage and trigger paste.
    {
        let conn = state.conn.lock();
        let _ = db::touch_item(&conn, id);
    }
    paste_back(app)
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
    let _ = app.emit("show-settings", ());
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

#[tauri::command]
fn get_drawer_hotkey(app: AppHandle) -> String {
    load_drawer_hotkey(&app)
}

#[tauri::command]
fn set_drawer_hotkey(app: AppHandle, value: String) -> Result<(), String> {
    let new = parse_hotkey(&value).ok_or_else(|| format!("无法解析快捷键: {value}"))?;
    let state = app
        .try_state::<HotkeyState>()
        .ok_or_else(|| "未初始化 HotkeyState".to_string())?;
    let old = *state.drawer.lock();
    // begin_hotkey_capture may have already unregistered; unregister is idempotent in our use.
    let _ = app.global_shortcut().unregister(old);
    if let Err(e) = app.global_shortcut().register(new) {
        // try to restore old on failure
        let _ = app.global_shortcut().register(old);
        return Err(format!("注册失败: {e}"));
    }
    *state.drawer.lock() = new;
    save_drawer_hotkey(&app, &value)?;
    Ok(())
}

/// Pause the global drawer hotkey so the user can press its current value
/// during capture without the OS intercepting it (which would close the
/// drawer instead of letting the input field record the combo).
#[tauri::command]
fn begin_hotkey_capture(app: AppHandle) -> Result<(), String> {
    let state = app
        .try_state::<HotkeyState>()
        .ok_or_else(|| "未初始化 HotkeyState".to_string())?;
    let cur = *state.drawer.lock();
    let _ = app.global_shortcut().unregister(cur);
    Ok(())
}

/// Re-register the previous hotkey — used when the user cancels capture
/// without choosing a new combo.
#[tauri::command]
fn cancel_hotkey_capture(app: AppHandle) -> Result<(), String> {
    let state = app
        .try_state::<HotkeyState>()
        .ok_or_else(|| "未初始化 HotkeyState".to_string())?;
    let cur = *state.drawer.lock();
    let _ = app.global_shortcut().register(cur);
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

/// Spawn macOS native interactive area screenshot, sent straight to clipboard.
/// The clipboard polling thread will pick it up and store as a new image item.
fn trigger_screenshot() {
    #[cfg(target_os = "macos")]
    {
        // -i: interactive area select; -c: to clipboard; -x: silent (no shutter sound)
        let _ = std::process::Command::new("/usr/sbin/screencapture")
            .args(["-i", "-c", "-x"])
            .spawn();
    }
}
