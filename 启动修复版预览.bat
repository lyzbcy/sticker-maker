@echo off
chcp 65001 >nul
title 表情包一键制作 - 修复版本地预览
cd /d "%~dp0desktop"

echo ============================================
echo   表情包一键制作 - 修复版本地预览
echo   含修复：向导完成 / S1 挂起 / 底部状态栏
echo ============================================
echo.

set "STICKER_ENGINE_PYTHON=%~dp0sticker_engine\.venv\Scripts\python.exe"
set "PYTHONPATH=%~dp0sticker_engine"

echo [启动] 新前端 + 新引擎（首次窗口出现约需 5~10 秒）
echo [提示] 底部状态栏点击可展开实时日志
echo.
npx electron .
