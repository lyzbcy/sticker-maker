# C 微信发布与上架 · 状态

> **何时读**：修改微信表情开放平台提交、批量发布、上架或页面选择器时。

## 已完成

- 单弹发布流程、批量发布、断点续传、失败重试。
- 审核通过后的批量上架与分页处理。
- 登录态复用、发布前资源检查、失败现场截图。
- 桌面结果页和历史结果页均可发起微信提交。
- Agent 可触发 publish、batch、shelf 动作及计划任务。
- 默认发布素材随 PyInstaller CLI 一起分发。

## 当前结论

自动化代码和 mock 页面测试通过，但没有把真实平台账号当成测试夹具。微信页面会改版、提交会产生真实外部影响，因此不能声称“真实发布已通过”。

## 发布前人工冒烟

1. 在桌面应用中完成或复用微信登录。
2. 选择一弹可公开的测试表情。
3. 点击“提交微信”，确认全部图片、横幅、封面、图标、介绍和赞赏素材预览正确。
4. 确认提交后进入明确的“审核中”状态。
5. 若失败，依据现场截图更新 `publish/selectors.py`。

## 关键文件

- `sticker_engine/sticker_engine/publish/publisher.py`
- `sticker_engine/sticker_engine/publish/batch.py`
- `sticker_engine/sticker_engine/publish/shelf.py`
- `sticker_engine/sticker_engine/publish/selectors.py`
- `desktop/src/renderer/components/ResultPreview.vue`
