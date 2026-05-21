//! Auto-paste support: track prev frontmost app, restore focus, synth ⌘V.
//!
//! Without this, tietie only writes to clipboard — the user has to manually
//! ⌘V into their previous app. With this, tietie behaves like Paste/Maccy
//! and types the value into the previously-focused field.

use core_foundation::base::TCFType;
use core_foundation::boolean::CFBoolean;
use core_foundation::dictionary::CFDictionary;
use core_foundation::string::CFString;
use core_graphics::event::{CGEvent, CGEventFlags, CGEventTapLocation, CGKeyCode};
use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};
use objc2::MainThreadMarker;
use objc2_app_kit::{NSApplicationActivationOptions, NSRunningApplication, NSWorkspace};
use once_cell::sync::OnceCell;
use parking_lot::Mutex;
use std::time::Duration;

// AXIsProcessTrustedWithOptions is in ApplicationServices/HIServices.
// Declare it locally to avoid pulling another crate.
#[link(name = "ApplicationServices", kind = "framework")]
unsafe extern "C" {
    fn AXIsProcessTrustedWithOptions(options: core_foundation::dictionary::CFDictionaryRef)
        -> bool;
    fn AXIsProcessTrusted() -> bool;
}

/// Pop the macOS Accessibility-permission dialog if tietie isn't trusted yet.
/// Returns true if currently trusted.
pub fn ensure_accessibility_trust() -> bool {
    let key = CFString::from_static_string("AXTrustedCheckOptionPrompt");
    let val = CFBoolean::true_value();
    let opts = CFDictionary::from_CFType_pairs(&[(key, val)]);
    unsafe { AXIsProcessTrustedWithOptions(opts.as_concrete_TypeRef()) }
}

/// Silent check (no system prompt). Use for UI status indicators.
pub fn is_accessibility_trusted() -> bool {
    unsafe { AXIsProcessTrusted() }
}

/// PID of the app that was frontmost just before tietie's drawer was shown.
static PREV_APP_PID: OnceCell<Mutex<Option<i32>>> = OnceCell::new();

fn slot() -> &'static Mutex<Option<i32>> {
    PREV_APP_PID.get_or_init(|| Mutex::new(None))
}

/// Capture the currently frontmost app. Call this just before showing the drawer.
pub fn snapshot_frontmost(mtm: MainThreadMarker) {
    let ws = NSWorkspace::sharedWorkspace();
    let app = ws.frontmostApplication();
    let pid = app.as_ref().map(|a| a.processIdentifier());
    let name = app
        .as_ref()
        .and_then(|a| a.localizedName())
        .map(|s| s.to_string())
        .unwrap_or_else(|| "<unknown>".into());
    log::info!("[paste] snapshot frontmost: pid={pid:?} name={name}");
    *slot().lock() = pid;
    let _ = mtm; // proof of main thread
}

/// Restore focus to the previously-captured app and synthesize ⌘V.
/// Returns true if a focus restore + key event were attempted.
pub fn paste_back(mtm: MainThreadMarker) -> bool {
    // Pull pid (don't clear — multiple pastes may chain).
    let pid = *slot().lock();
    log::info!("[paste] paste_back: stored pid={pid:?}");

    if let Some(pid) = pid {
        if let Some(app) = NSRunningApplication::runningApplicationWithProcessIdentifier(pid) {
            let name = app
                .localizedName()
                .map(|s| s.to_string())
                .unwrap_or_else(|| "<?>".into());
            log::info!("[paste] activating {name} (pid {pid})");
            let activated = app.activateWithOptions(NSApplicationActivationOptions(0));
            log::info!("[paste] activate returned: {activated}");
        } else {
            log::warn!("[paste] no running app with pid {pid}");
        }
    } else {
        log::warn!("[paste] no stored frontmost pid");
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
    log::info!("[paste] posted ⌘V keyDown");

    let up = match CGEvent::new_keyboard_event(source, VK_V, false) {
        Ok(e) => e,
        Err(_) => return false,
    };
    up.set_flags(CGEventFlags::CGEventFlagCommand);
    up.post(CGEventTapLocation::HID);
    log::info!("[paste] posted ⌘V keyUp");

    true
}
