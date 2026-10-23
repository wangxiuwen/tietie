//! Non-macOS paste-back: remember the previous foreground window, restore
//! focus to it, then synthesize Ctrl+V.
//!
//! - Windows: GetForegroundWindow snapshot + SetForegroundWindow (with the
//!   AttachThreadInput trick, since our process is not foreground) + SendInput.
//! - Linux/X11: the WM usually returns focus to the previously active window
//!   once the drawer hides; we wait a beat, then try `xdotool`. Wayland blocks
//!   synthetic input entirely — we only copy and tell the user via log.

#[cfg(windows)]
mod imp {
    use once_cell::sync::OnceCell;
    use parking_lot::Mutex;
    use std::time::Duration;
    use windows::Win32::Foundation::{CloseHandle, HWND};
    use windows::Win32::System::Threading::{
        AttachThreadInput, GetCurrentThreadId, OpenProcess, QueryFullProcessImageNameW,
        PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP,
        VIRTUAL_KEY, VK_CONTROL, VK_V,
    };
    use windows::Win32::UI::WindowsAndMessaging::{
        GetForegroundWindow, GetWindowThreadProcessId, SetForegroundWindow,
    };

    static PREV_HWND: OnceCell<Mutex<isize>> = OnceCell::new();

    fn slot() -> &'static Mutex<isize> {
        PREV_HWND.get_or_init(|| Mutex::new(0))
    }

    /// Name of the foreground app's process ("Notepad", "Code"), without the
    /// .exe suffix — the poller records it as the likely copy source.
    pub fn frontmost_app_name() -> Option<String> {
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd.0.is_null() {
                return None;
            }
            let mut pid = 0u32;
            GetWindowThreadProcessId(hwnd, Some(&mut pid));
            if pid == 0 || pid == std::process::id() {
                return None;
            }
            let proc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid).ok()?;
            let mut buf = [0u16; 512];
            let mut len = buf.len() as u32;
            let queried = QueryFullProcessImageNameW(
                proc,
                PROCESS_NAME_WIN32,
                windows::core::PWSTR(buf.as_mut_ptr()),
                &mut len,
            );
            let _ = CloseHandle(proc);
            queried.ok()?;
            let full = String::from_utf16_lossy(&buf[..len as usize]);
            let name = full.rsplit(['\\', '/']).next()?.to_string();
            let name = name.strip_suffix(".exe").unwrap_or(&name).to_string();
            if name.is_empty() {
                None
            } else {
                Some(name)
            }
        }
    }

    pub fn snapshot_frontmost() {
        let hwnd = unsafe { GetForegroundWindow() };
        *slot().lock() = hwnd.0 as isize;
        log::info!("[paste] snapshot frontmost hwnd={:?}", hwnd.0 as isize);
    }

    pub fn paste_back() -> bool {
        let stored = *slot().lock();
        if stored != 0 {
            force_foreground(HWND(stored as _));
        }
        std::thread::sleep(Duration::from_millis(60));
        send_ctrl_v();
        true
    }

    fn force_foreground(hwnd: HWND) {
        if hwnd.0.is_null() {
            return;
        }
        unsafe {
            let fg = GetForegroundWindow();
            let fg_tid = if fg.0.is_null() {
                0
            } else {
                GetWindowThreadProcessId(fg, None)
            };
            let cur_tid = GetCurrentThreadId();
            let attached = fg_tid != 0 && fg_tid != cur_tid;
            if attached {
                let _ = AttachThreadInput(cur_tid, fg_tid, true);
            }
            let _ = SetForegroundWindow(hwnd);
            if attached {
                let _ = AttachThreadInput(cur_tid, fg_tid, false);
            }
        }
    }

    fn make_key(vk: VIRTUAL_KEY, flags: KEYBD_EVENT_FLAGS) -> INPUT {
        INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: vk,
                    wScan: 0,
                    dwFlags: flags,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        }
    }

    fn send_ctrl_v() {
        let inputs = [
            make_key(VK_CONTROL, KEYBD_EVENT_FLAGS(0)),
            make_key(VK_V, KEYBD_EVENT_FLAGS(0)),
            make_key(VK_V, KEYEVENTF_KEYUP),
            make_key(VK_CONTROL, KEYEVENTF_KEYUP),
        ];
        unsafe {
            let sent = SendInput(&inputs, std::mem::size_of::<INPUT>() as i32);
            log::info!("[paste] SendInput Ctrl+V sent={sent}");
        }
    }
}

#[cfg(all(unix, not(target_os = "macos")))]
mod imp {
    pub fn snapshot_frontmost() {
        // The WM hands focus back to the previously active window on hide;
        // nothing to record.
    }

    pub fn paste_back() -> bool {
        if std::env::var_os("WAYLAND_DISPLAY").is_some() {
            log::warn!("[paste] Wayland 会话,合成按键被禁用 — 内容已复制,请手动 Ctrl+V");
            return false;
        }
        match std::process::Command::new("xdotool")
            .args(["key", "--clearmodifiers", "ctrl+v"])
            .output()
        {
            Ok(out) if out.status.success() => true,
            other => {
                log::warn!(
                    "[paste] xdotool 不可用({other:?}) — 需要 X11 + xdotool,内容已复制,请手动 Ctrl+V"
                );
                false
            }
        }
    }

    /// Best-effort frontmost app on X11: xdotool → window pid → /proc/comm.
    /// Returns None on Wayland (no protocol for this) or without xdotool.
    pub fn frontmost_app_name() -> Option<String> {
        if std::env::var_os("WAYLAND_DISPLAY").is_some() {
            return None;
        }
        let out = std::process::Command::new("xdotool")
            .args(["getactivewindow", "getwindowpid"])
            .output()
            .ok()?;
        if !out.status.success() {
            return None;
        }
        let pid = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if pid.is_empty() {
            return None;
        }
        let comm = std::fs::read_to_string(format!("/proc/{pid}/comm")).ok()?;
        let name = comm.trim().to_string();
        if name.is_empty() {
            None
        } else {
            Some(name)
        }
    }
}

pub fn snapshot_frontmost() {
    imp::snapshot_frontmost();
}

pub fn paste_back() -> bool {
    imp::paste_back()
}

/// Name of the app that most likely produced the clipboard content (the
/// frontmost app at the moment the poller spots new content).
pub fn frontmost_app_name() -> Option<String> {
    imp::frontmost_app_name()
}
