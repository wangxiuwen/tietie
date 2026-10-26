//! Encrypted clipboard sync over TCP for paired devices (direction 129).
//!
//! Session key = SHA-256(pairing token ‖ "tietie-sync-v1"). The token was
//! minted when both ends proved the same pairing code (direction 128), so
//! it is the shared secret; each frame carries its own random 12-byte nonce
//! and the sender instance as AES-GCM AAD. Inbound frames are only accepted
//! from instances in the pairing table and land through the normal upsert
//! path, so content-hash dedup applies on both ends. An echo-suppression
//! hash stops A→B→A loops: received content is never pushed back out.

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::str::FromStr;
use std::sync::Arc;

use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::{Aes256Gcm, Nonce};
use base64::Engine as _;
use parking_lot::Mutex;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::db::{self, InsertItem};

pub const PORT: u16 = 41784;
const LABEL: &[u8] = b"tietie-sync-v1";
const MAX_FRAME: u32 = 4 * 1024 * 1024;

#[derive(Serialize, Deserialize)]
struct Envelope {
    sender: String,
    nonce: String, // b64, 12 bytes
    ct: String,    // b64 AES-GCM ciphertext
}

#[derive(Serialize, Deserialize)]
struct SyncPayload {
    kind: String,
    content: String,
    ts: i64,
    /// image captures only: b64-encoded PNG (direction 137); text sync
    /// sends none and receivers must not require it
    image_b64: Option<String>,
    /// content_hash of the sending side — receivers dedupe on it
    hash: Option<String>,
}

fn session_key(token: &str) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(token.as_bytes());
    h.update(LABEL);
    h.finalize().into()
}

fn seal(key: &[u8; 32], sender: &str, p: &SyncPayload) -> Envelope {
    let pt = serde_json::to_vec(p).unwrap_or_default();
    let nonce_bytes = {
        let mut b = [0u8; 12];
        _ = getrandom::fill(&mut b);
        b
    };
    let cipher = Aes256Gcm::new(key.into());
    let ct = cipher
        .encrypt(
            Nonce::from_slice(&nonce_bytes),
            Payload {
                msg: &pt,
                aad: sender.as_bytes(),
            },
        )
        .unwrap_or_default();
    let b64 = &base64::engine::general_purpose::STANDARD;
    Envelope {
        sender: sender.to_string(),
        nonce: b64.encode(nonce_bytes),
        ct: b64.encode(ct),
    }
}

fn open(key: &[u8; 32], env: &Envelope) -> Option<SyncPayload> {
    let b64 = &base64::engine::general_purpose::STANDARD;
    let nonce_bytes: Vec<u8> = b64.decode(&env.nonce).ok()?;
    let ct: Vec<u8> = b64.decode(&env.ct).ok()?;
    if nonce_bytes.len() != 12 {
        return None;
    }
    let cipher = Aes256Gcm::new(key.into());
    let pt = cipher
        .decrypt(
            Nonce::from_slice(&nonce_bytes),
            Payload {
                msg: &ct,
                aad: env.sender.as_bytes(),
            },
        )
        .ok()?;
    serde_json::from_slice(&pt).ok()
}

fn send_frame(stream: &mut TcpStream, env: &Envelope) -> std::io::Result<()> {
    let body = serde_json::to_vec(env).map_err(|e| std::io::Error::other(e.to_string()))?;
    stream.write_all(&(body.len() as u32).to_be_bytes())?;
    stream.write_all(&body)?;
    stream.flush()
}

fn read_frame(stream: &mut TcpStream) -> Option<Envelope> {
    let mut len_b = [0u8; 4];
    stream.read_exact(&mut len_b).ok()?;
    let len = u32::from_be_bytes(len_b);
    if len == 0 || len > MAX_FRAME {
        return None;
    }
    let mut body = vec![0u8; len as usize];
    stream.read_exact(&mut body).ok()?;
    serde_json::from_slice(&body).ok()
}

// last content hash we RECEIVED over sync — pushed-back-out suppression
fn last_received() -> &'static Mutex<String> {
    static H: std::sync::OnceLock<Mutex<String>> = std::sync::OnceLock::new();
    H.get_or_init(|| Mutex::new(String::new()))
}

/// Sync on/off preference (setting table; default off).
pub fn enabled(conn: &Connection) -> bool {
    conn.query_row(
        "SELECT value FROM setting WHERE key = 'sync_enabled'",
        [],
        |r| r.get::<_, String>(0),
    )
    .map(|v| v == "1")
    .unwrap_or(false)
}

pub fn set_enabled(conn: &Connection, on: bool) {
    let _ = conn.execute(
        "INSERT INTO setting (key, value) VALUES ('sync_enabled', ?1)
         ON CONFLICT(key) DO UPDATE SET value = ?1",
        rusqlite::params![if on { "1" } else { "0" }],
    );
}

