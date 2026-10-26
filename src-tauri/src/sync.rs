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

/// Wire messages for the pairing handshake (direction 128): the joiner sends
/// `pair-req` with the code displayed on the initiator's screen; the
/// initiator answers `pair-ack` (minting one shared token for both sides)
/// or `pair-deny`. Same length-prefix framing as sync frames.
#[derive(Serialize, Deserialize, Default)]
pub(crate) struct PairMsg {
    pub(crate) op: String,
    #[serde(default)]
    pub(crate) code: String,
    #[serde(default)]
    pub(crate) name: String,
    #[serde(default)]
    pub(crate) token: String,
}

fn send_pair(stream: &mut TcpStream, msg: &PairMsg) -> std::io::Result<()> {
    let body = serde_json::to_vec(msg).map_err(|e| std::io::Error::other(e.to_string()))?;
    stream.write_all(&(body.len() as u32).to_be_bytes())?;
    stream.write_all(&body)?;
    stream.flush()
}

/// Joiner side of the handshake (used by the `pairing_join` command):
/// send the code shown on the target's screen, wait for the ack.
pub fn send_pair_req(stream: &mut TcpStream, code: &str, name: &str) -> std::io::Result<()> {
    send_pair(
        stream,
        &PairMsg {
            op: "pair-req".into(),
            code: code.to_string(),
            name: name.to_string(),
            ..Default::default()
        },
    )
}

/// Read one pairing frame from the peer (ack or deny).
pub fn read_pair_ack(stream: &mut TcpStream) -> Option<PairMsg> {
    let mut len_b = [0u8; 4];
    stream.read_exact(&mut len_b).ok()?;
    let len = u32::from_be_bytes(len_b);
    if len == 0 || len > 4096 {
        return None;
    }
    let mut body = vec![0u8; len as usize];
    stream.read_exact(&mut body).ok()?;
    let msg: PairMsg = serde_json::from_slice(&body).ok()?;
    (msg.op == "pair-ack" || msg.op == "pair-deny").then_some(msg)
}

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

fn read_frame_raw(stream: &mut TcpStream) -> Option<Vec<u8>> {
    let mut len_b = [0u8; 4];
    stream.read_exact(&mut len_b).ok()?;
    let len = u32::from_be_bytes(len_b);
    if len == 0 || len > MAX_FRAME {
        return None;
    }
    let mut body = vec![0u8; len as usize];
    stream.read_exact(&mut body).ok()?;
    Some(body)
}

/// Sync event ring for the settings page (direction 141): newest last,
/// capped at 20; process-local (a restart clears it, matching the log).
#[derive(Clone, serde::Serialize)]
pub struct SyncEvent {
    pub ts: i64,
    pub dir: String,  // "in" | "out" | "fail"
    pub peer: String, // instance label
    pub note: String, // byte counts / reason
}

fn events() -> &'static Mutex<Vec<SyncEvent>> {
    static E: std::sync::OnceLock<Mutex<Vec<SyncEvent>>> = std::sync::OnceLock::new();
    E.get_or_init(|| Mutex::new(Vec::new()))
}

fn push_event(dir: &str, peer: &str, note: String) {
    let mut g = events().lock();
    g.push(SyncEvent {
        ts: db::now_unix(),
        dir: dir.to_string(),
        peer: peer.to_string(),
        note,
    });
    let n = g.len();
    if n > 20 {
        g.drain(0..n - 20);
    }
}

/// Snapshot of the recent sync events (direction 141).
pub fn recent_events() -> Vec<SyncEvent> {
    events().lock().clone()
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
            let Some(raw) = read_frame_raw(&mut s) else {
                continue;
            };
            // pairing handshake first: a `pair-req` frame is answered inline
            // (and may mint a token) before any sync traffic can flow
            if let Ok(req) = serde_json::from_slice::<PairMsg>(&raw) {
                if req.op == "pair-req" {
                    handle_pair_req(&mut s, &conn, req);
                }
                continue;
            }
            let Ok(env) = serde_json::from_slice::<Envelope>(&raw) else {
                continue;
            };
            // only paired instances may talk to us
            let token = {
                let c = conn.lock();
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
                push_event("fail", &env.sender, "decrypt failed".into());
                continue;
            };
            // typed messages (direction 148) are explicit user intent: they
            // land in the clipboard store and toast, ignoring the sync gate
            if p.kind == "msg" {
                let c = conn.lock();
                let item = InsertItem {
                    kind: "text",
                    content: &p.content,
                    preview: &p.content.chars().take(120).collect::<String>(),
                    meta: "",
                    content_hash: &{
                        let mut h = Sha256::new();
                        h.update(p.content.as_bytes());
                        format!("t:{}", hex(&h.finalize()))
                    },
                    source_app: Some(&env.sender),
                    byte_size: p.content.len() as i64,
                    image_blob: None,
                    rich_html: None,
                    rich_rtf: None,
                };
                match db::upsert_item(&c, item, true) {
                    Ok(_) => {
                        log::info!("msg in: {} chars from {}", p.content.len(), env.sender);
                        push_event("in", &env.sender, format!("💬 {} chars", p.content.len()));
                        let _ = crate::notify_due(
                            format!("贴贴 · 来自 {}", env.sender),
                            p.content.clone(),
                        );
                    }
                    Err(e) => log::error!("msg insert: {e}"),
                }
                continue;
            }
            // clipboard frames honour the sync gate; typed messages above do not
            if !enabled(&conn.lock()) {
                continue;
            }
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
                    push_event("in", &env.sender, format!("{}B", p.content.len()));
                    touch_last_sync(&c, &env.sender);
                }
                Err(e) => log::error!("sync insert: {e}"),
            }
        }
    });
}

