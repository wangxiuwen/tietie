# 贴贴 (Tietie)

[English](./README.md) · 简体中文

> 漂亮、轻量、跨平台的剪切板管理器。

底部抽屉式弹出，全键盘操作，Tauri 2 + React + Rust，安装包 ~10 MB。专注做好一件事：**剪切板**。

## 功能

### 底部抽屉

- **底部抽屉** — `⌘⇧V` 从屏幕底部全宽滑出，毛玻璃面板覆盖在当前 app 上
- **紧凑列表模式** — 一键在卡片网格与单行列表间切换，省屏幕空间
- **自动分类** — 文本 / 链接 / 图片 / 代码 / 颜色，按内容启发式识别
- **用户文件夹** — 自定义彩色文件夹 chip，拖卡片到 chip 上直接归类
- **置顶** — 高频条目固定在最前（清理豁免）
- **内联编辑** — `⌘E` 在抽屉里直接改，不开新窗
- **全键盘** — `←/→` 切换，`↵` 粘贴，`⌘1-9` 直选，`⌘P` 置顶，`⌘D` 删除，`⌘↑` 挂绳，`⇧↑/↓` 扩展多选，`Menu` / `⇧F10` 右键菜单，`空格` 图片大图，`⌘R` 颜色复制 rgb()，`?` 键盘速查表
- **搜索** — `⌘F`；空格分词 AND，拼音首字母（`nz`→内存）、全拼（`neicun`→内存）、字母子序列（`tln`⊂turing-llm-next）三层匹配，命中高亮 + 使用频率加权排序

### 晾衣架

- 屏幕顶部一根绳子横贯左右，**真实 verlet 物理**——挂卡下沉、摘卡回弹
- 抽屉里的卡片**按住往上拖**、跟手幽灵跟到顶部松手挂上；挂着的卡**往下拖出绳区摘下**、**左右拖换位**
- 挂卡支持查看 / 复制 / 编辑 / 置顶，八色衣夹；`＋ 便签` 直接新建不经剪切板的便签；可选 **N 分钟定时提醒**，到时挂卡闪烁
- `Ctrl+Alt+H` 收起/展开，可见性跨重启保持

### 库与数据

- **Library 管理窗** — 全量表格式管理：列排序、使用统计（总数/类型分布/来源 Top）、多选批量删除、文本与 **Markdown 导出**（按类型分组、代码围栏）
- **颜色色板** — 颜色历史的色板网格视图，点击复制 hex
- **备份** — 一键 JSON 导出到「文档」并合并导入
- **敏感条目** — 标记 🔒 后以 AES-256-GCM + 机器派生密钥封装存储：DB 文件泄露也看不到内容（本机使用时透明解密）
- **数据管理** — 保留时长 永久/7/30 天、条目上限 200–3000、来源应用记录 + **黑名单**（密码管理器不入库）、夜间空闲自动回收缩文件

### 其它

- **快捷键全部可自定义** — 抽屉 / 截图 / 晾衣架三个全局热键按组合键捕获改绑；被占用时抽屉自动走降级链
- **双语界面** — 中/英文自动检测，字体三档，主题色四选
- **托盘面板** — 点托盘图标出可搜索的最近列表；Windows 任务栏跳转列表提供最近 5 条快速粘贴
- **开机自启** — 设置里一键开关
- **无障碍** — 列表框语义、可访问名全覆盖、键盘焦点环

### 默认快捷键

| 快捷键 | 动作 |
|---|---|
| `⌘⇧V` | 开关抽屉 |
| `⌘F` | 聚焦搜索 |
| `↵` | 粘贴选中项 |
| `⌘1`–`⌘9` / `⌘0` | 直选粘贴第 N 条 |
| `⌘E` / `⌘P` / `⌘D` | 编辑 / 置顶 / 删除 |
| `⌘↑` | 选中卡挂到晾衣架 |
| `⇧↑` `⇧↓` | 扩展多选 |
| `Menu` / `⇧F10` | 打开右键菜单 |
| `空格` | 选中图片卡大图 |
| `⌘R` | 颜色复制为 `rgb()` |
| `Tab` | 切换类型标签 |
| `?` | 键盘速查表 |
| `Esc` | 关闭浮层 / 抽屉 |

> **平台说明**：`⌘` 在 Windows 上映射 `Win`、Linux 上映射 `Super`（托盘菜单始终显示真实组合）。
> 截图热键 `Ctrl+Alt+4`：macOS 交互式框选（`screencapture`），Windows 全屏 GDI（含多显示器），
> Linux 依次尝试 `gnome-screenshot` / `spectacle` / `maim` / `scrot` / `import`。
> 粘贴 = 写剪切板 + 自动合成粘贴键：Windows 原生 `SendInput`；
> Linux X11 需要 `xdotool`（Wayland 禁止合成输入——只复制，设置里有检测提示）。

## 下载

[Releases](https://github.com/wangxiuwen/tietie/releases) 提供：

| 平台 | 格式 |
|---|---|
| macOS Apple Silicon | `Tietie_x.y.z_aarch64.dmg` |
| macOS Intel | `Tietie_x.y.z_x64.dmg` |
| Windows 10/11 | `Tietie_x.y.z_x64-setup.exe` / `.msi` |
| Linux | `tietie_x.y.z_amd64.deb` / `.AppImage` / `.rpm` |

> macOS：应用未签名。首次启动请在 *系统设置 → 隐私与安全性* 点「仍要打开」。

## 本地开发

需要 `Node 20+`、`Rust stable`。Linux 另需 `libwebkit2gtk-4.1-dev` 等依赖（见 CI 配置）。

```bash
npm install
npm run tauri:dev     # 热重载开发
npm test              # vitest：搜索 / i18n 对齐 / 颜色工具
npm run tauri:build   # 构建原生安装包
```

Rust 侧：`cargo test --lib` 跑 db / crypt / 日志 / 轮询测试套件（CI 三平台跑 fmt + clippy + 测试）。

## 架构

```
tietie/
├── src/                    # React 前端
│   ├── App.tsx             # 抽屉主面板（含紧凑列表）
│   ├── Clothesline.tsx     # 物理绳 + 挂卡便签
│   ├── Library.tsx         # 管理表 / 统计 / 色板
│   ├── Settings.tsx        # 独立设置窗口
│   └── styles.css
├── src-tauri/              # Rust 后端
│   └── src/
│       ├── lib.rs          # 入口、托盘、热键、IPC、跳转列表
│       ├── db.rs           # SQLite（rusqlite、WAL、迁移）
│       ├── clipboard.rs    # 自适应轮询 600ms→2s + 内容分类
│       └── crypt.rs        # 敏感条目 AES-256-GCM 封装
└── .github/workflows/      # 三平台 CI（fmt / clippy / 测试）
```

**性能取舍**
- Rust 后端 + React 前端
- SQLite WAL，唯一索引去重
- 自适应轮询：活动后 600ms，空闲逐步放缓到 2s（省 CPU；macOS 无公开变更通知 API）
- `tauri.conf` lto + codegen=1 + opt-level=s + strip → 发布二进制 ~6–8 MB

## Roadmap

- [x] Library 管理窗、设置窗、备份、双语 —— 均已在 0.1.x 交付
- [ ] 机器级快速取用：文件与应用搜索源并入同一抽屉
- [ ] WebDAV / iCloud 同步

## License

MIT
