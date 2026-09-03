@echo off
chcp 65001 >nul
title 表情包制作·开发版
cd /d E:\github\sticker-maker\desktop
echo 正在启动开发版（首次约 10 秒）...
echo 提示：这个黑窗口要一直开着，关掉它 = 关掉软件
npm run electron:dev
pause
