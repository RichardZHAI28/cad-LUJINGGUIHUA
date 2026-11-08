@echo off
chcp 65001 >nul
cd /d "%~dp0工程"
python run.py
if errorlevel 1 pause
