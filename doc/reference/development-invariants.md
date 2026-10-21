# 开发不变量与历史事故索引
> 状态：按需参考；最后更新2026-10-14。
> 本页保留原开发skill中非显然的锁、缓存、编号与发布经验；历史日期/旧测试数量不代表当前验收。
> 当前事实见[当前状态](../../docs/current-state.md)；原文见[skill归档](../history/context-checkpoint-20261014/development-skill.md)。

## 阅读范围与现行区别
检索词：runtime、_work_cache、fingerprint、parents、revision['files']、engine.lock、含义词、Vue Proxy。
本机/source0.5.12的最近测试为634后端通过/6既有fixture跳过、97桌面通过（phase11）。
应用/Python源码版本与公网清单分开核验；只在真实包验证后更新网站。
历史“单”计数按现行UI“弹”理解；旧批量时间不是当前耗时保证。
真实微信接收/提交后仍检查实际名称与文字值；平台可能去除标点，不能冒称逐字一致。
历史授权复选框经验仅适用于当时自制角色的表单，不替代当前素材实际授权信息。

## 开发命令

```bash
# 后端测试（venv 在 sticker_engine/.venv，pytest 就在 venv 里——用系统
# python 会报 No module 列表 pytest，务必走 .venv 的解释器）
cd sticker_engine && .venv/Scripts/python.exe -m pytest tests -q --ignore=tests/agent

# 已知环境性失败基线（2026-09-11 全量实测 16 个，非代码问题，对照清单）：
#   ① symlink 特权 ×3：test_deletion 两个 safe_unlink + test_maintenance 一个
#     cleanup_rejects（需 Windows 开发者模式/管理员）
#   ② %APPDATA% 污染 ×11：test_publisher ×9 + test_shelf_batch ×2（引擎测试
#     连到本机真实库/真实状态，干净 CI 上是绿的——stash 对照已验证过归属）
#   ③ 词库数据 ×1：test_generate 的 keywords_no_banned_low_rating（依赖线上词库快照）
#   另注意：写测试要封闭（monkeypatch 掉 hooks.runtime_for / _ensure_engine），
#   断言路径分隔符要归一化（Windows 是反斜杠）——test_sticker_pairing 两个
#   用例曾因此在本机全红、CI 全绿。跑全量后对照这份基线，别把环境失败当回归。

# 前端测试（65 个，提交前必跑——Vite build 不报未定义变量，只有它能拦）
cd desktop && npx vitest run

# 桌面 dev 启动（引擎需 PYTHONPATH 指向 sticker_engine 源码）
cd desktop && PYTHONPATH=../sticker_engine npx electron . --remote-debugging-port=9235

# 用户数据（prefs/episodes/series/资源库）在 %APPDATA%/StickerEngine/
```

## 必须遵守的项目纪律

1. **改完必须跑测试**：后端 pytest（460+）+ 前端 vitest（65），全绿才交付。半成品提交会白屏——`income is not defined` 事故：store return 引用未定义变量，Vite build 静默打包、运行时整树崩溃。
2. **版本号纪律**：`desktop/package.json` 的 `version` 每次发版必须 bump，且同步 `desktop/site/index.html` 的 `data-version` 与 `desktop/site/version.json`（老版本客户端靠它发现新版本）。
3. **codex 调用三条铁律**（`providers/codex.py`，违反就翻车）：
   - prompt 必须单行（多行经 codex.cmd 会让 `-i` 参考图静默丢失 → 模型自创角色）
   - prompt 必须在 `-i` 之前（clap 多值参数会吞后面的位置参数）
   - 参考图路径必须纯 ASCII（中文路径会被静默丢弃，provider 里有自动暂存）
4. **引擎有 IP 身份门禁**（S1）：生成后校验成图与 base 是否同一角色，不过则重试/作废。别绕过它。
5. **发布绝不假成功**：以页面出现「提交成功」字样为准，失败要截图带 warnings 返回。
6. **系列编号**：episode 编入 series 自动编号（series.json 的 next_number），删除 episode 必须回滚编号。

## 已知坑（血泪史，别再踩）

