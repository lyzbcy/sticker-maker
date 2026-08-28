# E 推广与介绍页 · 状态

> **何时读**：修改静态介绍页、精选表情、二维码或版本更新策略时。

## 已完成

- 介绍页位于 `desktop/site/`，桌面与 390 px 移动端已做视觉走查。
- 使用三张精选表情作为产品展示。
- 赞赏二维码、入群二维码、表情包二维码同时进入桌面应用与介绍页。
- `version.json` 包含版本、下载地址、更新说明、日期与 ZIP SHA-256。
- 页面发现版本变化时会刷新静态资源；应用启动与手动按钮读取同一清单。

## 2026-08-27 增量（prompt 落地：个人推广页/润物细无声/求好评/强制刷新/更新日志）

- 关于页升级：作者卡片（头像 + 捞鱼工作室署名）、一键直达（个人主页/给个 Star/提建议/检查更新）、自家表情走马灯；`PromotionConfig` 新增 `studio_name/homepage_url/avatar_url/repo_url/discussions_url`（promotion.json 可覆盖）。
- 表情植入：主页空态提示 + 关于页走马灯（自家 IP 表情，`featured` 接口复用）。
- 求好评弹窗 `ReviewAskModal`：成功发布 ≥2 次触发，关闭后 15 天静默（localStorage `review_ask_last_shown`）。
- 站点 `desktop/site/index.html`：右上角「最近更新 + 一键刷新」组件（sessionStorage 防循环：自动强刷每版本一次、手动刷每次会话最多 3 次后退化普通 reload）。
- 自适应更新补全（`desktop/src/main/updater.js`）：每天首检（`update-check.json`）、流式下载进度（任务栏 + 底边栏活动流）、国内代理提醒、失败一键重试/跳发布页兜底。

## 发布纪律

1. 先生成最终 ZIP。
2. 重算 SHA-256。
3. 更新 `desktop/site/version.json`。
4. 发布 ZIP 与网站。
5. 用线上 URL 验证下载、清单与二维码。
