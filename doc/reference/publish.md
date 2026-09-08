# 微信发布参考

> **何时读**：改发布自动化、登录、表单填写、提交判定时。

## 组件

| 文件 | 职责 |
|---|---|
| `publish/browser.py` | Playwright 驱动；**账号密码自动登录**（storage_state 缓存登录态，失效自动重登） |
| `publish/credentials.py` | keyring 存取（SERVICE=`StickerEngine-WeChatPublish`，Windows 凭据管理器/macOS 钥匙串） |
| `publish/publisher.py` | 12 步表单填写 + `_verify_form` 提交前自检（12 必填项） + 提交判定 |
| `publish/selectors.py` | 页面选择器（表单改版先重抓 DOM 再改这里） |

## 发布流程要点

1. **登录**：优先 storage_state（`%APPDATA%/StickerEngine/publish_storage.json`）；失效走密码重登（重新登录按钮 → 账号密码登录 tab → placeholder 定位填写 → 记住账号 → 登录）。**不要用扫码**（登录态半天就失效，用户明确拒绝）。
2. **上传顺序（2026-09-02 事故后重构，别改回去）**：新建模式 = **素材先传、表情图后传**——
   赞赏(勾选+引导语+两图) → 横幅/封面/图标（逐张等各自槽位缩略图确认） → 16 张表情图 → 含义词 → 专辑名/介绍/版权 → 分类 → 价格 → 赞赏兜底（先前未就绪则补） → 提交。
   老项目 skill 的实战经验：表情图批量 set 后平台上传通道拥堵，紧随其后的素材 set 容易不落地；素材先行 + 槽位级确认后稳定性更好。
3. **表单填写纪律**：
   - radio/checkbox 是**隐藏 input**，必须点可见 `<label>` 文本，点前判 checked 态（点两次=取消）
   - 文件上传：**可见** file input 槽位 [0]=横幅(jpg) [1]=封面(png) [2]=图标(png) [3/4]=赞赏(勾选后渲染)。图标定位必须用「封面之后第一个 png」——赞赏图 input 的 accept 同样含 png，用「最后一个 png」会把图标错传进赞赏致谢图槽
   - 上架地区/下载地区是两组独立 radio
   - **「涉及肖像权授权」「涉及版权授权」永远不勾**（自制角色无需授权，勾了反而要求证明文件）
4. **素材上传确认（防假阳性，三层）**：
   - 槽位级：set 后等**该槽 zone 内**出现新增的可见 img（对比上传前 src 集合），且**排除裁剪 dialog 子树内的预览图**（裁剪框挂在 zone 里，其预览图曾被误判为上传成功）
   - 裁剪框：素材 set 后平台可能弹「裁剪横幅/封面/图标」dialog——不点「确定」上传就不落地（`_confirm_crop` 轮询处理，这是提交红字「横幅不能为空」的经典来源）
   - 重试：确认超时 → 清挂起裁剪框 → 重传一次，两次失败记 warning
5. **含义词**：表情图上传后输入框**逐个渲染**——填完必须验证「格数 + 每格有值」，不足等 1s 重填（最多 3 轮）。
6. **提交判定（绝不假成功）**：以页面出现「提交成功」字样或跳回管理页为准；检测到 validation 错误关键词 → 失败 + 截图；warnings 列表（哪步可能没填上）随结果返回前端展示。
7. **发布状态回写**：成功后写 episode `meta.json` 的 `published: true` + `platform_status: "待审核"` + 时间。

## 历史事故档案（别再踩）

- **71-89 批量全失败（2026-09-02）**：`_step_upload_assets(only=[...])` 主流程传英文键
  `["banner","cover","icon"]`，函数内部却用中文标签 `("横幅",...)` 做 `in` 匹配 →
  pairs 被过滤成**空列表** → 素材上传整体空转且**零告警** → 提交红字
  「横幅不能为空/封面不能为空」。同一套代码 61-69 却全过——因为它们发布于
  only 参数引入之前。教训：**过滤参数的键名两套写法（中/英）必须做映射**
  （`_ASSET_ONLY_ALIAS`），且"循环体没执行"要能被测试捕获
  （`test_step_upload_assets_only_english_keys` 守护）。
- **裁剪框假阳性**：素材上传后弹「裁剪横幅」dialog，未点确定 → 上传不落地；
  且 dialog 内预览图会被"zone 内出现新 img"判定误读为成功。判定必须排除
  `.weui-desktop-dialog__wrp` 子树 + 主动点掉「确定」。
