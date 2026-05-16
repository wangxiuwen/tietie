mod clipboard;
mod db;

use parking_lot::Mutex;
use std::sync::Arc;
use tauri::{
    image::Image,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, Runtime, WebviewWindow,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

const DRAWER_HEIGHT: u32 = 360;
const TRAY_POPOVER_W: u32 = 320;
const TRAY_POPOVER_H: u32 = 460;

pub struct AppState {
    pub conn: Arc<Mutex<rusqlite::Connection>>,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ));

    #[cfg(desktop)]
    {
        builder = builder.plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state() == ShortcutState::Pressed {
                        let primary =
                            Shortcut::new(Some(Modifiers::SUPER | Modifiers::SHIFT), Code::KeyV);
                        if shortcut == &primary {
                            toggle_drawer(app);
                        }
                    }
                })
                .build(),
        );
    }

    builder
        .setup(|app| {
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

            // register hotkey
            #[cfg(desktop)]
            {
                let primary = Shortcut::new(Some(Modifiers::SUPER | Modifiers::SHIFT), Code::KeyV);
                if let Err(e) = app.global_shortcut().register(primary) {
                    log::warn!("register global shortcut failed: {e}");
                }
            }

            // configure drawer window
            if let Some(win) = app.get_webview_window("drawer") {
                position_drawer(&win);
                #[cfg(target_os = "macos")]
                let _ = win.set_visible_on_all_workspaces(true);
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
            list_slots,
            upsert_slot,
            delete_slot,
            launch_target,
            show_drawer,
            hide_window,
            open_settings,
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
    let show = MenuItem::with_id(app, "show", "显示剪切板", true, Some("CmdOrCtrl+Shift+V"))?;
    let stash = MenuItem::with_id(app, "stash", "打开收纳面板", true, None::<&str>)?;
    let sep = PredefinedMenuItem::separator(app)?;
    let about = MenuItem::with_id(app, "about", "关于贴贴", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &stash, &sep, &about, &quit])?;

    let _tray = TrayIconBuilder::with_id("main")
        .icon(tray_icon_image())
        .icon_as_template(true)
        .tooltip("贴贴 — ⌘⇧V 唤起剪切板")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => toggle_drawer(app),
            "stash" => toggle_tray_popover(app),
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

fn position_drawer<R: Runtime>(win: &WebviewWindow<R>) {
    if let Ok(Some(m)) = win.current_monitor() {
        let size = m.size();
        let scale = m.scale_factor();
        let target_w = size.width;
        let target_h = (DRAWER_HEIGHT as f64 * scale) as u32;
        let _ = win.set_size(PhysicalSize::new(target_w, target_h));
        let _ = win.set_position(PhysicalPosition::new(
            m.position().x,
            m.position().y + size.height as i32 - target_h as i32,
        ));
    }
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
fn list_slots(state: tauri::State<'_, AppState>) -> Result<Vec<db::LauncherSlot>, String> {
    let conn = state.conn.lock();
    db::list_slots(&conn).map_err(|e| e.to_string())
}

#[tauri::command]
fn upsert_slot(
    state: tauri::State<'_, AppState>,
    slot_index: i64,
    label: String,
    target: String,
    icon_path: Option<String>,
) -> Result<(), String> {
    let conn = state.conn.lock();
    db::upsert_slot(&conn, slot_index, &label, &target, icon_path.as_deref())
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_slot(state: tauri::State<'_, AppState>, slot_index: i64) -> Result<(), String> {
    let conn = state.conn.lock();
    db::delete_slot(&conn, slot_index).map_err(|e| e.to_string())
}

#[tauri::command]
fn launch_target(target: String) -> Result<(), String> {
    open::that(target).map_err(|e| e.to_string())
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

#[tauri::command]
fn open_settings(app: AppHandle) {
    // For MVP, settings opens the drawer with a settings event the UI can react to.
    let _ = app.emit("show-settings", ());
}

#[tauri::command]
fn quit_app(app: AppHandle) {
    app.exit(0);
}
