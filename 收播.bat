@echo off
chcp 936 >nul
cd /d "%~dp0"
title 小鲸鱼 · 收播
echo.
echo   正在停止后台服务...
echo.
python "%~dp0收播.py"
echo.
echo   好了。OBS 和直播伴侣不受影响，可以单独关。
timeout /t 4 >nul
