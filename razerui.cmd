@echo off
chcp 65001 >nul
title 雷蛇鼠标控制台
echo 正在启动控制台，浏览器会自动打开...
start "" /min cmd /c "timeout /t 2 >nul && start "" http://127.0.0.1:18765"
py -3.10 "%~dp0razer_server.py"
echo.
echo 服务已停止。
pause