- Electron IPC 传 Vue Proxy → "An object could not be cloned"。防御已做两层（store JSON 拷贝 + preload），新命令直接走 `api.send` 即可。
- 微信发布页面的 radio/checkbox 是隐藏 input，必须点可见 `<label>` 文本，且要点前判态（点两次=取消选择）。
- `涉及肖像权授权/涉及版权授权` 两个复选框**永远不要勾**（自制角色无需授权，勾了反而要求上传证明文件）。
- codex 生图会自我迭代多轮，600s 超时 + 已生成图收割策略在 provider 里，别缩短。
- playwright 浏览器下载直连自家 CDN 会卡死（本机代理在 7890 但子进程不吃）：
  `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright python -m playwright install chromium`（2026-08-29 实测镜像 1 分钟装完）。
- venv 装依赖后注意 playwright 版本是否被顺带升级（版本变→浏览器目录号变→
  `Executable doesn't exist` 秒失败），重装浏览器即可。
- **资源库引擎四坑（2026-09-08 真实迁移实测，2.5 万文件/2GB）**：
  1. **锁**：所有 `library_*` 命令共抢一把进程锁，status 轮询（每 8s、持锁 1~3s）会与用户命令撞车。已修：面板 busy 时停轮询 + 引擎锁排队 3s。新加 library 命令的硬性要求：凡会扫描或复制超过 100 个文件，必须逐 100 条发一次 progress 事件（含 scanned 或 completed/total），否则用户以为死了。
  2. **plan 持久化 O(n²)**：plan JSON 含全部条目明细（万级文件=37MB），复制循环每文件重写一次 = 2GB 迁移要 3 小时。已节流（每 50 文件/5 秒，循环后强制保存）；改 `transfer.py` 循环时别改回每条目保存。清理循环的全库重校验同理，已改 per-source 缓存，单文件删除前快照校验保留。
  3. **设置物化死锁**：`settings.py apply()` 曾把「本地实体未物化（fingerprint=None）」判为本地修改冲突 → 切库/新设备后全部设置冲突死锁。已修；动三方指纹判定（库/本地/marker）时保持 None=待物化语义。
  4. **幽灵冲突**：resolve 选用版本后 marker 与合并头错位，status 永远报 1 个 settings_conflict 但 heads=1。解法：对齐 marker（state 的 settings_versions）+ `refresh(capture=False)`。诊断冲突真假看 catalog 的 heads 数，别只信 status。
  5. **多实例并发=版本分叉（2026-09-09 事故，308 作品全冲突）**：两个应用实例各挂一个引擎时，进程内 LOCK 管不住跨进程——并发 capture 12 秒内全部作品 fork 平行头。已加跨进程单实例锁（cli 启动抢 `%APPDATA%/StickerEngine/engine.lock`，exit 3 拒启，bridge 不自动重启）。坑：`a+` 打开文件锁前必须 `seek(0)`，否则两实例锁不同字节区间互不冲突。用户报"全部作品都是版本冲突"先查 `wmic process where "name='python.exe'"` 有没有多组引擎。
  6. **capture 的 parent 必须取库当前 heads（2026-09-09 二次事故，单实例也分叉）**：`runtime.capture` 旧实现拿 marker 里记录的上次 revision 当父——head 被 resolve/合并推进后 marker 不随之更新，下次 capture 写出平行分支（一次同步 281 作品全冲突）。已修：`parents=None` 交给 catalog 自动取当前全部 heads。**任何写 write_revision 的新代码都别拿缓存/marker 的 revision 当父**。settings 实体的 marker-parent 是有意设计（显式分支让用户选，勿改），但 `runtime.resolve` 选设置版本时会自动对齐 marker（否则 resolve→同步→又冲突死循环）。
  7. **发布提速两板斧（2026-09-09 计时实锤，一弹发布 9.3 分钟）**：①批量内**复用浏览器会话**（`_SHARED_BROWSER`，`_publish_episode(keep_session=True)`）——平台对每个新会话都要求重新登录，实测每弹 login ~150s 是最大头；②发布分步计时（`_report` 步骤切换自动报"✓ XX完成，耗时 N 秒"）——发布耗时数据全透明。批量结束 `close_shared_browser()` 统一收尾，失败弹不复用（脏状态）。**写外部驱动注意**：publish_episode 的 result 响应先于 hooks 收尾刷新返回、锁后放——驱动必须只认 `result/error` 类型事件（progress 别提前返回）、撞「正在进行」要间隔重试；`_publish_impl` 的 finally 用自己的 `outcome` 局部变量判定会话保留，别引用外层 `publish()` 的 `result`（2026-09-10 NameError 吞成功+浏览器泄漏→后续弹全撞 "Sync API inside asyncio loop"）。
  8. **新增 prefs 键必须进 `PREF_KEYS` 白名单（2026-09-10 事故，317 弹起风格静默回退）**：`settings.py` 的 `_sanitize_prefs` 只保留白名单键，apply 曾把 prefs.yaml **整文件替换**为白名单 payload——`background_mode`/`sticker_text` 当初没进白名单，每次设置同步都被洗回 schema 默认值（transparent），用户白天设好的 solid 实底当天被静默改掉、批量 40+ 弹全透明。已修（白名单扩容 + apply/force_apply 改合并写入 `_write_prefs_merged`，本机独有键如 browser_headless 靠合并存活）。**给 Prefs 加新字段时同步改 PREF_KEYS**，否则一同步就丢。
  9. **rows() 有 30s 快照缓存（2026-09-10 测试拦截）**：delete/hide/resolve 改变可见性后必须 `self._rows_at = 0` 打穿缓存，否则删除后列表 30 秒内还显示（用户会重复点删）。新增改变作品可见性/状态的方法都要加这一句。
  10. **catalog 有 per-work 解析缓存（2026-09-10 性能根修，单操作 209s→2s）**：`_analyze_work` 以修订目录 mtime_ns 为戳缓存（修订目录 append-only，mtime 变化⇔内容变化；Syncthing 落盘自动失效）。**给 catalog 加任何写修订文件的新路径必须失效 `_work_cache`**（write_revision 按作品 pop、merge_from 整体 clear 已做）；批量循环里查作品路径用 `_work_path_map()` 一趟索引，别循环调 path_for（O(n²)）。
  11. **runtime 实例必须记忆化（2026-09-11 批量提速根修，每弹 3min→1min45s）**：`active_runtime()` 曾每次调用 new 实例，进程内全部缓存（catalog 解析、rows 30s、refresh TTL）随实例丢弃——批量发布每弹白付 ~80s 冷解析（`runtime_for` 09-05 已修、`active_runtime` 漏了，现均按 user_data 单例化）。**新写任何获取 runtime 的工厂函数都要走实例缓存**，否则所有缓存优化形同虚设。批量双生图工位：取号段持 `_SERIES_NUMBER_LOCK`（occupied 扫描→take→save 原子）、`prep.py` 目录名防同秒碰撞、run_batch 的 `gen_workers` 参数控制工位数（发布保持单车道防平台风控）。
  12. **写运维脚本先核对字段位置（2026-09-11 深夜事故）**：`files` 在 revision 顶层（`revision['files']`），**不在 metadata 里**——把 `metadata.get('files')` 当文件清单曾把 114 个已发布作品误判为空壳并软删除（deleted 修订与真头形成双头 conflict），靠 `catalog.resolve` 全量恢复。另外：**`write_revision(deleted=True, parents=[heads])` 后再写一条 deleted=False 的"恢复修订"时，parents 必须指向删除修订**（指向原头会让删除修订成为无引用竞争头 → conflict）。判断作品真伪永远用 revision['files'] + 完整性，别信 metadata。
  13. **"资源未到齐"半成品壳的三层根因（2026-09-11 一天 85 个）**：①发布成功不写 platform_item_id（要等下次同步）②同步名字兜底遇**同一作品的两个投影目录**（时间戳名 + work_id 名并存）误判"同名歧义"不绑定 ③未绑定 → placeholder_factory 给平台行建 0 文件壳。三层都修了：publisher 提交成功即拉列表 API 把 sid 写进 meta；同步匹配（platform_data._match_rows 与 status._match_by_item_then_name 两处）按 work_id 去重再判唯一。**新写"按名字匹配本地作品"的逻辑都要先按 work_id 去重**；清壳用 clone_fix.py（Temp 目录）。
  14. **含义词硬红线：每个含义词 ≤4 字符（含标点），超长被平台截成断词必驳回（2026-09-11 用户重申，107 单驳回复盘 626 个 5-8 字场景词是大头）**：生成端选词、整改改词、批量改名后都要跑 ≤4 字校验。批量整改图标/含义词时注意：**本地改名要同步到 work_id 投影目录**（jsonl episode_dir 常是时间戳目录，rows 指向 work_id 目录——只改一边会 conflict 卡 can_edit），以及批量暂停/恢复后用 operation reconcile 核销失败单。
  15. **打分反哺闭环（2026-09-13 用户 148 单 822 格打分落地）**：①一键复制打分导出 `rating_export/ratings.jsonl`（路径引用式，AI 自行读取）；②5 星=精选（用户目录 `微信表情包/精选表情/{专辑名}-{词}.png`）；③1-2 星=词库清洗（keywords.json 删词+备份，低分残留要归零，en 描写级禁词同查）；④画法问题（舌头×7/头大×4/三只手×4/裁剪×9）进 `_STYLE_BLOCK` 负面约束；⑤备注里"改为 X"自动改名（注意剥口头语尾巴"更好"）。**test_publisher 9 失败是 %APPDATA% 环境基线**（stash 验证过与代码无关），别误当回归。
  16. **选词重复三层修复（2026-09-13 用户"前后几代词全一样"）**：根因=小主题池（日常寒暄仅 19 词）被 70% 配额抽穿+装填重抽，近 20 单 14 单同批词。三层已修：①小池配额封顶（池容-2，不足自动并入跨主题大池）②跨单用词记忆 `_RECENT_WORDS`（60 词滚动，重用降权 ×0.15）③A/B 实测锁小池场景 67%→18%。**改 keywords.json 结构的脚本慎写**——小主题共享词池的 list 引用经 JSON 序列化会展开成全量拷贝+跨库 zh 去重会把后扫描主题清空（打过工人清零，已回滚重来）；上轮 20008 词误删事故的教训：**动词库前先备份+跑 test_keywords_resource_has_themes_and_zh**。
