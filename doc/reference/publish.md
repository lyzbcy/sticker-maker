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
2. **表单填写纪律**：
   - radio/checkbox 是**隐藏 input**，必须点可见 `<label>` 文本，点前判 checked 态（点两次=取消）
   - 文件上传：可见 file input 槽位 [0]=横幅(jpg) [1]=封面(png) [2]=图标(png)
   - 上架地区/下载地区是两组独立 radio
   - **「涉及肖像权授权」「涉及版权授权」永远不勾**（自制角色无需授权，勾了反而要求证明文件）
3. **提交判定（绝不假成功）**：以页面出现「提交成功」字样或跳回管理页为准；检测到 validation 错误关键词 → 失败 + 截图；warnings 列表（哪步可能没填上）随结果返回前端展示。
4. **发布状态回写**：成功后写 episode `meta.json` 的 `published: true` + 时间。

## 发布前置校验（cli.py publish 命令）

专辑名必须是正式名（系列编号名或手改名），还是时间戳目录名 → 直接 fail 并提示先去详情页命名。
