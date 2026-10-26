use crate::db;
use arboard::{Clipboard, ImageData};
use base64::{engine::general_purpose, Engine as _};
use parking_lot::Mutex;
use sha2::{Digest, Sha256};
use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Emitter};

/// Poll backoff ladder: 600ms right after activity, easing to 2s while
/// the clipboard stays unchanged (saves CPU/battery on idle machines).
const POLL_BACKOFF_STEPS: [u64; 4] = [600, 1000, 1500, 2000];

#[cfg(not(target_os = "macos"))]
struct NoRich {
    html: Option<String>,
    rtf: Option<Vec<u8>>,
}

pub fn start_polling(
    app: AppHandle,
    conn: Arc<Mutex<rusqlite::Connection>>,
    dedupe: Arc<std::sync::atomic::AtomicBool>,
    capture_paused_until: Arc<std::sync::atomic::AtomicI64>,
    retention_days: i64,
    max_history: i64,
) {
    std::thread::spawn(move || {
        let mut clipboard = match Clipboard::new() {
            Ok(c) => c,
            Err(e) => {
                log::error!("clipboard init failed: {e}");
                return;
            }
        };
        let mut last_text_hash: Option<String> = None;
        let mut last_image_hash: Option<String> = None;
        let mut quiet_runs: u32 = 0;
        let mut last_reclaim_day: Option<String> = None;

        loop {
            let poll = POLL_BACKOFF_STEPS[(quiet_runs as usize).min(POLL_BACKOFF_STEPS.len() - 1)];
            std::thread::sleep(Duration::from_millis(poll));
            quiet_runs = quiet_runs.saturating_add(1);
            if (1..=POLL_BACKOFF_STEPS.len() as u32).contains(&quiet_runs) {
                log::info!(
                    "clipboard quiet {} rounds (last poll {}ms)",
                    quiet_runs,
                    poll
                );
            }

            // Nightly idle reclaim (direction 55): once per local day inside
            // the 02:00–05:00 window, drop expired items (per retention),
            // re-apply the history cap and truncate the WAL so the DB file
            // actually shrinks even when nothing was copied that day.
            let now = chrono::Local::now();
            use chrono::Timelike;
            let today = now.format("%Y-%m-%d").to_string();
            if should_night_reclaim(now.hour(), &today, &last_reclaim_day) {
                let today = now.format("%Y-%m-%d").to_string();
                let mut removed = 0usize;
                {
                    let c = conn.lock();
                    if let Ok(n) = db::trim_expired(&c, retention_days) {
                        removed = n;
                    }
                    let _ = db::trim_history(&c, max_history);
                    let _ = c.execute_batch("PRAGMA wal_checkpoint(TRUNCATE)");
                }
                log::info!("nightly reclaim: {removed} expired trimmed, wal truncated");
                last_reclaim_day = Some(today);
            }

            // capture pause gate (direction 67): while paused (password
            // manager scenario) track the hash so it doesn't leak in on
            // resume, but record nothing
            let paused_until = capture_paused_until.load(std::sync::atomic::Ordering::Relaxed);
            let paused = paused_until > db::now_unix();

            // Try text first
            if let Ok(text) = clipboard.get_text() {
                let hash = hash_str(&text);
                if Some(&hash) != last_text_hash.as_ref() && !text.is_empty() {
                    last_text_hash = Some(hash.clone());
                    last_image_hash = None;
                    quiet_runs = 0; // new content -> fast poll next round
                    if paused {
                        log::info!(
                            "capture paused ({}s left), skipping text",
                            paused_until - db::now_unix()
                        );
                        continue;
                    }
                    let (kind, preview) = classify_text(&text);
                    // record who copied it (frontmost app right now);
                    // blacklisted apps (password managers etc.) are ignored
                    let source = crate::frontmost_app_name(&app);
                    if crate::source_blacked(&app, &source) {
                        log::info!("source app blacklisted, skipping insert");
                        continue;
                    }

                    // Snapshot rich variants (HTML / RTF) from NSPasteboard if present.
                    #[cfg(target_os = "macos")]
                    let snap = crate::richtext::read_current();
                    #[cfg(not(target_os = "macos"))]
                    let snap = NoRich {
                        html: None,
                        rtf: None,
                    };

                    let item = db::InsertItem {
                        kind,
                        content: &text,
                        preview: &preview,
                        meta: "",
                        content_hash: &hash,
                        source_app: source.as_deref(),
                        byte_size: text.len() as i64,
                        image_blob: None,
                        rich_html: snap.html.as_deref(),
                        rich_rtf: snap.rtf.as_deref(),
                    };
                    let conn_g = conn.lock();
                    if let Err(e) = db::upsert_item(
                        &conn_g,
                        item,
                        dedupe.load(std::sync::atomic::Ordering::Relaxed),
                    ) {
                        log::error!("insert text item: {e}");
                    } else {
                        let _ = db::trim_history(&conn_g, max_history);
                        let _ = db::trim_expired(&conn_g, retention_days);
                        // fan out to paired devices (direction 129); text
                        // payloads only for now — image sync rides later
                        crate::sync::on_captured(&conn_g, kind, &text);
                        drop(conn_g);
                        let _ = app.emit("clipboard-changed", ());
                        #[cfg(target_os = "windows")]
                        crate::jumplist::refresh(&conn);
                    }
                    continue;
                }
            }

            // Then image. Hash the raw pixels + dims (cheap) — encoding the
            // full PNG on every poll just to compare would burn serious CPU
            // while a large image sits in the clipboard.
            if let Ok(img) = clipboard.get_image() {
                if img.width == 0 || img.height == 0 {
                    continue;
                }
                let hash = hash_image(&img);
                if Some(&hash) != last_image_hash.as_ref() {
                    last_image_hash = Some(hash.clone());
                    last_text_hash = None;
                    quiet_runs = 0; // new content -> fast poll next round
                    if paused {
                        log::info!(
                            "capture paused ({}s left), skipping image",
                            paused_until - db::now_unix()
                        );
                        continue;
                    }
                    let source = crate::frontmost_app_name(&app);
                    if crate::source_blacked(&app, &source) {
                        log::info!("source app blacklisted, skipping image insert");
                        continue;
                    }
                    let png = match encode_png(&img) {
                        Ok(p) => p,
                        Err(e) => {
                            log::warn!("encode png: {e}");
                            continue;
                        }
                    };
                    let thumb = thumbnail_b64(&img, 320);
                    let meta = format!("{}x{}", img.width, img.height);
                    let item = db::InsertItem {
                        kind: "image",
                        content: &meta,
                        preview: &thumb,
                        meta: &meta,
                        content_hash: &hash,
                        source_app: source.as_deref(),
                        byte_size: png.len() as i64,
                        image_blob: Some(&png),
                        rich_html: None,
                        rich_rtf: None,
                    };
                    let conn_g = conn.lock();
                    if let Err(e) = db::upsert_item(
                        &conn_g,
                        item,
                        dedupe.load(std::sync::atomic::Ordering::Relaxed),
                    ) {
                        log::error!("insert image item: {e}");
                    } else {
                        let _ = db::trim_history(&conn_g, max_history);
                        let _ = db::trim_expired(&conn_g, retention_days);
                        drop(conn_g);
                        let _ = app.emit("clipboard-changed", ());
                    }
                }
            }
        }
    });
}

