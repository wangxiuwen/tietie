//! Windows taskbar jump list: right-click the taskbar icon → 最近复制 quick
//! paste. Round 2 of this feature — the fix that made CommitList land: the
//! AUMID passed to ICustomDestinationList::SetAppID must equal the
//! AppUserModel_ID property of the window owning the taskbar button. Tauri
//! leaves that property unset, so the system derives an unpredictable
//! default; we pin it explicitly (process + every window) to our identifier.

use parking_lot::Mutex;
use tauri::{AppHandle, Manager};
use windows::core::{Interface, PCWSTR};
use windows::Win32::Foundation::{HWND, RPC_E_CHANGED_MODE};
use windows::Win32::System::Com::{
    CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED,
};
use windows::Win32::UI::Shell::Common::{IObjectArray, IObjectCollection};
use windows::Win32::UI::Shell::PropertiesSystem::{
    IPropertyStore, SHGetPropertyStoreForWindow, PROPERTYKEY,
};
use windows::Win32::UI::Shell::{
    DestinationList, EnumerableObjectCollection, ICustomDestinationList, IShellLinkW,
    SetCurrentProcessExplicitAppUserModelID, ShellLink,
};

use crate::AppState;

/// Stable AppUserModelID shared by process, windows, and the jump list.
const AUMID: &str = "com.wangxiuwen.tietie";
const JUMP_ITEMS: i64 = 5;

/// PKEY_AppUserModel_ID from propkey.h (not exported by the windows crate).
const PKEY_APPUSERMODEL_ID: PROPERTYKEY = PROPERTYKEY {
    fmtid: windows::core::GUID::from_values(
        0x9F4C2855,
        0x9F79,
        0x4B39,
        [0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3],
    ),
    pid: 5,
};

/// PKEY_Title — jump-list IShellLinks MUST carry their display name here;
/// SetDescription alone gets AppendCategory rejected with E_INVALIDARG.
const PKEY_TITLE: PROPERTYKEY = PROPERTYKEY {
    fmtid: windows::core::GUID::from_values(
        0xF29F85E0,
        0x4FF9,
        0x1068,
        [0xAB, 0x91, 0x08, 0x00, 0x2B, 0x27, 0xB3, 0xD9],
    ),
    pid: 2,
};

fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

/// Pin the AUMID on the process and all existing top-level windows so the
/// jump list has a definite owner to attach to. Call once at setup, before
/// the first refresh().
pub fn init_aumid(app: &AppHandle) {
    let w = wide(AUMID);
    unsafe {
        if let Err(e) = SetCurrentProcessExplicitAppUserModelID(PCWSTR(w.as_ptr())) {
            log::warn!("set process aumid: {e}");
        }
        for (_, win) in app.webview_windows() {
            if let Ok(hwnd) = win.hwnd() {
                // tauri links a different `windows` crate version: rebuild
                // the handle from the raw pointer against ours
                if let Err(e) = set_window_aumid(HWND(hwnd.0 as _)) {
                    log::warn!("set window aumid on {:?}: {e}", win.label());
                }
            }
        }
    }
    log::info!("aumid pinned to {AUMID}");
}

unsafe fn set_window_aumid(hwnd: HWND) -> windows::core::Result<()> {
    let store: IPropertyStore = SHGetPropertyStoreForWindow(hwnd)?;
    let pv = windows::core::PROPVARIANT::from(AUMID);
    store.SetValue(&PKEY_APPUSERMODEL_ID, &pv)
}

/// Newest text items for the jump list, drawer order (pinned first).
fn recent_rows(conn: &Mutex<rusqlite::Connection>) -> Option<Vec<(i64, String)>> {
    let c = conn.lock();
    let mut stmt = c
        .prepare(
            "SELECT id, COALESCE(NULLIF(preview,''), content) FROM clip_item \
             WHERE kind='text' AND length(COALESCE(NULLIF(preview,''), content)) > 0 \
             ORDER BY pinned DESC, used_at DESC LIMIT ?1",
        )
        .ok()?;
    let it = stmt
        .query_map([JUMP_ITEMS], |r| {
            Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?))
        })
        .ok()?;
    Some(it.filter_map(|x| x.ok()).collect())
}

