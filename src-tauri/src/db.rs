use rusqlite::{params, Connection, Result as SqlResult};
use serde::{Deserialize, Serialize};
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

/// A note hung on the clothesline. Created by dragging a clip item up
/// from the drawer; content is a snapshot copy of the item at hang time.
/// source_item_id keeps a link back so image memos can copy the full blob.
#[derive(Debug, Clone, Serialize)]
pub struct Memo {
    pub id: i64,
    pub kind: String,
    pub content: String,
    pub preview: String,
    pub color: String,
    pub pinned: bool,
    pub source_item_id: Option<i64>,
    pub created_at: i64,
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
            image_blob BLOB,
            rich_html TEXT,
            rich_rtf BLOB
        );

        CREATE INDEX IF NOT EXISTS idx_clip_used ON clip_item(used_at DESC);
        CREATE INDEX IF NOT EXISTS idx_clip_pinned ON clip_item(pinned DESC, used_at DESC);
        CREATE INDEX IF NOT EXISTS idx_clip_kind ON clip_item(kind, used_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_clip_hash ON clip_item(content_hash);

        CREATE TABLE IF NOT EXISTS setting (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            preview TEXT NOT NULL DEFAULT '',
            color TEXT NOT NULL DEFAULT '#007aff',
            source_item_id INTEGER,
            created_at INTEGER NOT NULL
        );
        "#,
    )?;
    // Idempotent migrations for older databases (created before rich-text support).
    let _ = conn.execute("ALTER TABLE clip_item ADD COLUMN rich_html TEXT", []);
    let _ = conn.execute("ALTER TABLE clip_item ADD COLUMN rich_rtf BLOB", []);
    // memo pinned (clothesline sticky notes)
    let _ = conn.execute(
        "ALTER TABLE memo ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0",
        [],
    );
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
    pub rich_html: Option<&'a str>,
    pub rich_rtf: Option<&'a [u8]>,
}

/// Insert or bump used_at if hash already exists. Returns id.
/// Insert or bump. With `dedupe` (default), re-copying the same content
/// moves it to the front and counts a use. Without it, every copy becomes a
/// fresh row — the unique hash index is sidestepped with a `#n` suffix.
pub fn upsert_item(conn: &Connection, it: InsertItem, dedupe: bool) -> SqlResult<i64> {
    let now = now_unix();
    let existing: Option<i64> = conn
        .query_row(
            "SELECT id FROM clip_item WHERE content_hash = ?1",
            params![it.content_hash],
            |r| r.get(0),
        )
        .ok();
    if let Some(id) = existing {
        if dedupe {
            conn.execute(
                "UPDATE clip_item SET used_at = ?1, use_count = use_count + 1 WHERE id = ?2",
                params![now, id],
            )?;
            return Ok(id);
        }
        // not merging: insert a fresh row with a suffixed hash
        let mut n = 2;
        loop {
            let candidate = format!("{}#{n}", it.content_hash);
            let taken: bool = conn
                .query_row(
                    "SELECT COUNT(*) FROM clip_item WHERE content_hash = ?1",
                    params![candidate],
                    |r| r.get::<_, i64>(0),
                )
                .map(|c| c > 0)
                .unwrap_or(false);
            if !taken {
                return conn.execute(
                    "INSERT INTO clip_item (kind, content, preview, meta, content_hash, source_app,
                                            created_at, used_at, use_count, byte_size, image_blob,
                                            rich_html, rich_rtf)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?7, 0, ?8, ?9, ?10, ?11)",
                    params![
                        it.kind,
                        it.content,
                        it.preview,
                        it.meta,
                        candidate,
                        it.source_app,
                        now,
                        it.byte_size,
                        it.image_blob,
                        it.rich_html,
                        it.rich_rtf,
                    ],
                )
                .map(|_| conn.last_insert_rowid());
            }
            n += 1;
        }
    }
    conn.execute(
        "INSERT INTO clip_item (kind, content, preview, meta, content_hash, source_app,
                                created_at, used_at, use_count, byte_size, image_blob,
                                rich_html, rich_rtf)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?7, 0, ?8, ?9, ?10, ?11)",
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
            it.rich_html,
            it.rich_rtf,
        ],
    )?;
    Ok(conn.last_insert_rowid())
}

