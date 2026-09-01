---
name: sticker-maker-dev
description: 表情包一键制作（Electron + Python 引擎）的专用开发 skill。开发任何功能、修 bug、发版前必读。指引入口：doc/README.md 是渐进式索引，按模块跳转 doc/reference/ 专题文档。
---

# 表情包一键制作 · 开发 Skill

接管本项目的开发任务时，**先读这个 skill，再按需深入**，不要盲目翻代码。

## 项目一句话

Electron 桌面应用：向导配置 → codex 生图（主力=参考图弹药模式，备胎=排列组合；故事模式默认关）→ 内容感知切图/抠图 → 系列自动命名 → Playwright 自动提交到微信表情开放平台。仓库：`github.com/lyzbcy/sticker-maker`。

## 目录地图

| 路径 | 是什么 |
|---|---|
| `sticker_engine/sticker_engine/` | Python 核心引擎（JSON-lines over stdin/stdout 协议，被桌面端当子进程调） |
| `desktop/src/` | Electron 应用（main/preload/renderer，Vue3 + Pinia，phase 当路由） |
| `desktop/site/` | 静态介绍/发布页（部署到 lyzbcy.github.io/sticker-maker） |
| `doc/` | **AI Memory：渐进式文档入口，先读 `doc/README.md`** |
| `doc/reference/` | 模块专题文档（管线/发布/系列命名…），按需读 |

## 开发命令

```bash
# 后端测试（venv 在 sticker_engine/.venv）
cd sticker_engine && .venv/Scripts/python.exe -m pytest tests -q --ignore=tests/agent

# 前端测试
cd desktop && npx vitest run

# 桌面 dev 启动（引擎需 PYTHONPATH 指向 sticker_engine 源码）
cd desktop && PYTHONPATH=../sticker_engine npx electron . --remote-debugging-port=9235

# 用户数据（prefs/episodes/series）在 %APPDATA%/StickerEngine/
```

## 必须遵守的项目纪律

1. **改完必须跑测试**：后端 pytest（200+）+ 前端 vitest（32+），全绿才交付。
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

## 深入阅读

按任务查 `doc/README.md` 的模块表 → `doc/reference/pipeline.md`（生图管线） / `publish.md`（微信发布） / `series.md`(系列命名)。
