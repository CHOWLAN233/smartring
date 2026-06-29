@echo off
cd /d "%~dp0"
python "%~dp0rebuild.py" %*
if errorlevel 1 pause
