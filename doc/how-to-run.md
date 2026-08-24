# 怎么跑 / 怎么测 A

> **何时读**：要运行或测试 sticker_engine。

## 环境

- Python 3.9+（开发用 3.9.6 / 3.12 均可）
- venv 在 `sticker_engine/.venv/`
- 依赖：Pillow、numpy、PyYAML、pytest（都在 venv 里）

## 首次 setup

macOS：

```bash
cd <仓库根>/sticker_engine
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows（Git Bash 或 cmd）：

```bat
cd <仓库根>\sticker_engine
.venv\Scripts\activate
pip install -e ".[dev]"
```

桌面端（desktop/）：`npm ci`；开发跑 `npm run electron:dev`（会自动找
`../sticker_engine/.venv` 里的 venv Python；不在默认位置时设环境变量
`STICKER_ENGINE_PYTHON` 指向 venv python 可执行文件）。

## 跑测试

```bash
cd sticker_engine && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pytest -q                    # 全套件
pytest tests/providers/ -q   # 只测某层
pytest -k chromakey -v       # 只测某特性
```

桌面端：`cd desktop && npm test`（vitest）。

## CLI 冒烟（需真实 codex）

```bash
cd sticker_engine && source .venv/bin/activate
python -m sticker_engine.cli
```
前提：本机已装并登录 codex CLI（`codex login`）。会真实调 codex 生图，产出在
Mac `~/Library/Application Support/StickerEngine/episodes/`、
Windows `%APPDATA%\StickerEngine\episodes\`。

## 当作库用

```python
from sticker_engine import StickerEngine, Config
from sticker_engine.config.paths import resolve_paths, current_platform

config = Config.placeholder()
config.paths = resolve_paths(current_platform())
engine = StickerEngine(config)
episode = engine.run(progress_callback=lambda ev: print(ev.message))
if not episode.success:
    print("失败：", episode.errors, episode.aborted_reason)
```

## 关键路径

- 用户数据：Mac `~/Library/Application Support/StickerEngine/`；Windows `%APPDATA%\StickerEngine\`
- codex 输出：`~/.codex/generated_images/`（两平台一致）
- 内置资产：包内 `sticker_engine/resources/`（只读）
