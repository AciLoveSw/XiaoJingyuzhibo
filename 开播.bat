@echo off
chcp 936 >nul
cd /d "%~dp0"
title 小鲸鱼 · 开播
set PY=python
where python >nul 2>nul || set PY=py
start "信号" /min %PY% "%~dp0标记服务.py"
timeout /t 1 >nul
start "直连" /min %PY% "%~dp0抖音直连.py"
timeout /t 2 >nul
start "主播引擎" /min %PY% "%~dp0主播引擎.py"
echo.
echo 三个窗口最小化运行：信号 / 直连 / 引擎。
echo 检查网页：http://127.0.0.1:8788/形象.html
timeout /t 6 >nul
