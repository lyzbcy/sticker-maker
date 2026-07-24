@echo off
setlocal
chcp 65001 >nul

echo.
echo ============================================
echo   正在关闭概率控制台
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -like '*server.js*' -and $_.CommandLine -like '*sticker*' }; if (-not $procs) { Write-Host '[提示] 未找到正在运行的概率控制台进程。' } else { $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[关闭] 已终止进程 PID: ' + $_.ProcessId) } }"

echo.
echo [验证] 检查端口释放...
netstat -ano | findstr ":3412" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
  echo [完成] 端口 3412 已释放
) else (
  echo [警告] 端口 3412 仍被占用，尝试强制释放...
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3412" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
    echo [强制] 已终止 PID %%a
  )
)

echo.
echo [完成] 概率控制台已关闭
timeout /t 2 /nobreak >nul