- **全页计数判定的假阳性**：旧版"数全页含格式说明文字且有 img 的 div"等待——
  空槽 zone 里常驻的隐藏 dialog img 让条件恒真，等于没等。必须槽位级判定。

## 发布前置校验（cli.py publish 命令）

专辑名必须是正式名（系列编号名或手改名），还是时间戳目录名 → 直接 fail 并提示先去详情页命名。

## 平台操作互斥与安全取消（2026-09-07 增量，doc 实测建议第 5 步）

- **互斥**：`cli.py` 的 `_platform_exclusive`（非阻塞锁）包住四个平台命令——
  `sync_platform_status` / `shelf_passed` / `publish_episode` /
  `fix_and_republish`（仅其编辑器重提段）。并发第二个命令**立刻失败**并提示
  谁在跑（不排队：平台浏览器登录态与 meta.json 会被竞写破坏）。
- **安全取消**：sync 与 shelf 注册 `_stop_events[req_id]`，`stop` 命令可取消：
  - `sync_rows` 逐单理由抓取前检查 `should_stop`：取消时 `cancelled: true,
    complete: false`，已抓理由保留，剩余跳过；状态已在第一批全量落库。
  - shelf 逐单上架前检查：取消时返回 `cancelled + remaining` 列表，
    已上架单 meta 已落库（逐单保存，中断不丢已完成结果）。
- **失败重试**：沿用既有语义——理由失败单下次同步只补失败单
  （`platform_reject_checked_cycle` 守卫）；shelf 失败单在 `failed` 列表
  带原因返回，重跑即可（`fresh_passed` 语义不变）。
- 测试：`tests/publish/test_fast_status.py` 新增 3 例（互斥立刻失败/锁释放后
  可跑、sync 取消保留部分理由、shelf 取消保留已完成 + remaining）。

### CR 修复补记（2026-09-07，老田/土豆双评审）

- **取消语义统一**：任何阶段的取消都返回 `ok + cancelled: true`（不再用
  fail 表达取消）；登录前取消/降级路径取消/理由队列取消/上架逐单取消一致。
- **取消拦登录段**：shelf 在 sync 返回后立即检查 stop，取消时不启动
  Playwright/不登录；sync_rows 状态落库循环也逐单检查（`updated` 计数
  从 0 累计，取消时如实反映已写入数）。
- **legacy 降级路径**接入 `should_stop`（翻页/理由抓取逐轮检查）。
- **fix_and_republish 锁**改为标准 `with _platform_exclusive(...)`。
- **前端取消入口**：`pythonBridge.js` 追踪可取消平台命令
  （`CANCELLABLE = run/sync_platform_status/shelf_passed`），`stop()` 缺省
  target 时先停 run、再停平台命令；作品库页同步/发布中显示「✕ 取消」
  按钮，取消结果显示剩余未处理清单（`cancelled`/`remaining`）。
- **驳回理由全文入库**（不再 `[:500]` 截断）：meta.json 里的
  `platform_reject_reason` 是平台原文全文，前端展示自行截断。
- 新测试：`test_fix_republish_publish_step_is_exclusive`、
  `test_shelf_sync_phase_makes_zero_detail_requests`、
  `tests/pythonBridge.test.js` stop 贯通 2 例。

## 真机排障：同步失败「未知原因」（2026-09-07 23:44 实测）

三层叠加，已全修：
1. **凭据键名不匹配**：旧版引擎（2026-07）把密码存成 `password_b64`，
   现 `load_credentials` 只读 `password` → 读不到密码 → 登录失败。
   修复：兼容读 `password_b64`（`credentials.py`，`test_credentials.py` 3 例）。
   修复后真机实测：自动登录成功，列表 303 单全量返回（与 doc 实测一致）。
2. **失败原因在 Electron main 层被吞**：`python-command` 的 catch 把 CLI 的
   fail 事件压成 `{error: err.message}`（事件对象上 message 是 undefined）
   → 前端读 `errors[0].message` 落空 → 显示「未知原因」。
   修复：`PythonBridge.flattenError` 统一拍平成 errors 数组。
3. 已知项（不修）：本机若有旧命名作品目录（如 `周三涵做表情61`，非
   `episode_*` 且无 meta.json），`_match_rows` 不扫描 → matched=0；
   Windows 主力机不受影响。
