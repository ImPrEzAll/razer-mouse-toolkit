@echo off
chcp 65001 >nul
py -3.10 "%~dp0status.py"
if "%~1"=="" pause