/// First poll inside the 02:00–05:00 local window each day triggers the
/// reclaim; `last_run` is the local "YYYY-MM-DD" it last ran on.
fn should_night_reclaim(hour: u32, today: &str, last_run: &Option<String>) -> bool {
    (2..5).contains(&hour) && last_run.as_deref() != Some(today)
}

fn classify_text(s: &str) -> (&'static str, String) {
    let trimmed = s.trim();
    let preview: String = trimmed.chars().take(120).collect();

    // color: #RGB / #RRGGBB / #RRGGBBAA
    if is_color(trimmed) {
        return ("color", preview);
    }
    // url
    if is_url(trimmed) {
        return ("link", preview);
    }
    // code heuristic: contains common code tokens or looks like code
    if looks_like_code(trimmed) {
        return ("code", preview);
    }
    ("text", preview)
}

fn is_color(s: &str) -> bool {
    if !s.starts_with('#') {
        return false;
    }
    let body = &s[1..];
    matches!(body.len(), 3 | 4 | 6 | 8) && body.chars().all(|c| c.is_ascii_hexdigit())
}

fn is_url(s: &str) -> bool {
    if s.contains(char::is_whitespace) {
        return false;
    }
    if s.starts_with("http://") || s.starts_with("https://") || s.starts_with("ftp://") {
        return url::Url::parse(s).is_ok();
    }
    false
}

fn looks_like_code(s: &str) -> bool {
    if s.len() < 8 {
        return false;
    }
    let braces = s.matches(['{', '}', ';', '=']).count();
    let lines = s.lines().count();
    let kw = [
        "function", "const ", "let ", "var ", "import ", "from ", "class ", "def ", "return ",
        "fn ", "func ", "package ", "select ", "SELECT ", "FROM ", "WHERE ", "#include", "kubectl",
        "curl ", "git ", "npm ", "pnpm ", "<html", "</",
    ];
    let has_kw = kw.iter().any(|k| s.contains(k));
    has_kw || (braces >= 2 && lines >= 2)
}

fn hash_str(s: &str) -> String {
    let mut h = Sha256::new();
    h.update(s.as_bytes());
    format!("t:{}", hex(&h.finalize()))
}

