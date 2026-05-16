//! Auto-paste support: track prev frontmost app, restore focus, synth ⌘V.
//!
//! Without this, tietie only writes to clipboard — the user has to manually
//! ⌘V into their previous app. With this, tietie behaves like Paste/Maccy
//! and types the value into the previously-focused field.

use core_graphics::event::{CGEvent, CGEventFlags, CGEventTapLocation, CGKeyCode};
use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};
use objc2::MainThreadMarker;
use objc2_app_kit::{NSApplicationActivationOptions, NSRunningApplication, NSWorkspace};
use once_cell::sync::OnceCell;
use parking_lot::Mutex;
use std::time::Duration;

/// PID of the app that was frontmost just before tietie's drawer was shown.
static PREV_APP_PID: OnceCell<Mutex<Option<i32>>> = OnceCell::new();

fn slot() -> &'static Mutex<Option<i32>> {
    PREV_APP_PID.get_or_init(|| Mutex::new(None))
}

/// Capture the currently frontmost app. Call this just before showing the drawer.
pub fn snapshot_frontmost(mtm: MainThreadMarker) {
    let ws = NSWorkspace::sharedWorkspace();
    let app = ws.frontmostApplication();
    let pid = app.map(|a| a.processIdentifier());
    *slot().lock() = pid;
    let _ = mtm; // proof of main thread
}

/// Restore focus to the previously-captured app and synthesize ⌘V.
/// Returns true if a focus restore + key event were attempted.
pub fn paste_back(mtm: MainThreadMarker) -> bool {
    // Pull pid (don't clear — multiple pastes may chain).
    let pid = *slot().lock();

    if let Some(pid) = pid {
        if let Some(app) = NSRunningApplication::runningApplicationWithProcessIdentifier(pid) {
            app.activateWithOptions(NSApplicationActivationOptions(0));
        }
    }
    let _ = mtm;

    // Give macOS a moment to bring the app forward before posting keys.
    std::thread::sleep(Duration::from_millis(60));

    // Synthesize ⌘V (V keycode = 9 on US QWERTY; macOS virtual keycode).
    const VK_V: CGKeyCode = 9;
    let source = match CGEventSource::new(CGEventSourceStateID::CombinedSessionState) {
        Ok(s) => s,
        Err(_) => return false,
    };
    let down = match CGEvent::new_keyboard_event(source.clone(), VK_V, true) {
        Ok(e) => e,
        Err(_) => return false,
    };
    down.set_flags(CGEventFlags::CGEventFlagCommand);
    down.post(CGEventTapLocation::HID);

    let up = match CGEvent::new_keyboard_event(source, VK_V, false) {
        Ok(e) => e,
        Err(_) => return false,
    };
    up.set_flags(CGEventFlags::CGEventFlagCommand);
    up.post(CGEventTapLocation::HID);

    true
}
