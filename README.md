# Tietie (贴贴)

English · [简体中文](./README.zh-CN.md)

> A beautiful, lightweight, cross-platform clipboard manager.

Bottom-drawer popup, all-keyboard driven, Tauri 2 + React + Rust, ~10 MB installer. Does one thing well: **clipboard**.

## Features

### The drawer

- **Bottom drawer** — `⌘⇧V` slides up a full-width frosted-glass panel over the current app
- **Compact list mode** — one toggle swaps the card grid for a single-line list when screen estate matters
- **Auto categorization** — text / link / image / code / color, detected by content heuristics
- **User folders** — colored chips; drag a card onto a chip to file it
- **Pin** — keep frequently-used items at the front (pins survive retention cleanup)
- **Inline edit** — `⌘E` edits in place, no new window
- **Full keyboard** — `←/→` navigate, `↵` paste, `⌘1-9` pick directly, `⌘P` pin, `⌘D` delete, `⌘↑` hang on the line, `⇧↑/↓` extend multi-select, `Menu` / `⇧F10` context menu, `Space` zoom the selected image, `⌘R` copy a color as `rgb()`, `?` cheatsheet
- **Search** — `⌘F`; token-AND across text, pinyin initials (`nz` → 内存), full pinyin (`neicun` → 内存) and letter subsequence (`tln` ⊂ turing-llm-next); hit highlighting and frequency-weighted ordering

### The clothesline (晾衣架)

- A rope across the top of the screen with **real verlet physics** — it sags under the cards hanging on it and springs back when you take one off
- Drag a drawer card upward to hang it (a ghost chip follows the cursor); drag a hanging card **down out of the rope zone to take it off**, or **sideways to reorder**
- Hanging cards: click to view / copy / edit / pin, eight clothespin colors, `＋ 便签` creates a brand-new sticky note that never touched the clipboard, optional **N-minute reminders** that flash the card when due
- `Ctrl+Alt+H` collapses / expands; visibility persists across restarts

### Library & data

- **Library window** — full-table management view: column sorting, usage stats (totals / type distribution / top sources), multi-select batch delete, text & **Markdown export** (kind-grouped, code fenced)
- **Color swatches** — palette grid view over color history, click to copy the hex
- **Backups** — one-click JSON export to Documents and merge-on-import
- **Sensitive items** — mark any entry 🔒 and it is stored AES-256-GCM sealed with a machine-derived key: a leaked DB file reveals nothing (transparently decrypted for use on this machine)
- **Retention** — keep-forever / 7 / 30 days, history caps (200–3000), per-source app tracking with a **blacklist** (password managers never land in history), nightly idle reclaim that trims and shrinks the file

### Everything else

- **Rebindable hotkeys** — drawer / screenshot / clothesline global shortcuts, press-combo capture in settings; the drawer walks a fallback chain when its combo is taken
- **Bilingual UI** — Chinese / English with system detection, three font sizes, four accent colors
- **Tray panel** — click the tray icon for a searchable recent list; taskbar jump list (Windows) offers the last 5 clips for quick paste
- **Launch at login** — one toggle in settings
- **Accessibility** — listbox semantics, labeled controls, visible keyboard focus rings

### Default shortcuts

| Shortcut | Action |
|---|---|
| `⌘⇧V` | Toggle drawer |
| `⌘F` | Focus search |
| `↵` | Paste selected |
| `⌘1`–`⌘9` / `⌘0` | Paste the N-th item directly |
| `⌘E` / `⌘P` / `⌘D` | Edit / pin / delete |
| `⌘↑` | Hang the selected card on the line |
| `⇧↑` `⇧↓` | Extend multi-selection |
| `Menu` / `⇧F10` | Open the context menu |
| `Space` | Zoom the selected image |
| `⌘R` | Copy color as `rgb()` |
| `Tab` | Switch type tabs |
| `?` | Keyboard cheatsheet |
| `Esc` | Close overlay / drawer |

> **Platform notes**: `⌘` maps to `Win` on Windows and `Super` on Linux (the tray menu always shows the real combo).
> Screenshot hotkey `Ctrl+Alt+4`: interactive area select on macOS (`screencapture`), full screen on Windows (GDI, all monitors),
> on Linux it tries `gnome-screenshot` / `spectacle` / `maim` / `scrot` / `import` in order.
> Paste writes the clipboard and synthesizes the paste keystroke automatically: native `SendInput` on Windows;
> X11 needs `xdotool` on Linux (Wayland forbids synthetic input — copy-only fallback, detected and surfaced in settings).

## Download

[Releases](https://github.com/wangxiuwen/tietie/releases) ships:

| Platform | Format |
|---|---|
| macOS Apple Silicon | `Tietie_x.y.z_aarch64.dmg` |
| macOS Intel | `Tietie_x.y.z_x64.dmg` |
| Windows 10/11 | `Tietie_x.y.z_x64-setup.exe` / `.msi` |
| Linux | `tietie_x.y.z_amd64.deb` / `.AppImage` / `.rpm` |

> macOS: the app is unsigned. On first launch open *System Settings → Privacy & Security* and click *Open Anyway*.

## Local development

Requires `Node 20+`, `Rust stable`. Linux additionally needs `libwebkit2gtk-4.1-dev` and friends (see the CI files).

```bash
npm install
npm run tauri:dev     # dev with hot reload
npm test              # vitest: search / i18n parity / color utils
npm run tauri:build   # build native installer
```

Rust side: `cargo test --lib` runs the db / crypt / logger / backoff suites (CI runs fmt + clippy + tests on all three platforms).

## Architecture

```
tietie/
├── src/                    # React frontend
│   ├── App.tsx             # drawer main panel (+ compact list mode)
│   ├── Clothesline.tsx     # physics rope + hanging memos
│   ├── Library.tsx         # management table / stats / swatches
│   ├── Settings.tsx        # dedicated settings window
│   └── styles.css
├── src-tauri/              # Rust backend
│   └── src/
│       ├── lib.rs          # entry, tray, hotkeys, IPC, jump list
│       ├── db.rs           # SQLite (rusqlite, WAL, migrations)
│       ├── clipboard.rs    # adaptive polling 600ms→2s + classification
│       └── crypt.rs        # AES-256-GCM sealing for sensitive items
└── .github/workflows/      # tri-platform CI (fmt / clippy / tests)
```

**Performance trade-offs**
- Rust backend, React frontend
- SQLite WAL, unique index for dedup
- Adaptive clipboard polling: 600 ms after activity, easing to 2 s when idle (CPU-friendly; macOS has no public change-notification API)
- `tauri.conf` lto + codegen=1 + opt-level=s + strip → release binary ~6–8 MB

## Roadmap

- [x] Library window, settings window, backups, i18n — all shipped in 0.1.x
- [ ] Machine-wide quick access: file & app search sources inside the same drawer
- [ ] WebDAV / iCloud sync

## License

MIT
