//! File logger with size-based rotation: `tietie.log` in the app local data
//! dir, rotated to `tietie.log.1` past MAX_BYTES (the old .1 is dropped).
//! Releases have no console, so stderr-only logging was invisible in the
//! field — this keeps a small always-on diagnostic trail.

use log::{LevelFilter, Log, Metadata, Record};
use parking_lot::Mutex;
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

pub const MAX_BYTES: u64 = 512 * 1024;

pub struct FileLogger {
    file: Mutex<File>,
    path: PathBuf,
    level: LevelFilter,
}

impl FileLogger {
    /// Open (creating) the log file; rotates first if it is already huge.
    pub fn open(path: PathBuf, level: LevelFilter) -> std::io::Result<Self> {
        if let Ok(md) = std::fs::metadata(&path) {
            if md.len() >= MAX_BYTES {
                let _ = rotate(&path);
            }
        }
        let file = OpenOptions::new().create(true).append(true).open(&path)?;
        Ok(FileLogger {
            file: Mutex::new(file),
            path,
            level,
        })
    }
}

/// Rotate: log → log.1 (previous .1 is deleted). Visible for tests.
pub fn rotate(path: &Path) -> std::io::Result<()> {
    let prev = path.with_extension("log.1");
    if prev.exists() {
        std::fs::remove_file(&prev)?;
    }
    std::fs::rename(path, prev)
}

fn ts() -> String {
    let d = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let secs = d.as_secs();
    let ms = d.subsec_millis();
    let days = secs / 86400;
    let rem = secs % 86400;
    let (h, mi, s) = (rem / 3600, (rem % 3600) / 60, rem % 60);
    // civil-from-days for a readable UTC stamp
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    format!("{y:04}-{m:02}-{day:02} {h:02}:{mi:02}:{s:02}.{ms:03}")
}

impl Log for FileLogger {
    fn enabled(&self, metadata: &Metadata) -> bool {
        metadata.level() <= self.level
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        let mut f = self.file.lock();
        // rotate between writes when the file grew past the cap
        if let Ok(md) = f.metadata() {
            if md.len() >= MAX_BYTES {
                let _ = rotate(&self.path);
                if let Ok(nf) = OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&self.path)
                {
                    *f = nf;
                }
            }
        }
        let _ = writeln!(
            f,
            "{} {:5} [{}] {}",
            ts(),
            record.level(),
            record.target(),
            record.args()
        );
    }

    fn flush(&self) {
        let _ = self.file.lock().flush();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rotate_renames_and_drops_old() {
        let dir = std::env::temp_dir().join("tietie-log-test");
        std::fs::create_dir_all(&dir).unwrap();
        let log = dir.join("tietie.log");
        let old = dir.join("tietie.log.1");

        std::fs::write(&old, "previous").unwrap();
        std::fs::write(&log, "current").unwrap();

        rotate(&log).unwrap();
        assert!(log.metadata().is_err()); // moved away
        assert_eq!(std::fs::read_to_string(&old).unwrap(), "current");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