// Fields only read on macOS (paste_item rich-text / image write); non-mac
// builds still construct the struct but clippy would flag unused fields.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
pub struct FullItem {
    pub kind: String,
    pub content: String,
    pub image_blob: Option<Vec<u8>>,
    pub rich_html: Option<String>,
    pub rich_rtf: Option<Vec<u8>>,
}

/// Read full payload for an item — used by paste_item to compose the
/// right pasteboard write.
pub fn get_full(conn: &Connection, id: i64) -> SqlResult<FullItem> {
    conn.query_row(
        "SELECT kind, content, image_blob, rich_html, rich_rtf
         FROM clip_item WHERE id = ?1",
        params![id],
        |r| {
            Ok(FullItem {
                kind: r.get(0)?,
                content: r.get(1)?,
                image_blob: r.get(2)?,
                rich_html: r.get(3)?,
                rich_rtf: r.get(4)?,
            })
        },
    )
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

// ─────────────────────────── memos (clothesline) ───────────────────────────

pub fn list_memos(conn: &Connection) -> SqlResult<Vec<Memo>> {
    let mut stmt = conn.prepare(
        "SELECT id, kind, content, preview, color, pinned, source_item_id, created_at
         FROM memo ORDER BY pinned DESC, id ASC",
    )?;
    let ms = stmt
        .query_map([], |row| {
            Ok(Memo {
                id: row.get(0)?,
                kind: row.get(1)?,
                content: row.get(2)?,
                preview: row.get(3)?,
                color: row.get(4)?,
                pinned: row.get::<_, i64>(5)? != 0,
                source_item_id: row.get(6)?,
                created_at: row.get(7)?,
            })
        })?
        .collect::<SqlResult<Vec<_>>>()?;
    Ok(ms)
}

/// Hang a clip item on the line as a memo (snapshot copy + source link).
pub fn hang_memo(conn: &Connection, item_id: i64, color: &str) -> SqlResult<i64> {
    conn.execute(
        "INSERT INTO memo (kind, content, preview, color, source_item_id, created_at)
         SELECT kind, content, preview, ?2, id, ?3 FROM clip_item WHERE id = ?1",
        params![item_id, color, now_unix()],
    )?;
    Ok(conn.last_insert_rowid())
}

pub fn remove_memo(conn: &Connection, id: i64) -> SqlResult<()> {
    conn.execute("DELETE FROM memo WHERE id = ?1", params![id])?;
    Ok(())
}

pub fn toggle_memo_pin(conn: &Connection, id: i64) -> SqlResult<()> {
    conn.execute(
        "UPDATE memo SET pinned = 1 - pinned WHERE id = ?1",
        params![id],
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

// ─────────────────────────── backup export / import ───────────────────────────

/// Backup file format v1. Blobs ride as base64 strings so the JSON stays
/// portable; ids are not exported (restored rows get fresh autoincrement ids
/// and merge by natural keys).
#[derive(Serialize, Deserialize)]
pub struct BackupV1 {
    pub version: u32,
    pub exported_at: i64,
    pub folders: Vec<BackupFolder>,
    pub memos: Vec<BackupMemo>,
    pub items: Vec<BackupItem>,
}

#[derive(Serialize, Deserialize)]
pub struct BackupFolder {
    pub name: String,
    pub color: String,
    pub sort_order: i64,
}

#[derive(Serialize, Deserialize)]
pub struct BackupMemo {
    pub kind: String,
    pub content: String,
    pub preview: String,
    pub color: String,
    pub pinned: bool,
    pub created_at: i64,
}

#[derive(Serialize, Deserialize)]
pub struct BackupItem {
    pub kind: String,
    pub content: String,
    pub preview: String,
    pub meta: String,
    pub content_hash: String,
    pub pinned: bool,
    pub source_app: Option<String>,
    pub created_at: i64,
    pub used_at: i64,
    pub use_count: i64,
    pub byte_size: i64,
    pub image_blob_b64: Option<String>,
    pub rich_html: Option<String>,
    pub rich_rtf_b64: Option<String>,
}

pub fn dump_backup(conn: &Connection) -> SqlResult<BackupV1> {
    use base64::{engine::general_purpose, Engine as _};

    let mut folders = Vec::new();
    {
        let mut stmt = conn.prepare("SELECT name, color, sort_order FROM folder")?;
        let rows = stmt.query_map([], |r| {
            Ok(BackupFolder {
                name: r.get(0)?,
                color: r.get(1)?,
                sort_order: r.get(2)?,
            })
        })?;
        for f in rows {
            folders.push(f?);
        }
    }

    let mut memos = Vec::new();
    {
        let mut stmt =
            conn.prepare("SELECT kind, content, preview, color, pinned, created_at FROM memo")?;
        let rows = stmt.query_map([], |r| {
            Ok(BackupMemo {
                kind: r.get(0)?,
                content: r.get(1)?,
                preview: r.get(2)?,
                color: r.get(3)?,
                pinned: r.get::<_, i64>(4)? != 0,
                created_at: r.get(5)?,
            })
        })?;
        for m in rows {
            memos.push(m?);
        }
    }

    let mut items = Vec::new();
    {
        let mut stmt = conn.prepare(
            "SELECT kind, content, preview, meta, content_hash, pinned, source_app,
                    created_at, used_at, use_count, byte_size, image_blob, rich_html, rich_rtf
             FROM clip_item",
        )?;
        let rows = stmt.query_map([], |r| {
            let blob: Option<Vec<u8>> = r.get(11)?;
            let rtf: Option<Vec<u8>> = r.get(13)?;
            Ok(BackupItem {
                kind: r.get(0)?,
                content: r.get(1)?,
                preview: r.get(2)?,
                meta: r.get(3)?,
                content_hash: r.get(4)?,
                pinned: r.get::<_, i64>(5)? != 0,
                source_app: r.get(6)?,
                created_at: r.get(7)?,
                used_at: r.get(8)?,
                use_count: r.get(9)?,
                byte_size: r.get(10)?,
                image_blob_b64: blob.map(|b| general_purpose::STANDARD.encode(b)),
                rich_html: r.get(12)?,
                rich_rtf_b64: rtf.map(|b| general_purpose::STANDARD.encode(b)),
            })
        })?;
        for it in rows {
            items.push(it?);
        }
    }

    Ok(BackupV1 {
        version: 1,
        exported_at: now_unix(),
        folders,
        memos,
        items,
    })
}

#[derive(Serialize)]
pub struct RestoreStats {
    pub items: usize,
    pub folders: usize,
    pub memos: usize,
}

/// Merge a backup into the live database. Items dedupe on content_hash
/// (unique index, INSERT OR IGNORE); folders on name+color; memos on content.
pub fn restore_backup(conn: &Connection, bak: &BackupV1) -> SqlResult<RestoreStats> {
    use base64::{engine::general_purpose, Engine as _};

    let mut stats = RestoreStats {
        items: 0,
        folders: 0,
        memos: 0,
    };

    for f in &bak.folders {
        let exists: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM folder WHERE name = ?1 AND color = ?2",
                params![f.name, f.color],
                |r| r.get::<_, i64>(0),
            )
            .map(|n| n > 0)
            .unwrap_or(false);
        if exists {
            continue;
        }
        conn.execute(
            "INSERT INTO folder (name, color, sort_order) VALUES (?1, ?2, ?3)",
            params![f.name, f.color, f.sort_order],
        )?;
        stats.folders += 1;
    }

    for m in &bak.memos {
        let exists: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM memo WHERE content = ?1",
                params![m.content],
                |r| r.get::<_, i64>(0),
            )
            .map(|n| n > 0)
            .unwrap_or(false);
        if exists {
            continue;
        }
        conn.execute(
            "INSERT INTO memo (kind, content, preview, color, pinned, source_item_id, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5, NULL, ?6)",
            params![
                m.kind,
                m.content,
                m.preview,
                m.color,
                m.pinned as i64,
                m.created_at
            ],
        )?;
        stats.memos += 1;
    }

    for it in &bak.items {
        let blob = it
            .image_blob_b64
            .as_deref()
            .and_then(|b| general_purpose::STANDARD.decode(b).ok());
        let rtf = it
            .rich_rtf_b64
            .as_deref()
            .and_then(|b| general_purpose::STANDARD.decode(b).ok());
        let inserted = conn.execute(
            "INSERT OR IGNORE INTO clip_item
                (kind, content, preview, meta, content_hash, pinned, source_app,
                 created_at, used_at, use_count, byte_size, image_blob, rich_html, rich_rtf)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14)",
            params![
                it.kind,
                it.content,
                it.preview,
                it.meta,
                it.content_hash,
                it.pinned as i64,
                it.source_app,
                it.created_at,
                it.used_at,
                it.use_count,
                it.byte_size,
                blob,
                it.rich_html,
                rtf,
            ],
        )?;
        stats.items += inserted;
    }

    Ok(stats)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp_db(name: &str) -> Connection {
        let dir = std::env::temp_dir().join(format!("tietie-db-test-{name}"));
        let _ = std::fs::remove_dir_all(&dir);
        open(&dir.join("test.sqlite")).expect("open test db")
    }

    fn item<'a>(hash: &'a str, content: &'a str, preview: &'a str) -> InsertItem<'a> {
        InsertItem {
            kind: "text",
            content,
            preview,
            meta: "",
            content_hash: hash,
            source_app: None,
            byte_size: 10,
            image_blob: None,
            rich_html: None,
            rich_rtf: None,
        }
    }

    fn item_s(hash: &str) -> InsertItem<'_> {
        item(hash, hash, hash)
    }

    #[test]
    fn upsert_dedupes_on_hash_and_bumps_count() {
        let conn = tmp_db("upsert");
        let id1 = upsert_item(&conn, item_s("h1"), true).unwrap();
        let id2 = upsert_item(&conn, item_s("h1"), true).unwrap();
        assert_eq!(id1, id2); // same hash → bump, not new row
        let n: i64 = conn
            .query_row("SELECT COUNT(*) FROM clip_item", [], |r| r.get(0))
            .unwrap();
        assert_eq!(n, 1);
        let used: i64 = conn
            .query_row(
                "SELECT use_count FROM clip_item WHERE id = ?1",
                params![id1],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(used, 1);
    }

    #[test]
    fn trim_respects_pinned_and_cap() {
        let conn = tmp_db("trim");
        for i in 0..10 {
            let id = upsert_item(&conn, item_s(&format!("h{i}")), true).unwrap();
            if i == 0 {
                conn.execute("UPDATE clip_item SET pinned = 1 WHERE id = ?1", params![id])
                    .unwrap();
            }
        }
        let removed = trim_history(&conn, 5).unwrap();
        // cap counts only unpinned rows: 9 unpinned → keep 5, drop 4;
        // the pinned oldest survives on top of the cap (by design)
        assert_eq!(removed, 4);
        let (n, pinned): (i64, i64) = conn
            .query_row(
                "SELECT COUNT(*), COALESCE(SUM(pinned),0) FROM clip_item",
                [],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        assert_eq!(n, 6);
        assert_eq!(pinned, 1); // oldest row is pinned and still here
    }

    #[test]
    fn migration_adds_rich_columns_to_old_schema() {
        let dir = std::env::temp_dir().join("tietie-db-test-migrate");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("old.sqlite");
        {
            // simulate a pre-rich-text database
            let conn = Connection::open(&path).unwrap();
            conn.execute_batch(
                "CREATE TABLE clip_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL, content TEXT NOT NULL,
                    preview TEXT NOT NULL DEFAULT '', meta TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
                    folder_id INTEGER, source_app TEXT,
                    created_at INTEGER NOT NULL, used_at INTEGER NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    byte_size INTEGER NOT NULL DEFAULT 0,
                    image_blob BLOB
                );",
            )
            .unwrap();
        }
        let conn = open(&path).unwrap(); // runs migrations
        conn.execute(
            "INSERT INTO clip_item (kind, content, preview, meta, content_hash,
                created_at, used_at, rich_html, rich_rtf)
             VALUES ('text','c','c','','x',1,1,'<b>hi</b>', X'7b7d')",
            [],
        )
        .unwrap(); // rich columns now exist
    }
}
