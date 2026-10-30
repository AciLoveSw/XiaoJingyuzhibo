@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在关闭旧的监听器...
taskkill /F /IM WssBarrageServer.exe >nul 2>&1
timeout /t 2 >nul
echo 正在启动新的（带完整日志）...
start "" "%~dp0_弹幕监听\WssBarrageServer.exe"
timeout /t 3 >nul
echo.
echo 完成。如果这里没有报错，监听器已经起来了。
echo 这个窗口可以关掉。
timeout /t 5 >nul
