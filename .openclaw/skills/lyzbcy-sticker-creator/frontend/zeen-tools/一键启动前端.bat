@echo off
setlocal
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

cd /d "%PROJECT_ROOT%"

echo.
echo ============================================
echo   表情包概率控制台
echo   端口: 3412
echo ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 Node.js，请先安装 Node.js。
  pause
  exit /b 1
)

if not exist "node_modules\js-yaml" (
  echo [安装] 正在安装依赖...
  call npm install --silent
  if errorlevel 1 (
    echo [错误] npm install 失败
    pause
    exit /b 1
  )
)

echo [启动] 正在启动服务器...

start "sticker-dashboard" cmd /c "cd /d "%PROJECT_ROOT%" && node server.js"

echo [检查] 等待服务器就绪...
:wait
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://localhost:3412/api/config' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 goto wait

echo [就绪] 服务器已启动
echo.
echo 正在打开浏览器...
start "" http://localhost:3412

echo.
echo [提示] 关闭此窗口不会停止服务器。使用一键关闭前端.bat 来关闭。
pause >nul
