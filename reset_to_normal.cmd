@echo off
chcp 65001 >nul
echo 正在把鼠标按键复位为出厂行为...
py -3.10 "%~dp0reset_to_normal.py"
echo.
echo 如果左键仍然无反应, 请拔掉鼠标 USB 等 3 秒再插回。
pause
