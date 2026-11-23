@echo off
rem razerctl launcher - Razer DeathAdder Essential control (no Synapse needed)
py -3.10 "%~dp0razerctl.py" %*
if "%~1"=="" pause
