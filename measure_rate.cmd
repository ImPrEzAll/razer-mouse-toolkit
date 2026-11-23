@echo off
title Mouse Polling Rate Test
cd /d "%~dp0"
py -3.10 measure_rate3.py %*
echo.
echo Report saved to rate_report.txt
pause
