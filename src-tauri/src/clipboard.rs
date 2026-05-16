use crate::db;
use arboard::{Clipboard, ImageData};
use base64::{engine::general_purpose, Engine as _};
use parking_lot::Mutex;
use sha2::{Digest, Sha256};
use std::sync::Arc;
use std::time::Duration;
use tauri::{AppHandle, Emitter};

const POLL_MS: u64 = 600;
const MAX_HISTORY: i64 = 500;

pub fn start_polling(app: AppHandle, conn: Arc<Mutex<rusqlite::Connection>>) {
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

        loop {
            std::thread::sleep(Duration::from_millis(POLL_MS));

            // Try text first
            if let Ok(text) = clipboard.get_text() {
                let hash = hash_str(&text);
                if Some(&hash) != last_text_hash.as_ref() && !text.is_empty() {
                    last_text_hash = Some(hash.clone());
                    last_image_hash = None;
                    let (kind, preview) = classify_text(&text);
                    let item = db::InsertItem {
                        kind,
                        content: &text,
                        preview: &preview,
                        meta: "",
                        content_hash: &hash,
                        source_app: None,
                        byte_size: text.len() as i64,
                        image_blob: None,
                    };
                    let conn_g = conn.lock();
                    if let Err(e) = db::upsert_item(&conn_g, item) {
                        log::error!("insert text item: {e}");
                    } else {
                        let _ = db::trim_history(&conn_g, MAX_HISTORY);
                        drop(conn_g);
                        let _ = app.emit("clipboard-changed", ());
                    }
                    continue;
                }
            }

            // Then image
            if let Ok(img) = clipboard.get_image() {
                if img.width == 0 || img.height == 0 {
                    continue;
                }
                let png = match encode_png(&img) {
                    Ok(p) => p,
                    Err(e) => {
                        log::warn!("encode png: {e}");
                        continue;
                    }
                };
                let hash = hash_bytes(&png);
                if Some(&hash) != last_image_hash.as_ref() {
                    last_image_hash = Some(hash.clone());
                    last_text_hash = None;
                    let thumb = thumbnail_b64(&img, 320);
                    let meta = format!("{}x{}", img.width, img.height);
                    let item = db::InsertItem {
                        kind: "image",
                        content: &meta,
                        preview: &thumb,
                        meta: &meta,
                        content_hash: &hash,
                        source_app: None,
                        byte_size: png.len() as i64,
                        image_blob: Some(&png),
                    };
                    let conn_g = conn.lock();
                    if let Err(e) = db::upsert_item(&conn_g, item) {
                        log::error!("insert image item: {e}");
                    } else {
                        let _ = db::trim_history(&conn_g, MAX_HISTORY);
                        drop(conn_g);
                        let _ = app.emit("clipboard-changed", ());
                    }
                }
            }
        }
    });
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

fn hash_bytes(b: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(b);
    format!("i:{}", hex(&h.finalize()))
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
