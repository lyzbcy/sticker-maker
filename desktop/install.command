#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PATH="$SCRIPT_DIR/表情包一键制作.app"
INSTALL_ROOT="${STICKER_INSTALL_ROOT:-/Applications}"
DEST_PATH="$INSTALL_ROOT/表情包一键制作.app"
UPDATE_MODE="${1:-}"

show_error() {
  /usr/bin/osascript -e "display dialog \"$1\" buttons {\"好\"} default button 1 with title \"安装失败\""
}

if [ ! -d "$APP_PATH" ]; then
  show_error "未找到「表情包一键制作.app」，请确认它与安装文件在同一文件夹。"
  exit 1
fi

if [ -d "$DEST_PATH" ] && [ "$UPDATE_MODE" != "--update" ]; then
  CHOICE=$(/usr/bin/osascript -e 'button returned of (display dialog "应用程序中已有「表情包一键制作」。要替换为这个版本吗？" buttons {"取消", "替换"} default button "替换" cancel button "取消" with title "表情包一键制作")' 2>/dev/null || true)
  if [ "$CHOICE" != "替换" ]; then
    exit 0
  fi
fi

if [ "$UPDATE_MODE" = "--update" ] && [ "${STICKER_INSTALL_SKIP_DELAY:-0}" != "1" ]; then
  /bin/sleep 2
fi

/usr/bin/xattr -dr com.apple.quarantine "$APP_PATH" 2>/dev/null || true

install_app() {
  /usr/bin/ditto "$APP_PATH" "$DEST_PATH"
  /usr/bin/xattr -dr com.apple.quarantine "$DEST_PATH" 2>/dev/null || true
}

if ! install_app 2>/dev/null; then
  /usr/bin/osascript - "$APP_PATH" "$DEST_PATH" <<'APPLESCRIPT'
on run argv
  set sourcePath to item 1 of argv
  set destinationPath to item 2 of argv
  do shell script "/usr/bin/ditto " & quoted form of sourcePath & " " & quoted form of destinationPath & " && /usr/bin/xattr -dr com.apple.quarantine " & quoted form of destinationPath with administrator privileges
end run
APPLESCRIPT
fi

if [ "${STICKER_INSTALL_NO_LAUNCH:-0}" != "1" ]; then
  /usr/bin/open "$DEST_PATH"
fi
if [ "$UPDATE_MODE" != "--update" ] && [ "${STICKER_INSTALL_NO_LAUNCH:-0}" != "1" ]; then
  /usr/bin/osascript -e 'display dialog "安装完成，应用已复制到「应用程序」并启动。" buttons {"好"} default button 1 with title "表情包一键制作"'
fi
