use rusqlite::{params, Connection, Result as SqlResult};
use serde::Serialize;
use std::path::Path;

#[derive(Debug, Clone, Serialize)]
pub struct ClipItem {
    pub id: i64,
    pub kind: String,
    pub content: String,
    pub preview: String,
    pub meta: String,
    pub pinned: bool,
    pub folder_id: Option<i64>,
    pub source_app: Option<String>,
    pub created_at: i64,
    pub used_at: i64,
    pub use_count: i64,
    pub byte_size: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct Folder {
    pub id: i64,
    pub name: String,
    pub color: String,
    pub sort_order: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct LauncherSlot {
    pub id: i64,
    pub slot_index: i64,
    pub label: String,
    pub target: String,
    pub icon_path: Option<String>,
}

pub fn open(path: &Path) -> SqlResult<Connection> {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let conn = Connection::open(path)?;
    conn.execute_batch(
        r#"
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS folder (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#007aff',
            sort_order INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS clip_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            preview TEXT NOT NULL DEFAULT '',
            meta TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0,
            folder_id INTEGER REFERENCES folder(id) ON DELETE SET NULL,
            source_app TEXT,
            created_at INTEGER NOT NULL,
            used_at INTEGER NOT NULL,
            use_count INTEGER NOT NULL DEFAULT 0,
            byte_size INTEGER NOT NULL DEFAULT 0,
            image_blob BLOB
        );

        CREATE INDEX IF NOT EXISTS idx_clip_used ON clip_item(used_at DESC);
        CREATE INDEX IF NOT EXISTS idx_clip_pinned ON clip_item(pinned DESC, used_at DESC);
        CREATE INDEX IF NOT EXISTS idx_clip_kind ON clip_item(kind, used_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_clip_hash ON clip_item(content_hash);

        CREATE TABLE IF NOT EXISTS launcher_slot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_index INTEGER NOT NULL UNIQUE,
            label TEXT NOT NULL,
            target TEXT NOT NULL,
            icon_path TEXT
        );

        CREATE TABLE IF NOT EXISTS setting (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        "#,
    )?;
    Ok(conn)
}

pub fn list_items(conn: &Connection, limit: i64) -> SqlResult<Vec<ClipItem>> {
    let mut stmt = conn.prepare(
        "SELECT id, kind, content, preview, meta, pinned, folder_id, source_app,
                created_at, used_at, use_count, byte_size
         FROM clip_item
         ORDER BY pinned DESC, used_at DESC
         LIMIT ?1",
    )?;
    let items = stmt
        .query_map(params![limit], row_to_item)?
        .collect::<SqlResult<Vec<_>>>()?;
    Ok(items)
}

fn row_to_item(row: &rusqlite::Row) -> SqlResult<ClipItem> {
    Ok(ClipItem {
        id: row.get(0)?,
        kind: row.get(1)?,
        content: row.get(2)?,
        preview: row.get(3)?,
        meta: row.get(4)?,
        pinned: row.get::<_, i64>(5)? != 0,
        folder_id: row.get(6)?,
        source_app: row.get(7)?,
        created_at: row.get(8)?,
        used_at: row.get(9)?,
        use_count: row.get(10)?,
        byte_size: row.get(11)?,
    })
}

pub struct InsertItem<'a> {
    pub kind: &'a str,
    pub content: &'a str,
    pub preview: &'a str,
    pub meta: &'a str,
    pub content_hash: &'a str,
    pub source_app: Option<&'a str>,
    pub byte_size: i64,
    pub image_blob: Option<&'a [u8]>,
}

/// Insert or bump used_at if hash already exists. Returns id.
pub fn upsert_item(conn: &Connection, it: InsertItem) -> SqlResult<i64> {
    let now = now_unix();
    let existing: Option<i64> = conn
        .query_row(
            "SELECT id FROM clip_item WHERE content_hash = ?1",
            params![it.content_hash],
            |r| r.get(0),
        )
        .ok();
    if let Some(id) = existing {
        conn.execute(
            "UPDATE clip_item SET used_at = ?1, use_count = use_count + 1 WHERE id = ?2",
            params![now, id],
        )?;
        return Ok(id);
    }
    conn.execute(
        "INSERT INTO clip_item (kind, content, preview, meta, content_hash, source_app,
                                created_at, used_at, use_count, byte_size, image_blob)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?7, 0, ?8, ?9)",
        params![
            it.kind,
            it.content,
            it.preview,
            it.meta,
            it.content_hash,
            it.source_app,
            now,
            it.byte_size,
            it.image_blob,
        ],
    )?;
    Ok(conn.last_insert_rowid())
}

