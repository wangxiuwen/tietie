# Changelog

> 由 docs/ITERATION_BACKLOG.md 的迭代记录生成——`py -3 scripts/gen_changelog.py`，请勿手改。


## 2026-10-27

- **下线** `TBD` 挂绳/晾衣架整体下线（用户决定「先不要了，有点乱套」）：conf 移除 clothesline 窗口+热键不注册+托盘删项+抽屉拖挂手势/MOD+↑/批量挂绳钮/右键挂绳项/速查行全移除；便签数据保留在库（导出/提醒 toast 不受影响），恢复=回滚本提交 |

- **182** [`d0e7b93`](https://github.com/wangxiuwen/tietie/commit/d0e7b93) 颜色筛选 localStorage 持久（选色即存/全部即清，惰性初始化恢复），杀进程重启实测 active 色点跨会话恢复后还原

- **181** [`2c33ad4`](https://github.com/wangxiuwen/tietie/commit/2c33ad4) ⌘N 徽章随自动翻页循环（badgeBase=(pageCount-1)*PAGE 经 Row 下传，⌘数字快取同步映射），实测 0-9 → 30-39 Ctrl1 重新起算

- **180** [`9532d72`](https://github.com/wangxiuwen/tietie/commit/9532d72) Library 表格 Ctrl+A 全选当前过滤集（复用头部全选框 toggle 语义：全选态再按即清），146 行实测全选/全清/表头同步

- **179** [`75f2521`](https://github.com/wangxiuwen/tietie/commit/75f2521) 已具备收口：诊断导出后 reveal 自方向134 即在；命令级实证产物落盘+reveal_path Ok，产物已删；本轮池<3 先扩池 181-185

- **178** [`b01980b`](https://github.com/wangxiuwen/tietie/commit/b01980b) 详情按钮组加「复制（去格式）」（复用 plainTextOf+✓ 反馈通道，i18n 键复用 150），可信点击实测剪贴板=剥标记全文且 URL 保留

- **177** [`3b52e30`](https://github.com/wangxiuwen/tietie/commit/3b52e30) 抽屉卡片列表按本地日插 .day-sep 分隔行（今天/昨天/M/D，Fragment 不扰选择序），144 卡实测 6 条分隔数量文案顺序位置全对

- **176** [`7beab9a`](https://github.com/wangxiuwen/tietie/commit/7beab9a) 托盘行右键菜单加「备注…」→ 搜索框下行内编辑器（Enter 存/Esc 取消，复用 set_item_note），右键-注入-回车-落库-清空全链实测

- **175** [`b8fe04e`](https://github.com/wangxiuwen/tietie/commit/b8fe04e) 空态在拖卡引导后补行内「或点这里新建一张」链接（点击即开 composer，颜色筛选时空态保持原样），合成点击实测开/关零残留

- **174** [`a3bc0f7`](https://github.com/wangxiuwen/tietie/commit/a3bc0f7) 已具备收口：版本号点击复制自方向96 即在（含 ✓ 反馈）；可信点击实测剪贴板精确等于 app_version 全串，快照还原；本轮池<3 先扩池 176-180

- **173** [`c055834`](https://github.com/wangxiuwen/tietie/commit/c055834) 文件夹 chip 双击折叠为纯色点（title 保留名），折叠态 data-folder-id 仍在故拖放照常收入；可信指针拖拽实测拖到 16px 宽折叠 chip → 条目 folder_id 精确落夹后全还原

- **172** [`7a44567`](https://github.com/wangxiuwen/tietie/commit/7a44567) 到点便签托盘角标（运行时像素画红圆+3x5 数字，set_tray_badge 命令，10 分钟未读窗口），日志链路实测 badge→1/→0

- **171** [`767094f`](https://github.com/wangxiuwen/tietie/commit/767094f) 抽屉提交历史镜像 localStorage、托盘空查询 ↑ 召回（连按走更旧，打字/↓ 退出），跨窗共享实测 甲乙两连召回后快照还原

- **170** [`c9c3f53`](https://github.com/wangxiuwen/tietie/commit/c9c3f53) 已具备收口：Library 行 title 全文自方向123 即在（含遮蔽抑制）；实证 143 行中长行显示 80 字、title 承载 1106 字全文、遮罩行 title 抑制

- **169** [`6fbdae6`](https://github.com/wangxiuwen/tietie/commit/6fbdae6) 批量栏所选含敏感项时显示 ⚠ N 🔒 橙色警示（title 说明批量操作绕过遮蔽），取消敏感项即隐；真机标记敏感+Ctrl双选断言后全还原

- **168** [`18b1627`](https://github.com/wangxiuwen/tietie/commit/18b1627) 托盘行 title 补 fmtBytes 字节数（备注行「备注 · 大小」无备注纯大小），与桥 byte_size 逐行对照 5/5 通过

- **167** [`c7c057a`](https://github.com/wangxiuwen/tietie/commit/c7c057a) 详情数字键换色解除色板悬停门槛（输入框打字守卫保留），顺手修 viewing 陈旧快照（详情即时反映换色）；真机 key3 换绿+active 同步+输入框内 key5 不换色实测

- **166** [`c87c3b8`](https://github.com/wangxiuwen/tietie/commit/c87c3b8) 域名徽章 span→button（onSearchTerm 三层下传，stopPropagation 不触发选中），点击=填域名入搜索框+聚焦；真机实测 open.rokid.com 徽章点击后仅剩该域链接卡

- **165** [`420f268`](https://github.com/wangxiuwen/tietie/commit/420f268) 搜索无结果空态 💡 轮换五条使用技巧（模块级游标每次进空态 +1，文案全部来自真实功能），真机两 miss 轮换不同条、有结果无空态实测

- **164** [`7253748`](https://github.com/wangxiuwen/tietie/commit/7253748) export_memos md 按衣夹色分节（## 色名 N 张，首现序置顶带头；color_name 8 色板中文名+hex 兜底），txt 平铺不变；双色 fixtures 真机实测橙/绿各一节

- **163** [`5055fa9`](https://github.com/wangxiuwen/tietie/commit/5055fa9) 已具备收口：settings-open 监听自 141 起即刷同步日志；msg_send→WSL 对端 unreachable ⚠ 事件，藏/开设置窗（不点手动刷新）实测事件自动呈现后清理探针

- **162** [`89ebfbc`](https://github.com/wangxiuwen/tietie/commit/89ebfbc) 抽屉卡 onMouseDown button=1 直接 onPin（防自动滚动），与右键菜单/托盘同路径；中键两击 pinned 翻转实测（抽屉窗可信中键被 WebView2 吞，合成输入验证）

- **161** [`86c068e`](https://github.com/wangxiuwen/tietie/commit/86c068e) 抽屉搜索框 × 清空钮（流内插入避让 ⌘F kbd，mousedown preventDefault 保焦点+点击清空复焦），真机三态实测含 img: 前缀顺带回归

- **159** [`dafeee1`](https://github.com/wangxiuwen/tietie/commit/dafeee1) 模板 chip 按使用计数稳定降序（bumpTemplate+addTemplate 双处排序不变式），常用前置/0使用不插队/追平不跳位真机实测；连点同 chip 的 React bailout 用 render tick 兜住

- **158** [`752f969`](https://github.com/wangxiuwen/tietie/commit/752f969) 设置页一键恢复出厂热键（新 hotkey_defaults 命令+恢复默认钮，逐键容错占用保现役），真机实测 clothesline/screenshot 回出厂+面板刷新；本轮池<3 先扩池 161-165

- **157** [`c63d34d`](https://github.com/wangxiuwen/tietie/commit/c63d34d) 搜索 text:/img:/link: 类型前缀（matchQuery 加 kind 参数，抽屉+托盘双接线），前缀+词 AND 组合，vitest +14 断言 + 真机五组过滤实测

- **156** [`a295b19`](https://github.com/wangxiuwen/tietie/commit/a295b19) 新便签默认沿用上次提交颜色（会话级 lastMemoColor，null 语义保持默认蓝），composer B 选中态+落库色值双证

- **155** [`8b42457`](https://github.com/wangxiuwen/tietie/commit/8b42457) 托盘行中键直接置顶/取消（onMouseDown button=1 拦截防自动滚动），三处 Row 全接线；可信中键两连击实测 pinned 翻转且置顶分区随之出现/消失

- **160** [`fa0ad86`](https://github.com/wangxiuwen/tietie/commit/fa0ad86) 类型筛选行去彩点：dot-sm/TYPE_TABS.dot 移除（用户反馈彩点乱），标签+数量+激活高亮保留 |

- **154** [`a3ba8cf`](https://github.com/wangxiuwen/tietie/commit/a3ba8cf) 导出便签附备注列：md 行内 📝+备注、txt 加「备注：」行（空备注不输出），产品路径挂签写备注双格式实测后清理还原

- **153** [`4da8813`](https://github.com/wangxiuwen/tietie/commit/4da8813) 批量挂绳 >5 条两段式确认（首点变红「确认挂绳？」、3s 超时解除、复选变化即重置），armed 不执行/超时解除/确认 +6 全链真机实测

- **152** [`17366a1`](https://github.com/wangxiuwen/tietie/commit/17366a1) 热键行保存系统占用组合后行上持久红标（复用 settings-tag.err，101 的录制中黄警不回归），改键→红标→还原全链真机实测 |

- **151** `零改动` 已具备收口：置顶区标题随 pinnedAll.length>0 条件渲染（方向103），真机 pinned=0 实测置顶标题/分区不渲染、最近区正常 |

- **150** [`db5aa4e`](https://github.com/wangxiuwen/tietie/commit/db5aa4e) 挂卡右键新增「复制（去格式）」：剥 **粗**/`码`/[标签](url) 标记留纯文本（链接保留 URL 本身） |

- **148b** [`bc776a4`](https://github.com/wangxiuwen/tietie/commit/bc776a4) FileChunk 密封分块协议（512KiB/块≤64MiB）+ 接收端重组落盘 Documents/tietie-收到的文件/（重名自动 (n)）+📎回环全链路实测 |

- **149** [`f361f41`](https://github.com/wangxiuwen/tietie/commit/f361f41) MOD+J 弦：选中链接卡 open_url 系统浏览器打开（非链接卡忽略），速查表补 ⌘J；真机 CDP 实测链接卡打开浏览器进程、非链接控制组忽略、净零 |

- **148** [`5e43ca0`](https://github.com/wangxiuwen/tietie/commit/5e43ca0) 选中卡 box-shadow 呼吸（card-breathe 2.2s 无限循环），prefers-reduced-motion 自动关 |

- **147** [`3740236`](https://github.com/wangxiuwen/tietie/commit/3740236) Library 表格新增文件夹归属列（名称/—，悬停 title），folders 随 refresh 重载修后建文件夹不显 |

- **144** [`c34285c`](https://github.com/wangxiuwen/tietie/commit/c34285c) 图片卡缩略图加 img-fade-in 0.28s ease-out 渐显动画（keyframes opacity 0→1） |

- **142** [`c18d149`](https://github.com/wangxiuwen/tietie/commit/c18d149) 实现随 148a 提交一并落库（groupIds 全链路：捕获/幽灵计数/整组入夹/整组挂绳）——本轮真机实证双选整组拖入后 folder_id 齐变，按已具备勾掉 |

- **146** [`da8f2f9`](https://github.com/wangxiuwen/tietie/commit/da8f2f9) 托盘列表滚动>80px 显 ↑ 浮钮，点击回顶并重置选中到首行 |

- **148a** `TBD` 配对设备互发消息：💬 输入框→msg_send 加密帧（绕过同步开关），对端通知+入库可粘贴，发送方本地留档；WSL 虚拟机双向联调实证（win→wsl 命令路径 + wsl→win python 线上客户端，22 字符载荷精确一致） |

- **145** [`a03a893`](https://github.com/wangxiuwen/tietie/commit/a03a893) export_memo_one 命令+详情按钮与右键项「存为 txt」，换行原样保留，导出后资源管理器定位 |

- **128b** [`eb970e8`](https://github.com/wangxiuwen/tietie/commit/eb970e8) 配对协议补全：pair-req/ack/deny 线协议+pairing_join，两端共享同一 token（修复各自随机生成导致同步不可用的断链）；WSL Ubuntu 虚拟机真机联调全通（握手/加密帧跨机/解密入库三方实证） |

- **143** [`aca5dc6`](https://github.com/wangxiuwen/tietie/commit/aca5dc6) 提醒下拉（编写器+详情）加 2h 与「明天早上 9:00」预设，at9 折算分钟走既有管线 |

- **141** [`ce96880`](https://github.com/wangxiuwen/tietie/commit/ce96880) sync 模块事件环（in/out/fail≤20）+ sync_events 命令 + 设置页日志行（最新在前，⇦⇨⚠着色） |

- **140** [`aeb2dc5`](https://github.com/wangxiuwen/tietie/commit/aeb2dc5) 托盘行右键菜单（复制回粘/置顶切换/删除走真实命令并刷新），三处 Row 全接 |

- **139** [`0f7167e`](https://github.com/wangxiuwen/tietie/commit/0f7167e) 编写器「存为模板」chip（会话级去重≤8）点击原样填入，实现一键挂绳常用短语 |

- **138** [`b7aaa95`](https://github.com/wangxiuwen/tietie/commit/b7aaa95) 纯 B 键成为 N 的别名开备注浮层（文本域内仍仅 ⌘N），速查表更新 |

- **137** [`fb1cd66`](https://github.com/wangxiuwen/tietie/commit/fb1cd66) SyncPayload 加 image_b64/hash 字段，出站图片捕获≤4MiB PNG 入帧，入站解 blob 走 image_blob 列，去重用发送方哈希 |

## 2026-10-26

- **136** `—` 入池时已由既有实现覆盖（list_items 即 pinned/used_at DESC）——A→B→A 实测 A 居首，按已具备勾掉 |

- **135** [`44546fc`](https://github.com/wangxiuwen/tietie/commit/44546fc) 详情正文内联解析 **粗体**/[链接](url)/`代码`（React 文本节点零注入面，链接交系统浏览器） |

- **134** [`9272f29`](https://github.com/wangxiuwen/tietie/commit/9272f29) export_diagnostics：版本/OS+设置摘要+数据计数+热键态+末200行日志，通知正文与URL脱敏 |

- **133** [`7d77bfd`](https://github.com/wangxiuwen/tietie/commit/7d77bfd) 卡片/紧凑行 meta 显示 ×N 累计使用徽章（use_count>1 才显示，强调色） |

- **132** [`4de7af5`](https://github.com/wangxiuwen/tietie/commit/4de7af5) 晾衣架头部色点筛选条（全部∗+8色，点选/再点取消），空色显示专属提示 |

- **131** [`2adb3c9`](https://github.com/wangxiuwen/tietie/commit/2adb3c9) 扩池时与方向64重复——行尾 ⧉ 悬停复制已存在，复验悬停门控/行尾不出界/点击剪贴板精确一致后按已具备勾掉 |

- **130** [`754b559`](https://github.com/wangxiuwen/tietie/commit/754b559) 同步设备管理：别名行内改+上次同步时间+托盘开关；冲突提示由哈希去重天然覆盖、图片同步留待后续 |

- **129** [`d4362a5`](https://github.com/wangxiuwen/tietie/commit/d4362a5) 加密同步传输：AES-GCM 密封帧（会话密钥=SHA256(配对token‖v1标签)）双向 TCP 41784，回声抑制+入库去重，设置页开关（默认关） |

- **128** [`daf525f`](https://github.com/wangxiuwen/tietie/commit/daf525f) 配对码状态机：6位码5分钟有效/错码拒配/正码入长期信任表（含随机token供129）/可移除，设置页配对+已配对UI |

- **127b** `TBD` mDNS 验证补注：同主机双实例因 Windows 5353 REUSEADDR 组播单投递不可互见（0/5 实证），跨主机对端缺位未闭环；mdns 全链日志与 --browse 探针已就位供真机双设备回归 |

- **127** [`9dd3137`](https://github.com/wangxiuwen/tietie/commit/9dd3137) mDNS 设备发现（mdns-sd 纯 Rust）：应用广播+浏览 _tietie-sync._tcp，设置页局域网区显示在线设备+刷新 |

- **126** [`c9d7b16`](https://github.com/wangxiuwen/tietie/commit/c9d7b16) 搜索框聚焦（空查询）弹最近搜索下拉，点击即用；重聚焦取消关闭定时器修竞态 |

- **125** [`b8ab340`](https://github.com/wangxiuwen/tietie/commit/b8ab340) 默认衣夹色改为跟随系统强调色（Windows DWM ColorizationColor 去透明度位，OnceLock 缓存，失败回退经典蓝） |

- **124** [`4ab947b`](https://github.com/wangxiuwen/tietie/commit/4ab947b) 托盘行尾 ⌘N 序号徽章（前 10 行）+ ⌘/Ctrl+数字 直接复制对应行，纯数字仍输入搜索 |

- **123** [`13d2120`](https://github.com/wangxiuwen/tietie/commit/13d2120) Library 敏感行默认 ••••••••🔒 打码（title 同步防泄漏），点击显形 5 秒自动回码；行内复制/双击复制的状态提示对敏感行只显 🔒 不回显前 24 字 |

- **122** [`7335536`](https://github.com/wangxiuwen/tietie/commit/7335536) 便签 Markdown 导出中链接便签改为 [去scheme可读标签](完整URL)，txt 格式不变 |

- **121** [`ced56b0`](https://github.com/wangxiuwen/tietie/commit/ced56b0) 抽屉卡片/紧凑行相对时间悬停显示完整本地日期时间 tooltip |

- **修复** `9a21c66+7f390a8` 热键失效修复（用户报「快捷键呼不出主界面」）：诊断=本机 72h 长会话 win32k 输入辅助层渐进失效（RegisterHotKey 派发先死、LL 钩子派发后死，物理/注入全灭，三方对照实验定位），应用侧链路经 PostMessage 直投验证完全健康；新增 hotkey_hook 低级键盘钩子兜底（命中组合键即向 global-hotkey 隐藏窗口重放 WM_HOTKEY，复用全分发链路）+handler 400ms 去重防 OS 恢复后双触发，热键增删改四处同步钩子表；重启会话后热键走 OS 路径恢复、若派发再死由钩子接棒 |

- **120** [`622bcc8`](https://github.com/wangxiuwen/tietie/commit/622bcc8) Library 表格行双击即复制（图片行走复制图片），带已复制反馈不动勾选 |

- **119** [`b72b5fb`](https://github.com/wangxiuwen/tietie/commit/b72b5fb) 便签提醒到点跃迁时发一次系统通知（Win Toast/macOS osascript/Linux notify-send），防重+不补发 |

- **118** [`4f1d152`](https://github.com/wangxiuwen/tietie/commit/4f1d152) 链接卡片 URL 行首新增主域名小徽章（去 www.，强调色 pill） |

- **117** [`cb92665`](https://github.com/wangxiuwen/tietie/commit/cb92665) 底部状态始终带标签：平时「显示 N/N」、搜索时「命中 K/N」高亮 |

- **116** [`cca7bb3`](https://github.com/wangxiuwen/tietie/commit/cca7bb3) 便签详情进编辑态（按钮/双击）自动全选正文，进入后点击仍正常落光标 |

- **115** [`d6defd8`](https://github.com/wangxiuwen/tietie/commit/d6defd8) 托盘行 title 挂备注，悬停即见，无备注行不出 tooltip |

- **114** [`db571f5`](https://github.com/wangxiuwen/tietie/commit/db571f5) 挂卡右键新增「📝 添加/编辑备注…」，打开详情并自动聚焦备注输入框 |

- **113** [`e9c5642`](https://github.com/wangxiuwen/tietie/commit/e9c5642) 敏感卡片正文默认 •••• 打码（aria 同步），点击显形 5 秒自动回码，卡片/紧凑行双视图 |

- **112** [`d5f6e33`](https://github.com/wangxiuwen/tietie/commit/d5f6e33) 新增 export_selected_csv（RFC4180 转义+BOM+原始 kind 列），Library 底栏并列「导出 CSV」按钮 |

- **111** [`8065cb8`](https://github.com/wangxiuwen/tietie/commit/8065cb8) 紧凑行的 ⌘N 序号改为行内 chip 定位（原继承卡片绝对定位会错位），选中态同步强调色 |

- **110** [`766e143`](https://github.com/wangxiuwen/tietie/commit/766e143) 托盘面板暗色下黑 tint 全部反转白 tint（搜索框/行悬停/底栏/滚动条/色徽） |

- **109** [`6c1a8b5`](https://github.com/wangxiuwen/tietie/commit/6c1a8b5) 详情头相对时间悬停显示完整本地日期时间 tooltip |

- **108** [`f0e1904`](https://github.com/wangxiuwen/tietie/commit/f0e1904) 详情调色板最近三色排前（数字键快选同步顺序），顺修 recentPinColors 方向性 bug（原取最旧三色） |

- **107** [`3bd8cb5`](https://github.com/wangxiuwen/tietie/commit/3bd8cb5) 空态分家：真空库保留三步引导卡，搜索无匹配/空分类改紧凑提示不再误导 |

- **106** [`5143550`](https://github.com/wangxiuwen/tietie/commit/5143550) 新增 open_url 命令（仅 http(s)，跨平台默认浏览器），Library 链接行 Ctrl/⌘+点击直开不占选 |

- **105** [`5eb3e76`](https://github.com/wangxiuwen/tietie/commit/5eb3e76) export_memos 加 txt 格式（换行原样保留+分隔线），晾衣架新增「导出纯文本」按钮 |

- **104** [`b62e1ea`](https://github.com/wangxiuwen/tietie/commit/b62e1ea) 选中卡片按 N 开备注编辑器并自动聚焦，搜索框输入时仅 ⌘N 触发，速查表补条目 |

- **103** [`719c850`](https://github.com/wangxiuwen/tietie/commit/719c850) 托盘无搜索时拆「置顶/最近」两段，置顶>5 折叠显「展开 +N」，键盘选择与渲染行同步 |

- **102** [`eca6c3b`](https://github.com/wangxiuwen/tietie/commit/eca6c3b) 详情头每秒倒数剩余时间（到期变橙标已到期），到期挂卡改呼吸灯辉光 |

- **101** [`e0566e0`](https://github.com/wangxiuwen/tietie/commit/e0566e0) 热键录制显示冲突警告（系统常见组合/与其他热键重复，不阻断）；顺手修录制中 Esc 被窗口级拦截关窗的 bug |

- **100** [`98a69bc`](https://github.com/wangxiuwen/tietie/commit/98a69bc) Markdown 导出链接行改为 [去scheme可读标签](完整URL)，标签60字截断 |

- **99** [`2e7dc67`](https://github.com/wangxiuwen/tietie/commit/2e7dc67) 便签调色板悬停时数字键 1-8 直选衣夹色（dot 带 1-8 提示），移开即失效 |

- **98** [`33c71b6`](https://github.com/wangxiuwen/tietie/commit/33c71b6) 链接卡片标题行内嵌 🔗，点击直达复制完整 URL（悬停强调色） |

- **97** [`824c7bf`](https://github.com/wangxiuwen/tietie/commit/824c7bf) 搜索 token 前缀 - 变排除语义（三处搜索面共用 matchQuery 一次生效），含拼音/子序列同口径 |

- **96** [`a994948`](https://github.com/wangxiuwen/tietie/commit/a994948) 设置页版本号变可点击按钮，一键复制版本串并显 ✓ 反馈 |

- **95** [`0bdd41b`](https://github.com/wangxiuwen/tietie/commit/0bdd41b) 图片挂卡无 preview 时显示 🖼️ 占位块而非尺寸文字，有 preview 缩略图不受影响 |

- **94** [`b13783b`](https://github.com/wangxiuwen/tietie/commit/b13783b) Library 表格偶数行加 0.03 微底色斑马纹，声明在 hover/sel 之前不遮高亮 |

- **93** [`bda34f5`](https://github.com/wangxiuwen/tietie/commit/bda34f5) 拖卡经过文件夹 chip 时 drop-hot 状态下平滑放大到 1.1，移开还原 |

- **92** [`d4a1658`](https://github.com/wangxiuwen/tietie/commit/d4a1658) 托盘搜索框尾部 × 清空钮：有词才显、点击清空并回焦输入框 |

- **91** [`e71c577`](https://github.com/wangxiuwen/tietie/commit/e71c577) 便签详情头显示字数/行数（码点计不含换行），编辑态逐键实时，图片/色卡不显示 |

## 2026-10-25

- **90** [`9b71061`](https://github.com/wangxiuwen/tietie/commit/9b71061) 搜索历史会话级：重开抽屉提交搜索词，↑↓翻最近5条，输入即重置游标 |

- **89** [`62291b9`](https://github.com/wangxiuwen/tietie/commit/62291b9) 便签置底：sink_memo 命令（sort=MAX+1 追加到绳尾），右键菜单新增「沉到绳尾」，真机实测首张便签沉底后成为全表最后一张+sort=最大值+菜单项在位净零。同批扩池 91-96

- **88** [`6402f28`](https://github.com/wangxiuwen/tietie/commit/6402f28) Library 导出仅置顶：底栏「仅置顶 (N)」勾选切换导出目标=置顶条目（忽略行勾选，空勾选也启用按钮），文本/Markdown 双导出共用，真机实测按钮启停/导出仅含置顶条目/非置顶零泄漏净零

- **87** [`cbf32ee`](https://github.com/wangxiuwen/tietie/commit/cbf32ee) 抽屉宽度档位：drawer_width 设置（full/80/60）进 position_drawer 按显示器宽取比例并水平居中，设置页三档下拉即时生效，Win32 实测 1920→1536→1152 精确+居中，还原 full

- **86** [`3dcf35e`](https://github.com/wangxiuwen/tietie/commit/3dcf35e) 视图随文件夹：在文件夹内切换只写该文件夹键（tietie-compact-<id>）、在「全部」切换写全局键，切文件夹时恢复各自记忆（未访问文件夹保持当前视图），CDP 实测 all cards→folder compact→回 all cards→再进 folder compact 全对

- **85** [`f121b3b`](https://github.com/wangxiuwen/tietie/commit/f121b3b) 便签备注：memo 表加 note 列+set_memo_note 命令，详情提醒行下新增备注行（📝 状态显示+内联输入 Enter 存/Esc 退出/空即清除），CDP 实测设/清往返净零；晾衣架暂无搜索框，搜索参与随未来便签搜索落地

- **84** [`4a7e285`](https://github.com/wangxiuwen/tietie/commit/4a7e285) 抽屉滚动位置记忆：hide-drawer 时快照 .cards scrollLeft（模块级变量会话共享不落盘），重开 rAF 后 scrollTo 恢复，CDP 实测 636→关→开 636 精确还原。同批扩池 85-90

- **83** [`a421cc2`](https://github.com/wangxiuwen/tietie/commit/a421cc2) 图片卡复制：copy_item_image 命令走后端写图像剪贴板（复用 arboard/NSPasteboard 路径+touch 计数，无合成⌘V），图片卡 actions 行 🖼 按钮，真机实测剪贴板 IMG 3840x1080+日志留痕

- **82** `复验` 托盘 kind 着色勘误收口：与既有实现重复（.kind-* 与 .badge.* 共用类别色变量），真机探针四类 computed 颜色精确命中，零代码改动

- **81** [`157fc38`](https://github.com/wangxiuwen/tietie/commit/157fc38) 便签衣夹历史色板：add_memo_direct 增 color 参数，新建便签脚部显示最近 3 个不同衣夹色（点击选/再点取消=默认蓝），CDP 实测 recents 提取+选中色落库+净零

- **80** [`29217ba`](https://github.com/wangxiuwen/tietie/commit/29217ba) Esc 梯度审计修复：补右键菜单与备注浮层两层（此前开菜单按 Esc 会连抽屉一起关），梯度七层逐级剥，真机实测菜单/备注各开 Esc 仅关自身抽屉保持

- **79** [`8418bf6`](https://github.com/wangxiuwen/tietie/commit/8418bf6) 富文本徽标卡角化：✦ 徽标改绝对定位钉卡片右上角（正文截断不遮），点击仍开沙箱预览，加 aria-label 与 hover 底色；CDP 实测 corner 定位+点击 overlay 弹出净零

- **78** [`222a602`](https://github.com/wangxiuwen/tietie/commit/222a602) 便签字号快捷调节：详情内 ⌘+/⌘− 步进 0.15（0.7~2.0 钳制）、⌘0 复位，--memo-zoom 会话级（跨详情共享、不落盘），CDP 实测 1→1.3→1.15→1.0→字号 14.95px 全链

- **77** [`ed3170f`](https://github.com/wangxiuwen/tietie/commit/ed3170f) 托盘面板分页：30 行起步、↑↓ 触底自动加一页（查询变更即重置回首页），CDP 实测 30→32（满库）+查询重置 28 行+探针净零；★批量派发 keydown 会读到陈旧 sel，要逐 rAF 派发。同批扩池 79-84

- **76** [`a7701d5`](https://github.com/wangxiuwen/tietie/commit/a7701d5) 空库引导：Empty 态三步上手卡（编号圆点+i18n 双语），搜索无命中复用同组件，CDP 实测渲染/消失双向

- **75** [`a782780`](https://github.com/wangxiuwen/tietie/commit/a782780) Library 筛选记忆：新增类型筛选下拉+视图/排序/类型三项 localStorage 持久化，跨窗口重开甚至跨应用重启还原，真机实测 color 筛选重启后精确恢复

- **74** [`e3bb5e3`](https://github.com/wangxiuwen/tietie/commit/e3bb5e3) 条目备注：clip_item 加 note 列+set_item_note 命令（空白即清除），右键「添加/编辑备注」居中浮层（⌘↵存/Esc 取），meta 行 📝 显示，抽屉/库/托盘三处搜索并入备注，CDP 实测往返/搜索命中/清除净零

- **73** [`9f25f28`](https://github.com/wangxiuwen/tietie/commit/9f25f28) 抽屉卡片复制按钮：actions 悬停行首增 ⧉（粘贴旁）直接写剪贴板免右键，aria/title 复用 ctx.copy，CDP 实测 hover 可见+点击后剪贴板=行0 内容（GBK 对齐验证）

- **72** [`22f8bf5`](https://github.com/wangxiuwen/tietie/commit/22f8bf5) Library 表格快捷键：↑↓ 键盘光标（accent 描边+scrollIntoView，输入框/色板视图豁免），↵ 复制行（应用内提示），Del/Backspace 删行，CDP 实测光标步进/回车提示/净零删除

- **71** [`b14bc30`](https://github.com/wangxiuwen/tietie/commit/b14bc30) 热键占用实时检测：recheck_hotkeys 命令对被拒组合重探测（成功即接管热键并写回状态），设置页热键区加「重新检测被拒组合」按钮，真机实测三组合全注册+命令往返+按钮在位。同批扩池 73-78

- **70** [`96249b4`](https://github.com/wangxiuwen/tietie/commit/96249b4) 启动完整性自检：setup 跑 PRAGMA integrity_check（ok 记 info/异常记 error 全行），db_ok 原子贯穿 db_integrity_ok 命令，设置页异常时红条+一键导出备份，真机实测日志 ok+命令 true+无红条误报

- **69** [`2c3763a`](https://github.com/wangxiuwen/tietie/commit/2c3763a) 便签批量导出：export_memos 命令（置顶📌前缀/⏰提醒标注/图片占位）写 Documents/notes-*.md，晾衣架工具栏「导出便签」按钮+导出即 reveal，CDP 实测文件内容含便签+按钮在位+净零

- **68** [`474c86e`](https://github.com/wangxiuwen/tietie/commit/474c86e) 双击行为可配置：设置页三选一（粘贴/仅复制/编辑）持久化 settings.json，卡片与紧凑行共用 dblAct 分发，show-drawer 事件重读设置即时生效，CDP 实测 copy=剪贴板命中/edit=编辑器打开/还原默认净零

- **67** [`7183fcc`](https://github.com/wangxiuwen/tietie/commit/7183fcc) 剪贴板捕获暂停：托盘「暂停捕获 10 分钟/恢复捕获」两菜单+pause_capture/capture_paused_remaining 命令，轮询双分支（文本/图片）gate 且暂停期哈希照记防恢复泄漏，CDP 实测暂停期复制零入库/恢复即录/净零

- **66** [`de7359c`](https://github.com/wangxiuwen/tietie/commit/de7359c) 导出后打开位置：reveal_path 命令三平台（Explorer /select、mac open -R、linux xdg-open 父目录）+Library 文本/Markdown 导出成功即触发，真机走真实按钮路径实测新 Explorer 窗口弹出+日志留痕+净零

- **65** [`58b4fa0`](https://github.com/wangxiuwen/tietie/commit/58b4fa0) 便签提醒编辑：详情新增提醒行（状态 ⏰ 不提醒/剩 Nm/已到期 + 改提醒下拉 5/15/30/60/取消），set_memo_reminder 命令，CDP 实测设 5m 落库 299s→取消归 NULL→净零

- **64** [`2adb3c9`](https://github.com/wangxiuwen/tietie/commit/2adb3c9) Library 行内快捷复制：非图片行 hover 显 ⧉ 按钮（stopPropagation 不触选择），点击写剪贴板+「已复制」提示，CDP 实测 19 行显隐/剪贴板精确命中/图片行无按钮

- **63** [`6fae34f`](https://github.com/wangxiuwen/tietie/commit/6fae34f) 备份健康提醒：export_backup 成功即记 last_backup_at，设置页超 7 天（含从未）顶部黄条+一键导出即消，CDP 实测出现→导出→消失→时间戳落盘，测试文件与时间戳均还原

- **62** [`5c9addc`](https://github.com/wangxiuwen/tietie/commit/5c9addc) 抽屉搜索命中计数：底栏计数搜索时标签化「命中 N/M」+accent 高亮（空闲保持裸 N/M），CDP 实测 turing→命中 8/24、清空还原

- **61** [`ecb6471`](https://github.com/wangxiuwen/tietie/commit/ecb6471) 托盘面板图片缩略图：图片行内嵌 18px 缩略图（preview 即 b64 缩略图直用 data URL），行文本改显尺寸杜绝 base64 露出，CDP 实测 5 行缩略图解码 320x90+零泄漏

- **60** `审计` list_items 性能审计收口：生产 EXPLAIN 已走 idx_clip_pinned 序读+LIMIT 早停，5000 行合成基准 0.354ms（无索引对照 2.2× 劣化），covering index 不必要——零代码改动

- **59** [`2753300`](https://github.com/wangxiuwen/tietie/commit/2753300) 视觉 token 化审计：圆角五档阶梯+环境阴影两档+毛玻璃两档 token 落 :root，散值 15→9 种收敛（药丸/圆/绳锚保留），CDP 三窗 .btn/token 解析同值实证

- **58** [`8438d54`](https://github.com/wangxiuwen/tietie/commit/8438d54) README 双语全量同步：功能清单对齐 60+ 轮现实（紧凑列表/物理绳/拼音搜索/Markdown 导出/敏感加密/夜间回收/跳转列表/无障碍/新键位表），Roadmap 勘误已交付项，双语逐节平行

- **57** [`9edc1c3`](https://github.com/wangxiuwen/tietie/commit/9edc1c3) CHANGELOG 自动化：scripts/gen_changelog.py 解析迭代记录区全量生成 CHANGELOG.md（日期分组+sha 链接+--check 防过期），首跑 62 条落盘

- **56** [`d5cdcfa`](https://github.com/wangxiuwen/tietie/commit/d5cdcfa) 全键盘审计收口：MOD+↑挂绳/Menu⇧F10 右键菜单/⇧↑↓ 多选/空格大图/MOD+R 复制 rgb()，速查表 15 行，CDP 真机 5/5 全过

- **55** [`04c26a9`](https://github.com/wangxiuwen/tietie/commit/04c26a9) 夜间空闲回收：每日本地 02-05 点首轮 trim 过期+上限复执+WAL truncate（日期去重），门控单测钉死+真机窗口外正确静默

## 2026-10-24

- **54** [`64719dd`](https://github.com/wangxiuwen/tietie/commit/64719dd) 敏感条目加密：AES-256-GCM 机器派生密钥，标记后 DB 文件内全密文（enc1: 前缀）+应用内透明解密+🔒徽标+右键切换，CDP+裸库双验：密文落盘/明文不漏/取消原地还原

- **53** [`148c4a3`](https://github.com/wangxiuwen/tietie/commit/148c4a3) 便签到期闪烁：memo 加 remind_at 列（迁移）+新建可选 5/15/30/60 分钟提醒，到期挂卡 due-flash 动画 1 分钟后转常亮⏰，CDP 实测 6s 到期动画 live 运行+净零清理

- **52** [`7f42a65`](https://github.com/wangxiuwen/tietie/commit/7f42a65) 抽屉紧凑列表模式：Header 切换按钮（行/卡图标）卡片↔单行列表（badge+单行文本+来源/时间+置顶衣夹+序号），localStorage 持久化，CDP 实测 24 卡↔24 行+点击选中+跨开合保持

- **51** [`1408b37`](https://github.com/wangxiuwen/tietie/commit/1408b37) Library 颜色色板视图：表头「色板」切换网格（auto-fill 方形色块+hex 角标+hover 缩放，点击复制 hex），CDP 实测抓色→渲染 rgb 正确→点击复制命中→净零清理

- **50** [`57a3748`](https://github.com/wangxiuwen/tietie/commit/57a3748) Library 条目 Markdown 导出：export_selected_markdown 按类型分组（文本列表/链接[c](c)/代码```围栏/颜色`hex`/图片占位），CDP 实测导出文件内容正确

- **49** `复验` 方向49 与已完成的18重复（扩池误加）：R18 实现在当前构建合成拖拽全序列复验通过（folder None→临时夹→还原，净零），无需新代码

- **48** [`e9ec265`](https://github.com/wangxiuwen/tietie/commit/e9ec265) DPI/scale 跳变重定位：on_window_event 接 ScaleFactorChanged 重摆抽屉/晾衣架，WM_DPICHANGED(144) 合成实测窗口 1.5×+repositioned 日志（tao 有 scale 去重缓存，测试要错开值）

- **47** [`2f21101`](https://github.com/wangxiuwen/tietie/commit/2f21101) Linux .desktop 集成收口：category→Utility+deb desktopTemplate（Comment/Keywords 补齐），渲染后 spec 结构校验 PASS，config schema 构建实证

- **46** [`f2dad8b`](https://github.com/wangxiuwen/tietie/commit/f2dad8b) macOS template 图标代码侧收口：icon_as_template 精确 cfg(macos) 门控+确认透明底/不透明描边合法 template 形态，Win 真机回归描边照常

- **45** [`4257a1b`](https://github.com/wangxiuwen/tietie/commit/4257a1b) 无障碍审计：卡片列表 listbox/option 语义+aria-label（图片卡报尺寸不报 base64）、图标按钮可访问名、全局 :focus-visible 焦点环；CDP 实测 126 元素 0 缺名

- **44** [`5f463aa`](https://github.com/wangxiuwen/tietie/commit/5f463aa) E2E 冒烟脚本沉淀 scripts/e2e_smoke.py：内嵌 stdlib WebSocket+CDP invoke+Win32 窗口真值+只读 sqlite，四链路（开抽屉/挂绳/摘下/净零库）实测 PASS

- **42+43** [`ac89034`](https://github.com/wangxiuwen/tietie/commit/ac89034) vitest 前端测试上线：search 拼音三层/i18n key 双向 diff(92 key 全等)/hexToRgb 15 断言全绿，npm test 进 CI；hexToRgb 抽 color.ts 纯模块

- **41** [`975c083`](https://github.com/wangxiuwen/tietie/commit/975c083) 冷启动计时打点：run 入口 Instant→setup 首尾两条 boot 日志，装机实测 pre-setup 630ms / complete 705ms

- **40** [`c70d040`](https://github.com/wangxiuwen/tietie/commit/c70d040) panic hook 上线：PANIC+位置+强制 backtrace 写 tietie.log（panic=abort 下仍执行），端到端单测+装机日志实证

- **38** [`223f5c8`](https://github.com/wangxiuwen/tietie/commit/223f5c8) Windows 跳转列表重试成功：AUMID 显式钉窗口+PKEY_TITLE 补显名双根因修复，customDestinations-ms 落盘+--paste 转发 0.6s 实测

- **39** [`68cc0c3`](https://github.com/wangxiuwen/tietie/commit/68cc0c3) 轮询自适应退避 600→1000→1500→2000ms（变化即回 600），日志阶梯实证+深退避复制 1.47s 命中

- **38** `—` 未完成：jumplist COM 写通但 CommitList 未落盘（AUMID 疑不匹配），按协议回退不合坏代码，原因已标注

- **37** [`e8d1329`](https://github.com/wangxiuwen/tietie/commit/e8d1329) 晾衣架>15 张时橙色「已挂 N」提示（title 建议清理），<15 无/16 显示/清理消失实测

- **36** [`ca3a109`](https://github.com/wangxiuwen/tietie/commit/ca3a109) 新便统一尾部追加（sort=MAX+1 修隐性插队）+拖拽预览时行尾虚线「挂到这里」占位，A/B/C 顺序+占位出现消失实测

- **35** [`7204905`](https://github.com/wangxiuwen/tietie/commit/7204905) 便签详情 8 色衣夹色板（点击即时换色+active 指示），橙 #ff9500 全链路实测（详情→DB→挂卡衣夹）

- **34** [`c40f94a`](https://github.com/wangxiuwen/tietie/commit/c40f94a) Library 统计条（总数/今日/置顶+类型分布条形图+来源Top5 pill），19/6/0+13/5/1+chrome/explorer 实测

- **33b** [`5978557`](https://github.com/wangxiuwen/tietie/commit/5978557) 托盘弹窗两修：任务栏感知定位+查看全部走 open_drawer；CDP 全链路（19 行列表→点击→抽屉持续打开截图实证）

- **33a** [`2cc1409`](https://github.com/wangxiuwen/tietie/commit/2cc1409) 浮层视觉统一（圆角/阴影token+毛玻璃+弹入动画+菜单精致化），速查面板截图+右键菜单 computed 实证

- **33** [`ba97aca`](https://github.com/wangxiuwen/tietie/commit/ba97aca) 富文本卡 ✦HTML 徽标→沙箱 iframe 渲染预览（Esc 关闭），加粗/斜体/彩色截图实证

- **32** [`aeb88f2`](https://github.com/wangxiuwen/tietie/commit/aeb88f2) 代码卡无依赖 token 着色（关键字/字符串/数字/注释四色），搜索时回退命中高亮，token 实测 fn/42// 注释

- **31** [`9212d81`](https://github.com/wangxiuwen/tietie/commit/9212d81) Library 四列头点击排序（时间/类型/大小/来源，升降切换+箭头指示），大小/类型排序实测

- **30** [`0e75545`](https://github.com/wangxiuwen/tietie/commit/0e75545) 抽屉按 ? 弹键盘速查浮层（13 项双列，Esc 优先关浮层不关抽屉），i18n 双语实测

- **29** [`6b4543f`](https://github.com/wangxiuwen/tietie/commit/6b4543f) 来源黑名单（历史来源chip多选+手动添加，逗号串持久化，轮询双侧拦截），UI 往返+explorer 入单实测

- **28** [`e343377`](https://github.com/wangxiuwen/tietie/commit/e343377) 条目上限四档（200/500/1000/3000），MAX_HISTORY 常量参数化，设置下拉实测+非法值拒绝

- **27** [`b9a917f`](https://github.com/wangxiuwen/tietie/commit/b9a917f) 保留时长三档（永久/7/30天，置顶豁免），惰性清理+单测，设置下拉实测 0→7→reset

- **26** [`76865fc`](https://github.com/wangxiuwen/tietie/commit/76865fc) 主题色四选（蓝绿紫橙色点选择器，--accent/--accent-dim 覆盖），切紫实测 #af52de 全局生效

- **25** [`944e209`](https://github.com/wangxiuwen/tietie/commit/944e209) 全局字体三档缩放（--fs 0.9/1/1.15，72 条 font-size 全走 calc），设置面板下拉即时生效实测

- **24** [`0446818`](https://github.com/wangxiuwen/tietie/commit/0446818) 托盘图标按系统主题取描边色（浅色主题深笔画），本机深色主题日志实证 rgba(255,255,255,255)

- **23** [`7f1ef2a`](https://github.com/wangxiuwen/tietie/commit/7f1ef2a) 挂卡左右拖换位（sort 列+reorder_memo，水平/垂直手势分流），A→尾部 B C A 实测

- **22** [`3c21ad0`](https://github.com/wangxiuwen/tietie/commit/3c21ad0) 便签右键菜单（复制/置顶/编辑/摘下，复用ContextMenu），编辑直开编辑态，双击=快捷编辑

- **21** [`b37e5a1`](https://github.com/wangxiuwen/tietie/commit/b37e5a1) 卡片右键菜单（复制/粘贴回/置顶/挂绳/移入文件夹/删除 自定义div），CDP 开合+置顶往返+Esc 关闭实测

- **16d** [`71fd141`](https://github.com/wangxiuwen/tietie/commit/71fd141) 全拼（tuopan→托盘…）+字母子序列（tln→turing-llm-next）匹配，AND 组合同样生效

- **16c** [`79109f5`](https://github.com/wangxiuwen/tietie/commit/79109f5) 搜索结果按 use_count 加权排前（置顶优先），提升 use_count 后条目跃升实测

- **16b** [`a3a0d62`](https://github.com/wangxiuwen/tietie/commit/a3a0d62) 抽屉/托盘命中片段 <mark> 高亮（token 级黄底），turing llm 4 处高亮实测

- **16a** [`edf7b34`](https://github.com/wangxiuwen/tietie/commit/edf7b34) 搜索空格分词 AND（每词都命中才出，拼音按词独立），turing→3/llm→2/zzzz→0 实测

- **20** [`5634b7b`](https://github.com/wangxiuwen/tietie/commit/5634b7b) 抽屉/晾衣架跟随鼠标所在显示器（双屏真机验证：光标右屏→L=1920，回主屏→L=0）

- **19** [`4bb68d6`](https://github.com/wangxiuwen/tietie/commit/4bb68d6) 合并重复历史开关（默认开）+说明文案；关=每次复制记新条目（hash#n 后缀），A/B/A 交替实测

- **18** [`7325570`](https://github.com/wangxiuwen/tietie/commit/7325570) 卡片拖到文件夹 chip 高亮+松手归类（拖到「全部」移出），CDP 实测 folder_id=2

- **17** [`ae9279b`](https://github.com/wangxiuwen/tietie/commit/ae9279b) 托盘面板全量滚动列表+↑↓选择高亮+回车取选中，16 行连续导航实测

- **16** [`984c31b`](https://github.com/wangxiuwen/tietie/commit/984c31b) Wayland 检测：托盘禁用说明项+设置面板提示行（win 实证 false 不显示）

- **15** `TBD` bump-version.py 三处同步+check 模式+tag 提示，往返验证

- **14** [`54efd02`](https://github.com/wangxiuwen/tietie/commit/54efd02) db/clipboard 单测 8 个全过（trim 语义钉死）+CI cargo test

- **13** [`95f4892`](https://github.com/wangxiuwen/tietie/commit/95f4892) 文件日志 512KB 轮转+启动 self-check 日志/tooltip 告警，真机验证

- **12** [`9e83703`](https://github.com/wangxiuwen/tietie/commit/9e83703) 颜色卡 rgb() 显示+一键复制（#3b82f6→rgb(59,130,246) 实测）

- **11** [`46b2766`](https://github.com/wangxiuwen/tietie/commit/46b2766) 便签图片详情原图（source_item_id→blob URL 3840x1080 验证）

- **10** [`1f56d10`](https://github.com/wangxiuwen/tietie/commit/1f56d10) ⌘/Ctrl 多选+批量挂绳/删除（hang_items 命令），CDP 全链路验证

- **9** [`7cb29ee`](https://github.com/wangxiuwen/tietie/commit/7cb29ee) ↑/↓ 导航同义 ←/→，CDP 四方向验证

- **8** [`f5e0a0f`](https://github.com/wangxiuwen/tietie/commit/f5e0a0f) i18n 中英双语（~90 文案收口+语言下拉），CDP 切换验证

- **7** [`02f087b`](https://github.com/wangxiuwen/tietie/commit/02f087b) Library 管理窗（表格/多选/批量删/导出文本），真机全链路验证

- **6** [`7dec9a2`](https://github.com/wangxiuwen/tietie/commit/7dec9a2) JSON 备份导出/导入（Documents+base64 blob+三表去重合并），真机往返验证

- **5** [`6335732`](https://github.com/wangxiuwen/tietie/commit/6335732) 便签置顶（迁移+排序+详情按钮+衣夹橙色），CDP 三处同步验证

- **4** [`09fc70d`](https://github.com/wangxiuwen/tietie/commit/09fc70d) 拼音首字母搜索（GB2312 全字表生成+统一谓词），sx→上线单 真机验证

- **3** [`25d2243`](https://github.com/wangxiuwen/tietie/commit/25d2243) 图片卡大图预览浮层（blob 原图+Esc 优先关浮层），CDP 全链路验证

## 2026-10-23

- **2** [`3075a6b`](https://github.com/wangxiuwen/tietie/commit/3075a6b) 来源应用记录三平台实现，真机 Explorer 前台复制验证 source_app=explorer

- **1** [`fc7e692`](https://github.com/wangxiuwen/tietie/commit/fc7e692) 拖拽监听上提为窗口级单份（1500→6 个 handler），挂/摘两链路真机回归通过