/// Accept loop for inbound sealed frames. One thread for the process.
pub fn start_server(conn: Arc<Mutex<Connection>>) {
    std::thread::spawn(move || {
        let listener = match TcpListener::bind(("0.0.0.0", PORT)) {
            Ok(l) => l,
            Err(e) => {
                log::warn!("sync server not started: {e}");
                return;
            }
        };
        log::info!("sync server listening on {PORT}");
        for stream in listener.incoming() {
            let Ok(mut s) = stream else { continue };
            let Ok(_) = s.set_read_timeout(Some(std::time::Duration::from_secs(5))) else {
                continue;
            };
            let Some(env) = read_frame(&mut s) else {
                continue;
            };
            // only paired instances may talk to us
            let token = {
                let c = conn.lock();
                if !enabled(&c) {
                    continue;
                }
                c.query_row(
                    "SELECT token FROM pairing WHERE instance = ?1",
                    rusqlite::params![env.sender],
                    |r| r.get::<_, String>(0),
                )
                .ok()
            };
            let Some(token) = token else {
                log::warn!("sync frame from unpaired {}", env.sender);
                continue;
            };
            let Some(p) = open(&session_key(&token), &env) else {
                log::warn!("sync frame failed to decrypt (bad key/AAD)");
                continue;
            };
            // dedupe on the sender's hash when present (images), else the
            // local content hash — both stop A→B→A echoes
            let hash = match p.hash.as_deref() {
                Some(h) if !h.is_empty() => h.to_string(),
                _ => {
                    let mut h = Sha256::new();
                    h.update(p.content.as_bytes());
                    format!("t:{}", hex(&h.finalize()))
                }
            };
            if *last_received().lock() == hash {
                continue; // echo of our own content
            }
            *last_received().lock() = hash.clone();
            let c = conn.lock();
            let preview: String = p.content.chars().take(120).collect();
            let img_blob: Option<Vec<u8>> = if p.kind == "image" {
                p.image_b64
                    .as_deref()
                    .and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok())
            } else {
                None
            };
            let item = InsertItem {
                kind: &p.kind,
                content: &p.content,
                preview: &preview,
                meta: if p.kind == "image" { &p.content } else { "" },
                content_hash: &hash,
                source_app: Some(&env.sender),
                byte_size: p.content.len() as i64,
                image_blob: img_blob.as_deref(),
                rich_html: None,
                rich_rtf: None,
            };
            match db::upsert_item(&c, item, true) {
                Ok(_) => {
                    log::info!("sync in: {} bytes from {}", p.content.len(), env.sender);
                    touch_last_sync(&c, &env.sender);
                }
                Err(e) => log::error!("sync insert: {e}"),
            }
        }
    });
}

/// Record a successful sync exchange with a peer (direction 130).
fn touch_last_sync(conn: &Connection, instance: &str) {
    let _ = conn.execute(
        "UPDATE pairing SET last_sync_at = ?2 WHERE instance = ?1",
        rusqlite::params![instance, db::now_unix()],
    );
}

/// Outbound fan-out after a local capture. Never blocks the poll loop:
/// peers are pushed from a background thread with short timeouts.
pub fn on_captured(
    conn: &Arc<Mutex<Connection>>,
    kind: &str,
    content: &str,
    hash: &str,
    image_b64: Option<String>,
) {
    if !enabled(&conn.lock()) {
        return;
    }
    if *last_received().lock() == hash {
        return; // this capture IS an inbound sync echo
    }
    let rows: Vec<(String, String, String)> = match conn
        .lock()
        .prepare("SELECT instance, addr, token FROM pairing")
        .and_then(|mut s| {
            s.query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
                .map(|rows| rows.filter_map(|x| x.ok()).collect())
        }) {
        Ok(v) => v,
        Err(_) => return,
    };
    if rows.is_empty() {
        return;
    }
    let kind = kind.to_string();
    let content = content.to_string();
    let hash = hash.to_string();
    let conn = conn.clone();
    std::thread::spawn(move || {
        let me = hostname_instance();
        let p = SyncPayload {
            kind,
            content,
            ts: db::now_unix(),
            image_b64,
            hash: Some(hash),
        };
        for (instance, addr, token) in rows {
            let env = seal(&session_key(&token), &me, &p);
            let Ok(sock_addr) = std::net::SocketAddr::from_str(&addr) else {
                log::warn!("sync: bad peer addr {addr}");
                continue;
            };
            let connect = std::net::SocketAddr::new(sock_addr.ip(), sock_addr.port());
            let Ok(mut stream) = TcpStream::connect_timeout(
                &connect_try(&connect),
                std::time::Duration::from_secs(2),
            ) else {
                log::info!("sync: peer {addr} unreachable");
                continue;
            };
            let _ = stream.set_write_timeout(Some(std::time::Duration::from_secs(2)));
            if send_frame(&mut stream, &env).is_ok() {
                log::info!("sync out: {} bytes to {}", env.ct.len(), addr);
                touch_last_sync(&conn.lock(), &instance);
            }
        }
    });
}

fn connect_try(a: &std::net::SocketAddr) -> std::net::SocketAddr {
    *a
}

fn hex(b: &[u8]) -> String {
    let mut s = String::with_capacity(b.len() * 2);
    for byte in b {
        s.push_str(&format!("{byte:02x}"));
    }
    s
}

fn hostname_instance() -> String {
    crate::mdns_sync::our_instance()
}
