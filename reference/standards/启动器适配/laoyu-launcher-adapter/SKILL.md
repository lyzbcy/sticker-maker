---
name: laoyu-launcher-adapter
description: 为捞鱼软件中心适配 Windows 软件、安装包和便携 ZIP。新开发软件、变更主程序名称、制作发布包、接入产品目录或排查下载后无法识别时使用，提供适配规范与本地只读自查脚本。
---

# 启动器适配开发流程

1. 先读待开发软件根目录的 SKILL.md、docs/agent.md 和对应模块文档，遵守原有版本与更新约定。
2. 阅读本 skill 的 `references/适配规范.md`。先决定稳定产品 ID、主程序名、安装版或便携版；不要把安装器当成主程序。
3. 将 `assets/launcher-adapter.example.json` 复制到软件根目录为 `launcher-adapter.json`，填入真实信息。路径相对该描述文件；不能保留模板哈希或假下载地址。这个文件是开发验收输入，现有启动器不会自动读取它。
4. 开发、构建后核对真实主程序、原始图标、版本与发布包。安装版提供开始菜单、卸载登记、DisplayIcon/InstallLocation；桌面快捷方式和安装后打开由用户选择。任务栏固定交给 Windows 用户操作。
5. 运行下列自查（在本 skill 目录执行；任意工作目录运行时使用脚本绝对路径）：

   ```powershell
   python scripts/check_adapter.py '软件项目路径\launcher-adapter.json' --launcher-root 'E:\共享\创业\捞鱼软件中心' --strict --report '软件项目路径\verification\launcher-adapter-report.json'
   ```

6. 依照失败项修改产品构建配置与启动器登记。修改启动器前先读它的 SKILL.md 和 docs/agent.md。不能只修改远端 catalog：本机识别和 ZIP 自动准备是随客户端发版的白名单。
7. 需要验收本机识别时加 `--installed`，它调用启动器真实 detectInstalled，只读查询且不启动软件。用户未安装时该项失败，不能靠手动关联冒充自动识别成功。
8. 自查通过后仍要按规范人工验收：实际安装/解压、重开启动器、显示“打开软件”、点击打开、更新后仍识别。仅运行脚本不能宣称完成这些验收。保留报告，在产品 SKILL.md / docs/agent.md 中添加本适配规范的入口与版本文件位置。

## 交付条件

- 代码、项目文档和版本一致，按项目约定备份源码；公开下载包遵从已有授权，源码不因适配而改为公开。
- 没有修改白名单并发布新启动器时，要明确报告“产品已准备，当前客户端尚未支持”。
- 自查退出码：0 通过，1 不通过，2（仅 strict 模式）存在未完成事项。无 Node 时产品包检查仍可运行，但启动器集成检查不能算完成。
- 本工具不下载、不安装、不执行产品、不写注册表；仅报告路径由用户指定时写文件。
