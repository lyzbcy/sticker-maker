# 系列命名 / 作品库参考

> **何时读**：改系列、专辑命名、作品库、详情页时。

## 数据文件

| 文件 | 内容 |
|---|---|
| `%APPDATA%/StickerEngine/series.json` | `[{id, name, start_number, next_number, intro_prompt, role_asset_map}]` |
| `<episode>/meta.json` | `{series_id, series_name, number, album_name, intro, published, cover_mode, ...}` |
| `<episode>/meaning_map.json` | 16 格含义词顺序（发布上传排序用） |

## 命名规则

- 系列从 `start_number` 起编号：专辑名 = `系列名 + 空格 + 编号`（如「周三涵做表情 63」）
- 编入时 `take_number`：取 `next_number` 并自增；**删除 episode 必须回滚 next_number**（否则编号断档）
- run 成功后若 prefs 设了 `default_series_id` → 自动编入默认系列（详情页可改）

## CLI 命令

`list_series` / `save_series`（增删改，校验 default_series_id 引用存在）、`get_episode` / `update_episode_meta`（改名/介绍/素材设置）、`regen_intro`（系列提示词重生成介绍）、`regen_assets`（横幅/封面/图标四模式重生成）、`list_episodes`（含 album_name/series/published/complete）。

## 一键更新 & 物理删除（2026-08-27）

- `sync_platform_status`（`publish/status.py`）：打开平台管理页分页扫描（写死逻辑免 token，复用发布登录体系，只读），按专辑名归一化前缀匹配本地作品，把 状态/下载/发送/赞赏 写进 meta 的 `platform_*` 字段；未匹配的平台记录原样带回（脏数据提示）。
- `delete_episode`：物理删除作品文件夹。纪律：路径必须在 episodes 根内；占系列最新一号才回滚 next_number（中间号删除留空档防撞号）。
- `STICKER_ENGINE_USER_DATA` 环境变量可整体迁移用户数据目录（测试隔离用）。

## 前端

- `EpisodesPanel`（phase=episodes）：全部作品网格 + 系列筛选 chips；未完成（0 张）标记不可发布
- `EpisodeDetailPanel`（phase=episodeDetail）：16 张预览 / 编入系列（下拉显示各系列下一编号）/ 手动改名 / 介绍编辑+AI重生成 / 素材四模式 / 发布（含 warnings 展示）
- 入口：MainScreen 最近作品（点击进详情）+ 查看全部
