# A 核心生图引擎 · 状态

> **何时读**：修改概率、生图、参考图库、故事、抠图、裁切或资源产出时。

## 已完成

- 四阶段管线：准备 → 生成 → 后处理 → 发布资源。
- 参考图库、故事、提示词排列组合三种生成路径。
- 单/双/三/四人概率，角色概率，同角色多 base 概率。
- 多人模式按角色权重无放回选角色，并为每个角色独立抽取 base。
- `#ff00ff` 洋红背景约束、禁阴影提示、自动抠图。
- 1×1、2×2、3×3、4×4；按需裁切、抠图、含义预检和重命名。
- 进度事件包含阶段、说明、百分比与 ETA。
- 自定义 base 上传与 Codex 生成；自定义角色资源隔离。
- 参考图库路径与全部偏好持久化。

## 验证

- Python 全套 165 tests passed。
- PyInstaller arm64 CLI 构建通过。
- 打包 CLI 冒烟：版本、4 个角色/12 张 base、日志、Agent、推广配置均正常。
- Codex 检测在打包环境返回 image ready。

## 已知边界

- 本轮没有额外消耗用户生图额度跑完整真实生成；生成适配器与管线由单元/集成测试覆盖。
- Codex 调用期间的取消粒度受外部命令返回速度限制。
- 当前分发 CLI 为 Apple Silicon；Intel/Windows 留给后续发行版。

## 关键文件

- `sticker_engine/sticker_engine/stages/`
- `sticker_engine/sticker_engine/providers/`
- `sticker_engine/sticker_engine/pipeline/`
- `sticker_engine/sticker_engine/config/`
- `sticker_engine/sticker_engine/cli.py`
