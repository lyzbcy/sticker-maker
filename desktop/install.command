#!/bin/bash
# 双击此文件去除 macOS 隔离标记并提示安装
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
APP_PATH="$SCRIPT_DIR/表情包一键制作.app"

if [ ! -d "$APP_PATH" ]; then
  osascript -e 'display dialog "未找到「表情包一键制作.app」，请确认它与本脚本在同一文件夹。" buttons {"好"} defaultButton 1 with title "安装失败"'
  exit 1
fi

xattr -dr com.apple.quarantine "$APP_PATH"

osascript -e "display dialog \"已去除隔离标记。\n\n请将「表情包一键制作」拖到「应用程序」文件夹完成安装。\n\n之后可以从启动台打开它。\" buttons {\"好，我去拖\"} defaultButton 1 with title \"安装完成\""
