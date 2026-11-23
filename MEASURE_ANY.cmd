@echo off
title Polling Rate - Any Mouse
cd /d "%~dp0"
echo ============================================================
echo  Polling Rate Check - ANY mouse
echo ============================================================
echo.
echo  Unplug the Razer, plug in any other USB mouse, then run this.
echo  It measures whatever mouse is connected - no gear switching,
echo  no Razer driver needed.
echo.
echo  Keep moving the mouse in circles when prompted.
echo ------------------------------------------------------------
py -3.10 measure_rate3.py 3 --rate current --any
echo.
echo Done.
pause
