//! Windows-only global-hotkey fallback.
//!
//! The global-shortcut plugin delivers hotkeys through a hidden
//! "global_hotkey_app" window: win32k posts WM_HOTKEY there and tauri's main
//! loop pumps it into the plugin handler. On a wedged session that first hop
//! stops happening — the combos stay registered (OS still refuses the combo to
//! everyone else), physical and injected keys both reach low-level keyboard
//! hooks, yet no WM_HOTKEY is ever posted. This module installs a
//! WH_KEYBOARD_LL hook and, when it sees a configured combo, replays the
//! missed WM_HOTKEY into the hidden window itself. The replay walks the exact
//! same dispatch path as an OS-fired hotkey, so handler, state and tray all
//! behave identically. A short debounce in the plugin handler swallows the
//! duplicate if the OS path ever starts working again.

use std::sync::atomic::{AtomicIsize, Ordering};
use std::sync::OnceLock;

use parking_lot::Mutex;
use windows::Win32::Foundation::{BOOL, HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, DispatchMessageW, EnumWindows, GetClassNameW, GetMessageW,
    GetWindowThreadProcessId, PostMessageW, SetWindowsHookExW, UnhookWindowsHookEx, HOOKPROC,
    KBDLLHOOKSTRUCT, MSG, WH_KEYBOARD_LL, WM_HOTKEY,
};

// win32 RegisterHotKey modifier bits (winuser.h)
const MOD_SHIFT: u32 = 0x0004;
const MOD_CONTROL: u32 = 0x0002;
const MOD_ALT: u32 = 0x0001;
const MOD_WIN: u32 = 0x0008;

/// One live hotkey: (win32 modifier bits, virtual-key code, global-hotkey id).
pub type Combo = (u32, u32, u32);

struct Shared {
    combos: Mutex<Vec<Combo>>,
    /// hidden "global_hotkey_app" window of this process; 0 until located
    hwnd: AtomicIsize,
    /// keyboard state as seen by the hook (only the hook thread mutates)
    mods: Mutex<u32>,
    down: Mutex<Vec<u32>>,
}

static SHARED: OnceLock<Shared> = OnceLock::new();

fn shared() -> &'static Shared {
    SHARED.get_or_init(|| Shared {
        combos: Mutex::new(Vec::new()),
        hwnd: AtomicIsize::new(0),
        mods: Mutex::new(0),
        down: Mutex::new(Vec::new()),
    })
}

/// Replace the live combo table (called after every hotkey (re)registration).
pub fn set_combos(combos: Vec<Combo>) {
    log::info!("hotkey fallback combos: {combos:?}");
    *shared().combos.lock() = combos;
}

/// Install the hook on a dedicated thread and keep it alive for the process
/// lifetime. The thread's message loop is what lets the system deliver hook
/// callbacks, exactly as a message-only window's queue would.
pub fn start() {
    std::thread::spawn(|| {
        let hwnd = find_manager_window();
        if hwnd.0.is_null() {
            log::warn!("hotkey fallback: manager window not found, hook idle");
            return;
        }
        shared().hwnd.store(hwnd.0 as isize, Ordering::Relaxed);
        let proc: HOOKPROC = Some(hook_proc);
        let hook = unsafe { SetWindowsHookExW(WH_KEYBOARD_LL, proc, None, 0) };
        match hook {
            Ok(h) => {
                log::info!("hotkey fallback hook installed");
                // watchdog: the hook itself only bumps a counter, so this is
                // the place to observe whether callbacks actually arrive
                std::thread::spawn(|| {
                    let mut last = 0u32;
                    loop {
                        std::thread::sleep(std::time::Duration::from_secs(5));
                        let n = CB_COUNT.load(Ordering::Relaxed);
                        if n != last {
                            log::info!("hotkey fallback callbacks: {n}");
                            last = n;
                        }
                    }
                });
                let mut msg = MSG::default();
                unsafe {
                    // GetMessageW returns 0 on WM_QUIT / -1 on error — either
                    // way the hook thread (and with it the hook) ends.
                    while GetMessageW(&mut msg, None, 0, 0).as_bool() {
                        DispatchMessageW(&msg);
                    }
                }
                unsafe {
                    let _ = UnhookWindowsHookEx(h);
                }
                log::warn!("hotkey fallback hook loop exited");
            }
            Err(e) => log::warn!("hotkey fallback hook install failed: {e}"),
        }
    });
}

