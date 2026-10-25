//! At-rest encryption for manually-marked sensitive clip items
//! (direction 54). AES-256-GCM; the key is derived from machine identity
//! (hostname + username) — no password, no prompt. This protects the DB
//! FILE if it leaks (backup export, sync, copy), NOT someone using this
//! machine: the app itself decrypts transparently.

use aes_gcm::aead::{Aead, KeyInit};
use aes_gcm::{Aes256Gcm, Nonce};
use sha2::{Digest, Sha256};

/// Domain separation for the key derivation (bump to rotate the key).
const SALT: &[u8] = b"tietie-sensitive-v1";
/// Prefix marking sealed values; `enc1:` + base64(nonce ‖ ciphertext).
const PREFIX: &str = "enc1:";
const NONCE_LEN: usize = 12;

fn machine_key() -> [u8; 32] {
    let host = std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .unwrap_or_default();
    let user = std::env::var("USERNAME")
        .or_else(|_| std::env::var("USER"))
        .unwrap_or_default();
    let mut h = Sha256::new();
    h.update(SALT);
    h.update(host.as_bytes());
    h.update(b"\x1f");
    h.update(user.as_bytes());
    h.finalize().into()
}

fn cipher() -> Aes256Gcm {
    Aes256Gcm::new_from_slice(&machine_key()).expect("32-byte key")
}

fn random_nonce() -> [u8; NONCE_LEN] {
    let mut buf = [0u8; NONCE_LEN];
    getrandom::fill(&mut buf).expect("os rng");
    buf
}

/// Seal a text value → `enc1:<base64(nonce ‖ ct)>`. Idempotent on already
/// sealed input (returns it unchanged).
pub fn seal_str(plain: &str) -> String {
    if plain.starts_with(PREFIX) {
        return plain.to_string();
    }
    let nonce = random_nonce();
    let ct = cipher()
        .encrypt(Nonce::from_slice(&nonce), plain.as_bytes())
        .expect("aes-gcm encrypt");
    let mut blob = nonce.to_vec();
    blob.extend_from_slice(&ct);
    format!("{PREFIX}{}", base64_encode(&blob))
}

/// Open a sealed text value. Returns None for unsealed input or when the
/// key does not match (e.g. file copied from another machine).
pub fn open_str(sealed: &str) -> Option<String> {
    if !sealed.starts_with(PREFIX) {
        return None;
    }
    let blob = base64_decode(sealed.trim_start_matches(PREFIX))?;
    if blob.len() <= NONCE_LEN {
        return None;
    }
    let (nonce, ct) = blob.split_at(NONCE_LEN);
    let plain = cipher().decrypt(Nonce::from_slice(nonce), ct).ok()?;
    String::from_utf8(plain).ok()
}

/// Seal binary columns (image blobs): raw `enc1:` magic + nonce + ct.
pub fn seal_bytes(plain: &[u8]) -> Vec<u8> {
    let mut magic = PREFIX.as_bytes().to_vec();
    let nonce = random_nonce();
    let ct = cipher()
        .encrypt(Nonce::from_slice(&nonce), plain)
        .expect("aes-gcm encrypt");
    magic.extend_from_slice(&nonce);
    magic.extend_from_slice(&ct);
    magic
}

/// Binary counterpart of [`open_str`]. None when not sealed or key mismatch.
pub fn open_bytes(sealed: &[u8]) -> Option<Vec<u8>> {
    if !sealed.starts_with(PREFIX.as_bytes()) {
        return None;
    }
    let body = &sealed[PREFIX.len()..];
    if body.len() <= NONCE_LEN {
        return None;
    }
    let (nonce, ct) = body.split_at(NONCE_LEN);
    cipher().decrypt(Nonce::from_slice(nonce), ct).ok()
}

fn base64_encode(data: &[u8]) -> String {
    use base64::{engine::general_purpose, Engine as _};
    general_purpose::STANDARD.encode(data)
}

fn base64_decode(s: &str) -> Option<Vec<u8>> {
    use base64::{engine::general_purpose, Engine as _};
    general_purpose::STANDARD.decode(s).ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn str_round_trip() {
        let sealed = seal_str("hunter2-密码");
        assert!(sealed.starts_with("enc1:"));
        assert!(!sealed.contains("hunter2"));
        assert_eq!(open_str(&sealed).as_deref(), Some("hunter2-密码"));
    }

    #[test]
    fn bytes_round_trip() {
        let sealed = seal_bytes(&[1, 2, 3, 4, 5]);
        assert!(sealed.starts_with(b"enc1:"));
        assert_eq!(open_bytes(&sealed).as_deref(), Some(&[1u8, 2, 3, 4, 5][..]));
    }

    #[test]
    fn wrong_key_fails_and_plaintext_passes_through() {
        // unsealed input → None (not sealed)
        assert_eq!(open_str("plain text"), None);
        assert_eq!(open_bytes(b"plain bytes"), None);
        // a ciphertext sealed under a different key fails to open
        let foreign = {
            let key = [7u8; 32];
            let c = Aes256Gcm::new_from_slice(&key).unwrap();
            let n = [0u8; NONCE_LEN];
            let ct = c
                .encrypt(Nonce::from_slice(&n), b"secret".as_slice())
                .unwrap();
            let mut b = n.to_vec();
            b.extend_from_slice(&ct);
            format!("{PREFIX}{}", base64_encode(&b))
        };
        assert_eq!(open_str(&foreign), None);
        // sealing is idempotent
        let once = seal_str("x");
        assert_eq!(seal_str(&once), once);
    }
}
