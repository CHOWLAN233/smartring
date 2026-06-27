@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ====================================
echo   SmartRing — 环形应用启动器
echo ====================================
echo.
echo 正在后台启动 (无控制台窗口) ...
echo 程序图标将出现在系统托盘中。
echo.

REM Use pythonw to avoid console window
start "" pythonw "%~dp0SmartRing.pyw"

if errorlevel 1 (
    echo.
    echo [错误] 启动失败。
    echo.
    echo 请确认:
    echo   1. Python 3 已安装 (python.org)
    echo   2. 依赖已安装: pip install -r requirements.txt
    echo.
    pause
) else (
    echo 启动成功! 查看系统托盘中的 SmartRing 图标。
    timeout /t 2 >nul
)