fn modifier_bit(vk: u32) -> Option<u32> {
    match vk {
        0x10 | 0xA0 | 0xA1 => Some(MOD_SHIFT), // VK_SHIFT / VK_LSHIFT / VK_RSHIFT
        0x11 | 0xA2 | 0xA3 => Some(MOD_CONTROL), // VK_CONTROL / L / R
        0x12 | 0xA4 | 0xA5 => Some(MOD_ALT),   // VK_MENU / L / R
        0x5B | 0x5C => Some(MOD_WIN),          // VK_LWIN / VK_RWIN
        _ => None,
    }
}

/// Callback invocations seen so far. LL hook callbacks must be fast — a slow
/// callback gets the hook silently removed by the system after a timeout — so
/// the hot path only bumps this counter; a watchdog thread does all logging.
static CB_COUNT: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);

unsafe extern "system" fn hook_proc(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code >= 0 {
        CB_COUNT.fetch_add(1, Ordering::Relaxed);
        let kb = &*(lparam.0 as *const KBDLLHOOKSTRUCT);
        let vk = kb.vkCode;
        let msg = wparam.0 as u32;
        const WM_KEYDOWN: u32 = 0x0100;
        const WM_KEYUP: u32 = 0x0101;
        const WM_SYSKEYDOWN: u32 = 0x0104;
        const WM_SYSKEYUP: u32 = 0x0105;
        if let Some(bit) = modifier_bit(vk) {
            let mut m = shared().mods.lock();
            if msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN {
                *m |= bit;
            } else if msg == WM_KEYUP || msg == WM_SYSKEYUP {
                *m &= !bit;
            }
        } else if msg == WM_KEYDOWN || msg == WM_SYSKEYDOWN {
            // auto-repeat re-delivers keydown without an intervening keyup
            let mut down = shared().down.lock();
            let first = !down.contains(&vk);
            if first {
                down.push(vk);
            }
            drop(down);
            if first {
                let mods = *shared().mods.lock();
                if let Some(id) = match_combo(mods, vk) {
                    fire(id, vk);
                }
            }
        } else if msg == WM_KEYUP || msg == WM_SYSKEYUP {
            shared().down.lock().retain(|&v| v != vk);
        }
    }
    CallNextHookEx(None, code, wparam, lparam)
}

fn match_combo(mods: u32, vk: u32) -> Option<u32> {
    shared()
        .combos
        .lock()
        .iter()
        .find(|(m, v, _)| *m == mods && *v == vk)
        .map(|&(_, _, id)| id)
}

/// Replay the hotkey as WM_HOTKEY into the plugin's hidden window, mirroring
/// what win32k would have posted: wparam = hotkey id, HIWORD(lparam) = the
/// key's virtual-key code (the crate's release watcher reads it there).
fn fire(id: u32, vk: u32) {
    let raw = shared().hwnd.load(Ordering::Relaxed);
    if raw == 0 {
        return;
    }
    let hwnd = HWND(raw as *mut _);
    let lparam = LPARAM((vk as isize) << 16);
    let res = unsafe { PostMessageW(hwnd, WM_HOTKEY, WPARAM(id as usize), lparam) };
    match res {
        Ok(()) => log::info!("hotkey fallback: replayed id={id:#010x} vk={vk:#04x}"),
        Err(e) => log::warn!("hotkey fallback replay failed: {e}"),
    }
}

/// Locate this process's "global_hotkey_app" window (created by the
/// global-hotkey crate during plugin setup). A couple of retries cover a
/// slow cold start; giving up leaves the hook idle but harmless.
fn find_manager_window() -> HWND {
    let mut found: usize = 0;
    for _ in 0..10 {
        let lparam = LPARAM(&mut found as *mut usize as isize);
        unsafe {
            let _ = EnumWindows(Some(enum_proc), lparam);
        }
        if found != 0 {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(300));
    }
    HWND(found as *mut _)
}

unsafe extern "system" fn enum_proc(hwnd: HWND, lparam: LPARAM) -> BOOL {
    let mut pid = 0u32;
    GetWindowThreadProcessId(hwnd, Some(&mut pid));
    if pid != std::process::id() {
        return BOOL(1);
    }
    let mut buf = [0u16; 32];
    let n = GetClassNameW(hwnd, &mut buf);
    let class = String::from_utf16_lossy(&buf[..n.max(0) as usize]);
    if class == "global_hotkey_app" {
        unsafe { *(lparam.0 as *mut usize) = hwnd.0 as usize };
        return BOOL(0); // stop enumeration
    }
    BOOL(1)
}
