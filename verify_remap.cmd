@echo off
chcp 65001 >nul
echo 请先在任务管理器结束 pythonw.exe (软件方案), 再按侧键.
echo.
py -3.10 "%~dp0verify_remap.py" 45
pause
