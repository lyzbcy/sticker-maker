# C 发布与上架 · 完成度与技术债

> **何时读**：要看 C 做到哪了、有哪些坑没填。

## 完成度：可交付（待真实平台冒烟）

- Publisher 单弹提交（24 步，迁移自 publisher skill）
- Shelf 批量预约上架（7 步 + 翻页 + 自我审查）
- Batch 批量发布（分批 + 断点续传 + 失败重试）
- publish-cli 入口（publish/batch/shelf/login/logout）
- selectors.py 集中管理选择器（平台改版易修）
- 登录态 storage_state 持久化（playwright 原生）

## 测试

- C 单测：46 passed（EpisodeAssets 解析、Publisher 步骤序列、Shelf 状态判定、Batch 续传、Config）
- 全项目：131 passed（A 85 + B CLI + C 46）
- 全用 mock playwright Page，不启真实浏览器

## 用法

```bash
cd sticker_engine && source .venv/bin/activate

# 首次：登录（浏览器扫码/账号密码，存登录态）
python -m sticker_engine.publish.cli login

# 单弹发布
python -m sticker_engine.publish.cli publish --dir <episode目录>

# 批量发布
python -m sticker_engine.publish.cli batch --start 1 --end 10
python -m sticker_engine.publish.cli batch --start 1 --end 10 --resume

# 自动上架审核通过的
python -m sticker_engine.publish.cli shelf --limit 3
```

## ⚠️ 必须你手动验证（C 的已知未完成项）

C 的 mock 测试验证了"选择器被正确使用"，但**没在真实微信平台跑过**。需要你回来：

1. **配置 .env**：在项目根或 publisher skill 目录建 `.env`：
   ```
   WECHAT_STICKER_ACCOUNT=你的账号
   WECHAT_STICKER_PASSWORD_ENCODED=<密码的base64>
   ```
   （或用 `publish-cli login` 扫码首次登录）
2. **真实发布一弹**：`publish-cli publish --dir <一个真实 episode>`
3. **平台改版时修 selectors.py**：选择器失效会截图保现场（`_publish_error.png`）

## 遗留技术债

| # | 问题 | 说明 |
|---|---|---|
| 赞赏图缩略图验证 | 经验12（上传后查缩略图防假阳性）未实现运行时验证，只做了文件存在性前置校验 | mock 不好覆盖真实 DOM，真实冒烟时观察是否需要补 |
| 提交成功判定较宽 | "URL 离开表单页即判成功"，原 skill 也承认是 known-gap | 真实冒烟时收紧（要求"审核中"文案） |
| 桌面 .app 不含发布 | C 是独立 CLI（开发者用），不进 B 的 .app 分发包 | 设计如此（C1 决策） |

## 架构定位

C **复用 A 的 episode 产物**（读 `最终版/横幅/封面/图标/介绍.txt/本次制作角色.md`），但**不 import A 核心库**——独立的发布层，只读文件。这样 C 可单独运行，不拖累粉丝的 .app。
