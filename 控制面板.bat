@echo off
chcp 936 >nul
cd /d "%~dp0"
if not exist "控制.txt" ( echo. > "控制.txt" )
start "" notepad "控制.txt"
