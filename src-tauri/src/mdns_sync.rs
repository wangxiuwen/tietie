//! LAN device discovery over mDNS, service `_tietie-sync._tcp` (direction 127).
//!
//! Uses the pure-Rust `mdns-sd` crate (no system Bonjour/Avahi dependency):
//! one daemon both registers this machine and browses the service; resolved
//! peers are kept in a shared snapshot the settings page can poll. The
//! daemon lives for the whole process — dropping it would unregister us.

use std::collections::HashMap;
use std::net::IpAddr;
use std::sync::{Arc, Mutex, OnceLock};

use mdns_sd::{ServiceDaemon, ServiceEvent, ServiceInfo};

pub const SERVICE: &str = "_tietie-sync._tcp.local.";
/// Reserved TCP port for the upcoming sync transport (direction 129);
/// discovery advertises it so peers can display address:port already.
pub const SYNC_PORT: u16 = 41784;

#[derive(serde::Serialize, Clone)]
pub struct Peer {
    /// instance label ("DESKTOP-ABC-tietie")
    pub instance: String,
    /// advertised host ("desp-abc.local")
    pub hostname: String,
    /// first resolved "ip:port"
    pub addr: String,
}

fn hostname_label() -> String {
    std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .unwrap_or_else(|_| "tietie".into())
        .to_lowercase()
}

/// Our advertised instance label ("<host>-tietie"), also used as the sync
/// sender identity (direction 129).
pub fn our_instance() -> String {
    format!("{}-tietie", hostname_label())
}

/// Best-effort LAN IP: ask the OS which source address it would route with.
fn local_ip() -> IpAddr {
    std::net::UdpSocket::bind("0.0.0.0:0")
        .and_then(|s| {
            let _ = s.connect("8.8.8.8:80");
            s.local_addr()
        })
        .map(|a| a.ip())
        .unwrap_or(IpAddr::from([127, 0, 0, 1]))
}

/// "instance._tietie-sync._tcp.local." → "instance"
fn instance_label(fullname: &str) -> String {
    fullname.split('.').next().unwrap_or(fullname).to_string()
}

pub struct Discovery {
    peers: Arc<Mutex<Vec<Peer>>>,
    /// kept alive so our registration lives as long as the process
    _daemon: ServiceDaemon,
}

impl Discovery {
    fn start() -> Option<Discovery> {
        let daemon = match ServiceDaemon::new() {
            Ok(d) => d,
            Err(e) => {
                log::warn!("mdns: daemon start failed: {e}");
                return None;
            }
        };
        let host = hostname_label();
        let instance = format!("{}-tietie", host);
        let host_local = format!("{}.local.", host);
        let info = match ServiceInfo::new(
            SERVICE,
            &instance,
            host_local.as_str(),
            local_ip(),
            SYNC_PORT,
            None::<HashMap<String, String>>,
        ) {
            Ok(i) => i,
            Err(e) => {
                log::warn!("mdns: service info failed: {e}");
                return None;
            }
        };
        if let Err(e) = daemon.register(info) {
            log::warn!("mdns: register failed: {e}");
            return None;
        }
        let receiver = match daemon.browse(SERVICE) {
            Ok(r) => r,
            Err(e) => {
                log::warn!("mdns: browse failed: {e}");
                return None;
            }
        };
        log::info!("mdns: discovery up as {instance} (port {SYNC_PORT})");
        let peers: Arc<Mutex<Vec<Peer>>> = Arc::new(Mutex::new(Vec::new()));
        let self_full = format!("{}.{}", instance, SERVICE);
        let sink = peers.clone();
        std::thread::spawn(move || {
            while let Ok(ev) = receiver.recv() {
                if let ServiceEvent::ServiceResolved(info) = ev {
                    if info.get_fullname().eq_ignore_ascii_case(&self_full) {
                        continue; // our own announcement
                    }
                    let label = instance_label(info.get_fullname());
                    let host = info.get_hostname().trim_end_matches('.').to_string();
                    let mut g = match sink.lock() {
                        Ok(g) => g,
                        Err(_) => return,
                    };
                    g.retain(|p| p.instance != label);
                    for addr in info.get_addresses() {
                        log::info!("mdns: peer {label} at {addr}:{}", info.get_port());
                        g.push(Peer {
                            instance: label.clone(),
                            hostname: host.clone(),
                            addr: format!("{}:{}", addr, info.get_port()),
                        });
                    }
                }
            }
        });
        Some(Discovery {
            peers,
            _daemon: daemon,
        })
    }

    pub fn snapshot(&self) -> Vec<Peer> {
        self.peers.lock().map(|g| g.clone()).unwrap_or_default()
    }
}

/// Process-wide discovery (starts lazily on first use; None if the mDNS
/// daemon could not start — the feature then reports an empty peer list).
pub fn shared() -> Option<&'static Discovery> {
    static DISCOVERY: OnceLock<Option<Discovery>> = OnceLock::new();
    DISCOVERY.get_or_init(Discovery::start).as_ref()
}