- **平台素材上传（2026-09-02，71-89 批量全败事故，三层坑叠加）**：
  1. **过滤键名两套写法**：`_step_upload_assets(only=["banner",...])` 英文键 vs 内部中文标签 `("横幅",...)` 不匹配 → 上传整体空转且零告警 → 提交红字「横幅不能为空」。61-69 全过只因发布早于该 bug 引入。`_ASSET_ONLY_ALIAS` 做了映射，动 only 逻辑必须跑 `test_step_upload_assets_only_english_keys`。
  2. **上传顺序**：16 张表情图批量 set 会占满平台异步上传通道，素材 set 紧随其后容易不落地（老项目 skill 降级经验：素材图先传、表情图后传）。publisher 新建模式已按「赞赏→横幅/封面/图标→表情图→文本→分类」排序，别改回去。
  3. **裁剪框与假阳性确认**：素材上传后可能弹「裁剪横幅」dialog，不点「确定」上传不落地；且 dialog 内预览图、空槽常驻隐藏 img 都会被"zone 出现新 img"误判成功。确认必须：槽位级 zone + 排除 `.weui-desktop-dialog__wrp` 子树 + 对比上传前 src 集合；超时重传一次。图标槽定位用「封面后第一个 png」（赞赏 input 的 accept 也含 png）。
- **平台 API 字段口径（2026-09-10 改版事故，用户报"下载/发送/赞赏全错"）**：`home?f=json` 的 `DownloadNum/SendNum` 是**近期值**（No.6 实测 2/95），累计真值在 `TotalDownloadNum/TotalSendNum`（同单 168/4882），赞赏 `Rewards` 无 Total 对应。回写必须优先 Total 字段（platform_data.py 已修）。另外管理页 HTML 已改成标签/卡片式（"下载量"标签+值换行），旧的 Tab 表格文本解析（parse_rows_from_text）只能当降级兜底且大概率解析不出数。

