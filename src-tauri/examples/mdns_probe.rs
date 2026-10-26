//! Dev probe for direction 127: advertises a SECOND `_tietie-sync._tcp`
//! instance so the running app's device list has a peer to discover.
//! Run: cargo run --example mdns_probe -- <label> [seconds] [--browse]
//! With --browse it also resolves other advertisers and prints them —
//! two probes with --browse on one machine prove the mDNS path both ways.

use std::collections::HashMap;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let browse = args.iter().any(|a| a == "--browse");
    let pos: Vec<&String> = args.iter().filter(|a| a.as_str() != "--browse").collect();
    let label = pos.first().map(|s| s.as_str()).unwrap_or("probe-device");
    let secs: u64 = pos.get(1).and_then(|s| s.parse().ok()).unwrap_or(60);
    let daemon = mdns_sd::ServiceDaemon::new().expect("daemon");
    let host_local = format!("{}.local.", label);
    let instance = format!("{}-tietie", label);
    // loopback addresses are never resolved over mDNS — advertise the LAN IP
    // the OS would route with, same trick the app uses
    let lan_ip = std::net::UdpSocket::bind("0.0.0.0:0")
        .and_then(|s| {
            let _ = s.connect("8.8.8.8:80");
            s.local_addr()
        })
        .map(|a| a.ip())
        .unwrap_or(std::net::IpAddr::from([127, 0, 0, 1]));
    let info = mdns_sd::ServiceInfo::new(
        "_tietie-sync._tcp.local.",
        instance.as_str(),
        host_local.as_str(),
        lan_ip,
        41784,
        None::<HashMap<String, String>>,
    )
    .expect("service info");
    daemon.register(info).expect("register");
    println!("probing as {instance} for {secs}s");
    if browse {
        let rx = daemon.browse("_tietie-sync._tcp.local.").expect("browse");
        let self_full = format!("{instance}._tietie-sync._tcp.local.");
        std::thread::spawn(move || {
            while let Ok(ev) = rx.recv() {
                if let mdns_sd::ServiceEvent::ServiceResolved(i) = ev {
                    if i.get_fullname().eq_ignore_ascii_case(&self_full) {
                        continue;
                    }
                    println!(
                        "RESOLVED {} -> {:?}:{}",
                        i.get_fullname(),
                        i.get_addresses(),
                        i.get_port()
                    );
                }
            }
        });
    }
    std::thread::sleep(std::time::Duration::from_secs(secs));
}
