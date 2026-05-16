# 贴贴 (Tietie)

> 漂亮、轻量、跨平台的剪切板管理器 —— 加上一个菜单栏收纳/启动器面板。

底部抽屉式弹出，全键盘操作，Tauri 2 + React + Rust，安装包 ~10 MB。

## ✨ 功能

### 🗂 剪切板管理
- **底部抽屉** — `⌘⇧V` 从屏幕底部全宽滑出，毛玻璃面板覆盖在当前 app 上
- **自动分类** — 文本 / 链接 / 图片 / 代码 / 颜色，按内容启发式识别
- **用户文件夹** — 自定义彩色文件夹归类（chip 横排）
- **置顶** — 高频条目固定在最前
- **内联编辑** — `⌘E` 在抽屉里直接改，不开新窗
- **全键盘** — `←/→` 切换，`↵` 粘贴，`⌘1-9` 直选，`⌘P` 置顶，`⌘D` 删除
- **历史搜索** — `⌘F` 全文搜
- **图片支持** — PNG 缩略图 + 完整数据，粘贴回还原

### 🎯 系统托盘 + 启动器收纳
- **托盘小窗** — 点托盘图标，弹出 320×460 popover
- **最近 5 条** — 一键复制回剪切板
- **8 个启动槽** — 固定常用 App / 文件夹 / URL，作为"被刘海挡住的菜单栏图标"的替代方案（让那些 app 退出，从这里启动）
- **快捷退出/设置** — 底部按钮

### ⌨️ 默认快捷键
| 快捷键 | 动作 |
|---|---|
| `⌘⇧V` | 唤起 / 关闭抽屉 |
| `⌘F` | 聚焦搜索 |
| `⌘E` | 编辑当前条 |
| `⌘P` | 置顶 |
| `⌘D` | 删除 |
| `⌘1`～`⌘9` | 直接粘贴第 N 条 |
| `←` `→` `↵` | 选择 + 粘贴 |
| `Tab` | 切换类型 tab |
| `Esc` | 关闭抽屉 |

## 📦 下载

[Releases 页](https://github.com/wangxiuwen/tietie/releases) 提供：

| 平台 | 包格式 |
|---|---|
| macOS Apple Silicon | `贴贴_x.y.z_aarch64.dmg` |
| macOS Intel | `贴贴_x.y.z_x64.dmg` |
| Windows 10/11 | `贴贴_x.y.z_x64-setup.exe` / `.msi` |
| Linux | `tietie_x.y.z_amd64.deb` / `.AppImage` |

## 🛠 本地开发

依赖：`Node 20+`、`Rust stable`，Linux 还需要 `libwebkit2gtk-4.1-dev` 等（详见 CI 文件）。

```bash
npm install
npm run tauri:dev          # 开发热重载
npm run tauri:build        # 出本平台安装包
```

## 🏗 架构

```
tietie/
├── src/                    # React 前端
│   ├── App.tsx             # 抽屉主面板
│   ├── TrayPopover.tsx     # 托盘 mini 面板
│   └── styles.css
├── src-tauri/              # Rust 后端
│   └── src/
│       ├── lib.rs          # 入口、托盘、热键、IPC
│       ├── db.rs           # SQLite (rusqlite, bundled)
│       └── clipboard.rs    # 600ms 轮询 + 内容分类
└── .github/workflows/      # CI 三平台出包
```

**性能取舍**
- 后端 Rust，前端 React (~170 KB gzipped)
- SQLite WAL，唯一索引去重
- 600ms 剪切板轮询（macOS 没有官方 change notification API；用 polling 比 NSPasteboard.changeCount 监听简单且跨平台）
- `tauri.conf` lto + codegen=1 + opt-level=s + strip，目标 release 二进制 ~6-8 MB

## 🗺 路线图

- [x] **v0.1** — 剪切板抽屉 + 自动分类 + 托盘 + 启动槽
- [ ] **v0.2** — 完整 Library 全屏管理窗（mockup 4 号屏）
- [ ] **v0.2** — 设置面板（mockup 5 号屏） + 拦截 ⌘V 长按
- [ ] **v0.3** — iCloud / WebDAV 同步
- [ ] **v0.4** — Bartender 式菜单栏图标接管 (macOS-only, 需要 Accessibility 权限 + AppKit FFI)

## 📜 License

MIT