/// Validate a joiner's `pair-req` against the pairing code displayed on
/// this machine; on match, mint ONE token, store it for the joiner and hand
/// it back — both ends then hold the same shared secret (direction 128).
fn handle_pair_req(stream: &mut TcpStream, conn: &Arc<Mutex<Connection>>, req: PairMsg) {
    let peer_ip = stream
        .peer_addr()
        .map(|a| a.ip().to_string())
        .unwrap_or_default();
    let mut deny = |why: &str| {
        log::info!("pairing denied: {why}");
        let _ = send_pair(
            stream,
            &PairMsg {
                op: "pair-deny".into(),
                ..Default::default()
            },
        );
    };
    let Some(p) = crate::pending_pairing().lock().clone() else {
        return deny("no pending pairing");
    };
    if p.instance != req.name {
        return deny(&format!(
            "pending is for {}, req from {}",
            p.instance, req.name
        ));
    }
    if db::now_unix() > p.expires_at {
        *crate::pending_pairing().lock() = None;
        return deny("pairing code expired");
    }
    if p.code != req.code.trim() {
        return deny("wrong code"); // pending stays armed for a retry
    }
    *crate::pending_pairing().lock() = None;
    let mut b = [0u8; 32];
    if getrandom::fill(&mut b).is_err() {
        return deny("rng failed");
    }
    let token = base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(b);
    {
        let c = conn.lock();
        if let Err(e) = c.execute(
            "INSERT INTO pairing (instance, addr, token, created_at) VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(instance) DO UPDATE SET addr=?2, token=?3, created_at=?4",
            rusqlite::params![req.name, peer_ip, token, db::now_unix()],
        ) {
            log::error!("pairing store: {e}");
            return;
        }
    }
    log::info!("pairing wire: paired with {} at {peer_ip}", req.name);
    push_event("in", &req.name, "paired".into());
    let _ = send_pair(
        stream,
        &PairMsg {
            op: "pair-ack".into(),
            name: crate::mdns_sync::our_instance(),
            token,
            ..Default::default()
        },
    );
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
                push_event("fail", &instance, "unreachable".into());
                continue;
            };
            let _ = stream.set_write_timeout(Some(std::time::Duration::from_secs(2)));
            if send_frame(&mut stream, &env).is_ok() {
                log::info!("sync out: {} bytes to {}", env.ct.len(), addr);
                push_event("out", &instance, format!("{}B", env.ct.len()));
                touch_last_sync(&conn.lock(), &instance);
            }
        }
    });
}

fn connect_try(a: &std::net::SocketAddr) -> std::net::SocketAddr {
    *a
}

/// Typed message to a paired peer (direction 148): explicit user intent, so
/// this bypasses the sync gate on both ends; `instance = None` fans out to
/// every paired device. The message also lands in the LOCAL clipboard store
/// so the sender can re-copy it later. Delivery runs on a background thread.
pub fn send_message(
    conn: &Arc<Mutex<Connection>>,
    instance: Option<String>,
    text: &str,
) -> Result<(), String> {
    let text = text.trim();
    if text.is_empty() {
        return Err("消息为空".into());
    }
    {
        let mut h = Sha256::new();
        h.update(text.as_bytes());
        let hash = format!("t:{}", hex(&h.finalize()));
        let c = conn.lock();
        let item = InsertItem {
            kind: "text",
            content: text,
            preview: &text.chars().take(120).collect::<String>(),
            meta: "",
            content_hash: &hash,
            source_app: Some("💬"),
            byte_size: text.len() as i64,
            image_blob: None,
            rich_html: None,
            rich_rtf: None,
        };
        db::upsert_item(&c, item, true).map_err(|e| e.to_string())?;
    }
    let targets: Vec<(String, String, String)> = {
        let c = conn.lock();
        let mut stmt = c
            .prepare("SELECT instance, addr, token FROM pairing")
            .map_err(|e| e.to_string())?;
        let rows = stmt
            .query_map([], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))
            .map(|rows| rows.filter_map(|x| x.ok()).collect::<Vec<_>>())
            .map_err(|e| e.to_string())?;
        rows.into_iter()
            .filter(|(i, _, _)| instance.as_deref().map(|w| i == w).unwrap_or(true))
            .collect()
    };
    if targets.is_empty() {
        return Err("没有已配对设备".into());
    }
    let p = SyncPayload {
        kind: "msg".into(),
        content: text.to_string(),
        ts: db::now_unix(),
        image_b64: None,
        hash: None,
    };
    let me = hostname_instance();
    let conn = conn.clone();
    std::thread::spawn(move || {
        for (instance, addr, token) in targets {
            let env = seal(&session_key(&token), &me, &p);
            let Ok(sa) = std::net::SocketAddr::from_str(&addr) else {
                log::warn!("msg: bad peer addr {addr}");
                continue;
            };
            let Ok(mut stream) = TcpStream::connect_timeout(&sa, std::time::Duration::from_secs(3))
            else {
                push_event("fail", &instance, "unreachable".into());
                continue;
            };
            let _ = stream.set_write_timeout(Some(std::time::Duration::from_secs(3)));
            if send_frame(&mut stream, &env).is_ok() {
                log::info!("msg out: {} chars to {}", p.content.len(), addr);
                push_event("out", &instance, format!("💬 {} chars", p.content.len()));
                touch_last_sync(&conn.lock(), &instance);
            }
        }
    });
    Ok(())
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