pub fn touch_item(conn: &Connection, id: i64) -> SqlResult<()> {
    conn.execute(
        "UPDATE clip_item SET used_at = ?1, use_count = use_count + 1 WHERE id = ?2",
        params![now_unix(), id],
    )?;
    Ok(())
}

pub fn toggle_pin(conn: &Connection, id: i64) -> SqlResult<()> {
    conn.execute(
        "UPDATE clip_item SET pinned = 1 - pinned WHERE id = ?1",
        params![id],
    )?;
    Ok(())
}

pub fn delete_item(conn: &Connection, id: i64) -> SqlResult<()> {
    conn.execute("DELETE FROM clip_item WHERE id = ?1", params![id])?;
    Ok(())
}

pub fn update_content(conn: &Connection, id: i64, content: &str) -> SqlResult<()> {
    let preview: String = content.chars().take(120).collect();
    conn.execute(
        "UPDATE clip_item SET content = ?1, preview = ?2, byte_size = ?3 WHERE id = ?4",
        params![content, preview, content.len() as i64, id],
    )?;
    Ok(())
}

pub fn set_folder(conn: &Connection, id: i64, folder_id: Option<i64>) -> SqlResult<()> {
    conn.execute(
        "UPDATE clip_item SET folder_id = ?1 WHERE id = ?2",
        params![folder_id, id],
    )?;
    Ok(())
}

pub fn get_image_blob(conn: &Connection, id: i64) -> SqlResult<Option<Vec<u8>>> {
    conn.query_row(
        "SELECT image_blob FROM clip_item WHERE id = ?1",
        params![id],
        |r| r.get(0),
    )
}

/// Trim to keep history bounded.
pub fn trim_history(conn: &Connection, max: i64) -> SqlResult<usize> {
    let removed = conn.execute(
        "DELETE FROM clip_item WHERE pinned = 0 AND id NOT IN
            (SELECT id FROM clip_item WHERE pinned = 0 ORDER BY used_at DESC LIMIT ?1)",
        params![max],
    )?;
    Ok(removed)
}

pub fn list_folders(conn: &Connection) -> SqlResult<Vec<Folder>> {
    let mut stmt = conn.prepare(
        "SELECT id, name, color, sort_order FROM folder ORDER BY sort_order ASC, id ASC",
    )?;
    let fs = stmt
        .query_map([], |row| {
            Ok(Folder {
                id: row.get(0)?,
                name: row.get(1)?,
                color: row.get(2)?,
                sort_order: row.get(3)?,
            })
        })?
        .collect::<SqlResult<Vec<_>>>()?;
    Ok(fs)
}

pub fn create_folder(conn: &Connection, name: &str, color: &str) -> SqlResult<i64> {
    let next: i64 = conn
        .query_row(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM folder",
            [],
            |r| r.get(0),
        )
        .unwrap_or(1);
    conn.execute(
        "INSERT INTO folder (name, color, sort_order) VALUES (?1, ?2, ?3)",
        params![name, color, next],
    )?;
    Ok(conn.last_insert_rowid())
}

pub fn delete_folder(conn: &Connection, id: i64) -> SqlResult<()> {
    conn.execute("DELETE FROM folder WHERE id = ?1", params![id])?;
    Ok(())
}

pub fn list_slots(conn: &Connection) -> SqlResult<Vec<LauncherSlot>> {
    let mut stmt = conn.prepare(
        "SELECT id, slot_index, label, target, icon_path FROM launcher_slot ORDER BY slot_index",
    )?;
    let xs = stmt
        .query_map([], |row| {
            Ok(LauncherSlot {
                id: row.get(0)?,
                slot_index: row.get(1)?,
                label: row.get(2)?,
                target: row.get(3)?,
                icon_path: row.get(4)?,
            })
        })?
        .collect::<SqlResult<Vec<_>>>()?;
    Ok(xs)
}

pub fn upsert_slot(
    conn: &Connection,
    slot_index: i64,
    label: &str,
    target: &str,
    icon_path: Option<&str>,
) -> SqlResult<()> {
    conn.execute(
        "INSERT INTO launcher_slot (slot_index, label, target, icon_path) VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT(slot_index) DO UPDATE SET label=excluded.label, target=excluded.target, icon_path=excluded.icon_path",
        params![slot_index, label, target, icon_path],
    )?;
    Ok(())
}

pub fn delete_slot(conn: &Connection, slot_index: i64) -> SqlResult<()> {
    conn.execute(
        "DELETE FROM launcher_slot WHERE slot_index = ?1",
        params![slot_index],
    )?;
    Ok(())
}

pub fn now_unix() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}
