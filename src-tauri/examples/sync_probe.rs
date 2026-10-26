//! Dev probe for direction 129: speaks the sealed-frame sync protocol as a
//! fake paired device.
//!   send   <addr> <sender> <token> <content>   -> push one frame to the app
//!   listen <port> <sender> <token>             -> accept one frame, print it
//! Frame: 4-byte BE length + JSON envelope {sender, nonce(b64), ct(b64)};
//! key = SHA-256(token || "tietie-sync-v1"), AAD = sender, AES-256-GCM.

use std::io::{Read, Write};
use std::net::TcpStream;

use aes_gcm::aead::{Aead, KeyInit, Payload};
use aes_gcm::{Aes256Gcm, Nonce};
use base64::Engine as _;
use sha2::{Digest, Sha256};

const LABEL: &[u8] = b"tietie-sync-v1";

fn key_of(token: &str) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(token.as_bytes());
    h.update(LABEL);
    h.finalize().into()
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let b64 = &base64::engine::general_purpose::STANDARD;
    match a[0].as_str() {
        "send" => {
            let addr = &a[1];
            let sender = &a[2];
            let key = key_of(&a[3]);
            let content = &a[4];
            let payload = serde_json::json!({
                "kind": "text",
                "content": content,
                "ts": 0,
            });
            let pt = serde_json::to_vec(&payload).unwrap();
            let mut nb = [0u8; 12];
            _ = getrandom::fill(&mut nb);
            let cipher = Aes256Gcm::new_from_slice(&key).unwrap();
            let ct = cipher
                .encrypt(
                    Nonce::from_slice(&nb),
                    Payload {
                        msg: &pt,
                        aad: sender.as_bytes(),
                    },
                )
                .unwrap();
            let env = serde_json::json!({
                "sender": sender,
                "nonce": b64.encode(nb),
                "ct": b64.encode(ct),
            });
            let body = serde_json::to_vec(&env).unwrap();
            let mut s = TcpStream::connect(addr).expect("connect");
            s.write_all(&(body.len() as u32).to_be_bytes()).unwrap();
            s.write_all(&body).unwrap();
            s.flush().unwrap();
            println!("SENT {} bytes to {addr}", body.len());
        }
        "listen" => {
            let port: u16 = a[1].parse().unwrap();
            let key = key_of(&a[3]);
            let listener = std::net::TcpListener::bind(("0.0.0.0", port)).expect("bind");
            println!("LISTENING {port}");
            let (mut s, _) = listener.accept().expect("accept");
            let mut lb = [0u8; 4];
            s.read_exact(&mut lb).unwrap();
            let mut body = vec![0u8; u32::from_be_bytes(lb) as usize];
            s.read_exact(&mut body).unwrap();
            let env: serde_json::Value = serde_json::from_slice(&body).unwrap();
            let sender = env["sender"].as_str().unwrap_or("?").to_string();
            let nb: Vec<u8> = b64.decode(env["nonce"].as_str().unwrap()).unwrap();
            let ct: Vec<u8> = b64.decode(env["ct"].as_str().unwrap()).unwrap();
            let cipher = Aes256Gcm::new_from_slice(&key).unwrap();
            match cipher.decrypt(
                Nonce::from_slice(&nb),
                Payload {
                    msg: &ct,
                    aad: sender.as_bytes(),
                },
            ) {
                Ok(pt) => {
                    let p: serde_json::Value = serde_json::from_slice(&pt).unwrap();
                    println!(
                        "RECEIVED from {sender} kind={} content={}",
                        p["kind"].as_str().unwrap_or("?"),
                        p["content"].as_str().unwrap_or("?")
                    );
                }
                Err(_) => println!("DECRYPT_FAILED from {sender}"),
            }
        }
        _ => eprintln!(
            "usage: send <addr> <sender> <token> <content> | listen <port> <sender> <token>"
        ),
    }
}
