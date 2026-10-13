#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PATH="$SCRIPT_DIR/表情包一键制作.app"
INSTALL_ROOT="${STICKER_INSTALL_ROOT:-/Applications}"
DEST_PATH="$INSTALL_ROOT/表情包一键制作.app"
UPDATE_MODE="${1:-}"
OLD_PID="${2:-}"
READY_FILE="${3:-}"
show_error() {
if [ "${STICKER_INSTALL_NO_LAUNCH:-0}" = '1' ]; then printf '%s\n' "$1" >&2; return; fi
/usr/bin/osascript - "$1" <<'APPLESCRIPT'
on run argv
 display dialog (item 1 of argv) buttons {"好"} default button 1 with title "安装失败"
end run
APPLESCRIPT
}
if [ ! -d "$APP_PATH" ]; then show_error '未找到应用，请把安装文件和应用放在同一目录。'; exit 1; fi
if [ "$UPDATE_MODE" = '--update' ] && [[ "$OLD_PID" =~ ^[0-9]+$ ]]; then
  [ -n "$READY_FILE" ] && printf 'ready' > "$READY_FILE"
  for ((n=0;n<450;n++)); do /bin/kill -0 "$OLD_PID" 2>/dev/null || break; /bin/sleep 0.1; done
  if /bin/kill -0 "$OLD_PID" 2>/dev/null; then show_error '旧版尚未退出，请重新安装。'; exit 1; fi
elif [ -d "$DEST_PATH" ]; then
  CHOICE=$(/usr/bin/osascript -e 'button returned of (display dialog "已有表情包一键制作，要安装这个版本吗？作品和设置会保留。" buttons {"取消", "安装"} default button "安装")' 2>/dev/null || true)
  [ "$CHOICE" = '安装' ] || exit 0
fi
/bin/mkdir -p "$INSTALL_ROOT"
STAGE=$(/usr/bin/mktemp -d "$INSTALL_ROOT/.sticker-install-XXXXXX")
BACKUP="$INSTALL_ROOT/表情包一键制作.rollback-$(date +%Y%m%d%H%M%S).app"
rollback() {
  if [ -d "$BACKUP" ] && [ ! -d "$DEST_PATH" ]; then /bin/mv "$BACKUP" "$DEST_PATH"; fi
  show_error '安装未完成，旧版与作品已保留。请重试。'
}
trap rollback ERR
/usr/bin/ditto "$APP_PATH" "$STAGE/表情包一键制作.app"
/usr/bin/codesign --verify --deep --strict "$STAGE/表情包一键制作.app"
/usr/bin/xattr -dr com.apple.quarantine "$STAGE/表情包一键制作.app" 2>/dev/null || true
[ ! -d "$DEST_PATH" ] || /bin/mv "$DEST_PATH" "$BACKUP"
/bin/mv "$STAGE/表情包一键制作.app" "$DEST_PATH"
/bin/rmdir "$STAGE"
trap - ERR
if [ "${STICKER_INSTALL_NO_LAUNCH:-0}" != '1' ]; then /usr/bin/open "$DEST_PATH"; fi
