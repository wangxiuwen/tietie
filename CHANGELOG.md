# Changelog

> 由 docs/ITERATION_BACKLOG.md 的迭代记录生成——`py -3 scripts/gen_changelog.py`，请勿手改。


## 2026-10-25

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