/// Hash raw pixel buffer + dimensions — avoids a full PNG re-encode per poll.
fn hash_image(img: &ImageData) -> String {
    let mut h = Sha256::new();
    h.update(img.width.to_le_bytes());
    h.update(img.height.to_le_bytes());
    h.update(&img.bytes);
    format!("i:{}x{}:{}", img.width, img.height, hex(&h.finalize()))
}

fn hex(b: &[u8]) -> String {
    let mut s = String::with_capacity(b.len() * 2);
    for byte in b {
        s.push_str(&format!("{:02x}", byte));
    }
    s
}

fn encode_png(img: &ImageData) -> Result<Vec<u8>, String> {
    use std::io::Cursor;
    let mut buf: Vec<u8> = Vec::new();
    {
        let mut cursor = Cursor::new(&mut buf);
        let mut encoder = png::Encoder::new(&mut cursor, img.width as u32, img.height as u32);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header().map_err(|e| e.to_string())?;
        writer
            .write_image_data(&img.bytes)
            .map_err(|e| e.to_string())?;
    }
    Ok(buf)
}

fn thumbnail_b64(img: &ImageData, max_dim: u32) -> String {
    let w = img.width as u32;
    let h = img.height as u32;
    let scale = (max_dim as f32 / w.max(h) as f32).min(1.0);
    let nw = ((w as f32) * scale) as u32;
    let nh = ((h as f32) * scale) as u32;
    if nw == 0 || nh == 0 {
        return String::new();
    }
    let bytes = if (nw, nh) == (w, h) {
        img.bytes.clone().into_owned()
    } else {
        nearest_rescale(&img.bytes, w, h, nw, nh)
    };
    let small = ImageData {
        width: nw as usize,
        height: nh as usize,
        bytes: std::borrow::Cow::Owned(bytes),
    };
    match encode_png(&small) {
        Ok(p) => general_purpose::STANDARD.encode(p),
        Err(_) => String::new(),
    }
}

fn nearest_rescale(src: &[u8], sw: u32, sh: u32, dw: u32, dh: u32) -> Vec<u8> {
    let mut out = vec![0u8; (dw * dh * 4) as usize];
    for y in 0..dh {
        for x in 0..dw {
            let sx = x * sw / dw;
            let sy = y * sh / dh;
            let si = ((sy * sw + sx) * 4) as usize;
            let di = ((y * dw + x) * 4) as usize;
            out[di..di + 4].copy_from_slice(&src[si..si + 4]);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn night_gate_windows_and_suppression() {
        let none: Option<String> = None;
        // inside the window, never ran → go
        assert!(should_night_reclaim(3, "2026-10-25", &none));
        // outside the window → never
        assert!(!should_night_reclaim(1, "2026-10-25", &none));
        assert!(!should_night_reclaim(5, "2026-10-25", &none));
        // already ran today → suppressed all day
        assert!(!should_night_reclaim(
            4,
            "2026-10-25",
            &Some("2026-10-25".into())
        ));
        // next day inside the window → runs again
        assert!(should_night_reclaim(
            2,
            "2026-10-26",
            &Some("2026-10-25".into())
        ));
    }

    #[test]
    fn classify_colors() {
        assert_eq!(classify_text("#fff").0, "color");
        assert_eq!(classify_text("#ff0000").0, "color");
        assert_eq!(classify_text("#1a2b3c4d").0, "color");
        assert_ne!(classify_text("#ff00zz").0, "color"); // bad hex
        assert_ne!(classify_text("fff").0, "color"); // no #
    }

    #[test]
    fn classify_urls() {
        assert_eq!(classify_text("https://example.com/a?b=1").0, "link");
        assert_eq!(classify_text("http://example.com").0, "link");
        assert_eq!(classify_text("ftp://host/x").0, "link");
        assert_ne!(classify_text("https://exa mple.com").0, "link"); // space
        assert_ne!(classify_text("example.com").0, "link"); // no scheme
    }

    #[test]
    fn classify_code() {
        assert_eq!(classify_text("fn main() { println!(\"x\"); }").0, "code");
        assert_eq!(classify_text("kubectl get pods -n prod").0, "code");
        assert_eq!(classify_text("SELECT * FROM t WHERE a = 1;").0, "code");
        // plain sentence stays text
        assert_eq!(classify_text("今天天气不错，出去走走吧。").0, "text");
    }

    #[test]
    fn image_hash_depends_on_pixels_and_dims() {
        let px = |w, h| ImageData {
            width: w,
            height: h,
            bytes: std::borrow::Cow::Owned(vec![1u8; w * h * 4]),
        };
        assert_ne!(hash_image(&px(2, 2)), hash_image(&px(2, 3)));
        assert_ne!(
            hash_image(&px(2, 2)),
            hash_image(&ImageData {
                width: 2,
                height: 2,
                bytes: std::borrow::Cow::Owned(vec![9u8; 16]),
            })
        );
    }
}
