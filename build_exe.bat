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
echo [1/5] 安装 Python 依赖...
pip install -r requirements.txt -q
pip install pyinstaller -q

REM 3. 生成图标
echo [2/5] 生成应用图标...
python generate_icon.py
if not exist "smartring.ico" (
    echo [警告] 图标生成失败，将使用默认图标
)

REM 4. 构建 EXE
echo [3/5] 正在构建 SmartRing.exe (可能需要几分钟)...
pyinstaller SmartRing.spec --clean --noconfirm

REM 5. 同步配置文件到 dist\ (始终用最新版本)
echo [4/5] 同步 config.json 到 dist\ ...

REM 如果 dist 中的 config 比根目录的更新，先回同步到根目录
if exist "dist\config.json" if exist "config.json" (
    powershell -Command "if ((Get-Item 'dist\config.json').LastWriteTime -gt (Get-Item 'config.json').LastWriteTime) { Copy-Item 'dist\config.json' 'config.json' -Force }" >nul 2>&1
)

if exist "config.json" (
    echo   复制 config.json -^> dist\config.json
    copy /y "config.json" "dist\config.json" >nul
) else if exist "dist\config.json" (
    echo   复制 dist\config.json -^> config.json
    copy /y "dist\config.json" "config.json" >nul
    echo   复制 config.json -^> dist\config.json
    copy /y "config.json" "dist\config.json" >nul
) else (
    echo   未找到 config.json，首次运行 EXE 时将自动创建默认配置
)

REM 6. 检查结果
echo.
if exist "dist\SmartRing.exe" (
    echo [5/5] 构建成功！
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