/// Rebuild the 最近复制 category from the newest text items. Cheap (≤5 shell
/// links); called at startup and after every text insert from the poll thread.
pub fn refresh(conn: &Mutex<rusqlite::Connection>) {
    let rows = match recent_rows(conn) {
        Some(r) if !r.is_empty() => r,
        _ => return,
    };

    // The poll thread has no COM apartment; a balanced MTA init is enough
    // for these short-lived shell objects. If the thread already runs in an
    // incompatible apartment we still try — the main-thread call at setup
    // is the one that must succeed.
    let coinit = unsafe { CoInitializeEx(None, COINIT_MULTITHREADED) };
    if coinit.is_err() && coinit != RPC_E_CHANGED_MODE {
        log::warn!("jumplist coinit: {coinit:?}");
        return;
    }
    let built = unsafe { build(&rows) };
    if coinit.is_ok() {
        unsafe { CoUninitialize() };
    }
    match built {
        Ok(()) => log::info!("jumplist committed ({} items)", rows.len()),
        Err(e) => log::warn!("jumplist: {e}"),
    }
}

unsafe fn build(rows: &[(i64, String)]) -> Result<(), String> {
    let tag = |step: &'static str| move |e: windows::core::Error| format!("{step}: {e}");

    let list: ICustomDestinationList =
        CoCreateInstance(&DestinationList, None, CLSCTX_INPROC_SERVER).map_err(tag("create"))?;
    list.SetAppID(PCWSTR(wide(AUMID).as_ptr()))
        .map_err(tag("setappid"))?;
    let mut slots = 0u32;
    let _removed: IObjectArray = list.BeginList(&mut slots).map_err(tag("begin"))?;

    let coll: IObjectCollection =
        CoCreateInstance(&EnumerableObjectCollection, None, CLSCTX_INPROC_SERVER)
            .map_err(tag("collection"))?;
    let exe = std::env::current_exe()
        .map_err(|e| format!("exe path: {e}"))?
        .to_string_lossy()
        .into_owned();
    for (id, preview) in rows {
        let link: IShellLinkW =
            CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER).map_err(tag("link"))?;
        link.SetPath(PCWSTR(wide(&exe).as_ptr()))
            .map_err(tag("setpath"))?;
        link.SetArguments(PCWSTR(wide(&format!("--paste {id}")).as_ptr()))
            .map_err(tag("setargs"))?;
        let name: String = preview
            .replace(['\r', '\n'], " ")
            .chars()
            .take(60)
            .collect();
        link.SetDescription(PCWSTR(wide(&name).as_ptr()))
            .map_err(tag("setdesc"))?;
        link.SetIconLocation(PCWSTR(wide(&exe).as_ptr()), 0)
            .map_err(tag("seticon"))?;
        // required display name: PKEY_Title on the link's property store
        let ps: IPropertyStore = link.cast().map_err(tag("linkps"))?;
        ps.SetValue(
            &PKEY_TITLE,
            &windows::core::PROPVARIANT::from(name.as_str()),
        )
        .map_err(tag("settitle"))?;
        coll.AddObject(&link).map_err(tag("add"))?;
    }
    let arr: IObjectArray = coll.cast().map_err(tag("cast"))?;
    let cat = wide("最近复制");
    list.AppendCategory(PCWSTR(cat.as_ptr()), &arr)
        .map_err(tag("append"))?;
    list.CommitList().map_err(tag("commit"))?;
    Ok(())
}

/// Handle `--paste <id>` from a jump-list launch. The single-instance plugin
/// forwards args here on the already-running instance; the second process
/// exits by itself.
pub fn handle_launch_args(app: &AppHandle, args: &[String]) {
    let Some(pos) = args.iter().position(|a| a == "--paste") else {
        return;
    };
    let Some(id) = args.get(pos + 1).and_then(|s| s.parse::<i64>().ok()) else {
        return;
    };
    let app = app.clone();
    std::thread::spawn(move || {
        // let the taskbar click settle so focus returns to the user's app
        std::thread::sleep(std::time::Duration::from_millis(200));
        paste_id(&app, id);
    });
}

fn paste_id(app: &AppHandle, id: i64) {
    let state = app.state::<AppState>();
    let full = {
        let c = state.conn.lock();
        crate::db::get_full(&c, id)
    };
    let Ok(full) = full else {
        log::warn!("jump paste: item {id} gone");
        return;
    };
    if let Err(e) = crate::write_clipboard_native(&full) {
        log::warn!("jump paste clipboard: {e}");
        return;
    }
    {
        let c = state.conn.lock();
        let _ = crate::db::touch_item(&c, id);
    }
    log::info!("jump paste {id} ({})", full.kind);
    let _ = crate::paste_native::paste_back();
}
