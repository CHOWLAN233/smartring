@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ==============================================
echo   SmartRing — 构建 EXE 安装包
echo ==============================================
echo.

REM 1. 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.7+
    pause
    exit /b 1
)

REM 2. 安装/更新依赖
echo [1/4] 安装 Python 依赖...
pip install -r requirements.txt -q
pip install pyinstaller -q

REM 3. 生成图标
echo [2/4] 生成应用图标...
python generate_icon.py
if not exist "smartring.ico" (
    echo [警告] 图标生成失败，将使用默认图标
)

REM 4. 构建 EXE
echo [3/4] 正在构建 SmartRing.exe (可能需要几分钟)...
pyinstaller SmartRing.spec --clean --noconfirm

REM 5. 检查结果
echo.
if exist "dist\SmartRing.exe" (
    echo [4/4] ✓ 构建成功！
    echo.
    echo   输出文件: dist\SmartRing.exe
    echo   文件大小:
    dir "dist\SmartRing.exe" | find "SmartRing.exe"
    echo.
    echo 双击 dist\SmartRing.exe 即可启动！
) else (
    echo [错误] 构建失败，请检查上方错误信息。
    pause
    exit /b 1
)

pause
