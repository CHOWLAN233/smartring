"""
SmartRing — 一键覆盖 & 启动工具

用法:
    python rebuild.py         构建 EXE + 替换 dist\ + 同步配置 + 启动 (默认)
    python rebuild.py exe     同上
    python rebuild.py fast    仅从源码快速启动 (开发测试用，秒级)
    python rebuild.py help    显示帮助

修改 smartring.py 后，双击此脚本即可自动：
  1. 关闭旧版 SmartRing
  2. 同步配置 (双向，不丢失任何设置)
  3. 重新构建 EXE 覆盖 dist\SmartRing.exe
  4. 启动新版
"""

import os
import sys
import subprocess
import shutil
import time

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_EXE = os.path.join(PROJECT_DIR, "dist", "SmartRing.exe")
PYW_PATH = os.path.join(PROJECT_DIR, "SmartRing.pyw")
CONFIG = os.path.join(PROJECT_DIR, "config.json")
DIST_CONFIG = os.path.join(PROJECT_DIR, "dist", "config.json")
ICON = os.path.join(PROJECT_DIR, "smartring.ico")
SPEC = os.path.join(PROJECT_DIR, "SmartRing.spec")
REQUIREMENTS = os.path.join(PROJECT_DIR, "requirements.txt")
GENERATE_ICON = os.path.join(PROJECT_DIR, "generate_icon.py")


# ============================================================================
# 进程管理
# ============================================================================

def kill_old():
    """关闭正在运行的 SmartRing 进程（以便覆盖 dist\SmartRing.exe）"""
    print("  [检查] 查找正在运行的 SmartRing...")
    found = False
    try:
        result = subprocess.run(
            ["tasklist", "/fi", "imagename eq SmartRing.exe", "/fo", "csv"],
            capture_output=True, text=True, timeout=10
        )
        if "SmartRing.exe" in result.stdout:
            print("         发现 SmartRing.exe，正在关闭...")
            subprocess.run(["taskkill", "/f", "/im", "SmartRing.exe"],
                           capture_output=True, timeout=10)
            found = True

        result = subprocess.run(
            ["tasklist", "/fi", "imagename eq pythonw.exe", "/fo", "csv", "/v"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if "smartring" in line.lower():
                pid = line.split(",")[1].strip('"')
                print(f"         发现 pythonw.exe (SmartRing) PID={pid}，正在关闭...")
                subprocess.run(["taskkill", "/f", "/pid", pid],
                               capture_output=True, timeout=10)
                found = True

        if found:
            time.sleep(0.5)

        if not found:
            print("         未发现运行中的 SmartRing")
    except Exception as e:
        print(f"         (检查进程时出错: {e})")
    print()


# ============================================================================
# 配置同步 — 双向，保证不丢失用户设置
# ============================================================================

def sync_config():
    """
    双向同步 config.json

    场景分析:
      - 用户在应用中修改了设置 → dist\config.json 比根目录的新 → 先同步回来
      - 用户手动编辑了根目录 config.json → 根目录的更新 → 覆盖 dist\
      - 两边都存在 → 保留最新的那个，同步到两边
      - 只存在一边 → 复制到另一边
      - 都不存在 → 首次运行，不做处理

    结果：两边始终一致，不会丢失设置。
    """
    print("  [同步] 检查 config.json...")

    root_exists = os.path.isfile(CONFIG)
    dist_exists = os.path.isfile(DIST_CONFIG)

    if not root_exists and not dist_exists:
        print("         两边都不存在 config.json，首次运行时会自动创建")
        return

    if root_exists and dist_exists:
        root_time = os.path.getmtime(CONFIG)
        dist_time = os.path.getmtime(DIST_CONFIG)
        if dist_time > root_time:
            # 用户在应用中修改了设置，同步回根目录
            shutil.copy2(DIST_CONFIG, CONFIG)
            print("         dist\\config.json (较新) → config.json (已同步回根目录)")
        else:
            # 根目录较新（用户手动编辑或之前同步过），覆盖 dist
            shutil.copy2(CONFIG, DIST_CONFIG)
            print("         config.json → dist\\config.json (已覆盖)")
    elif root_exists:
        # 只有根目录有，复制到 dist
        os.makedirs(os.path.dirname(DIST_CONFIG), exist_ok=True)
        shutil.copy2(CONFIG, DIST_CONFIG)
        print("         config.json → dist\\config.json (新创建)")
    elif dist_exists:
        # 只有 dist 有，复制到根目录
        shutil.copy2(DIST_CONFIG, CONFIG)
        print("         dist\\config.json → config.json (新创建)")

    print()


# ============================================================================
# Python 环境
# ============================================================================

def find_pythonw():
    """查找 pythonw.exe 的完整路径（用于后台无控制台启动）"""
    python_dir = os.path.dirname(sys.executable)
    candidates = [
        os.path.join(python_dir, "pythonw.exe"),
    ]

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    for ver in ["313", "312", "311", "310", "39", "38", "37"]:
        candidates.append(
            os.path.join(local_appdata, "Programs", "Python", f"Python{ver}", "pythonw.exe")
        )
        candidates.append(
            os.path.join(program_files, f"Python{ver}", "pythonw.exe")
        )

    for c in candidates:
        if os.path.isfile(c):
            return c

    result = shutil.which("pythonw")
    if result and "WindowsApps" not in result:
        return result

    return None


def python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


# ============================================================================
# 源码启动（快速模式）
# ============================================================================

def launch_source():
    """从源码启动 (快速模式，秒级)"""
    pythonw = find_pythonw()
    if not pythonw:
        print("  [失败] 找不到 pythonw.exe！")
        print("         请安装 Python 3.7+ https://python.org")
        print("         并勾选 'Add Python to PATH'")
        return False

    print(f"  [启动] {pythonw}")
    try:
        subprocess.Popen(
            [pythonw, PYW_PATH],
            cwd=PROJECT_DIR,
            creationflags=0x00000008,  # DETACHED_PROCESS
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("  [成功] SmartRing 已在后台启动！查看系统托盘图标。")
        return True
    except Exception as e:
        print(f"  [失败] 启动出错: {e}")
        return False


# ============================================================================
# 完整构建 + 替换 dist\
# ============================================================================

def clean_build_dir():
    """手动清理 PyInstaller 的 build 目录（避免 --clean 权限错误）"""
    build_dir = os.path.join(PROJECT_DIR, "build")
    if not os.path.isdir(build_dir):
        return

    max_retries = 3
    for attempt in range(max_retries):
        try:
            shutil.rmtree(build_dir)
            return
        except PermissionError:
            if attempt < max_retries - 1:
                print(f"         build 目录被占用，1秒后重试 ({attempt + 2}/{max_retries})...")
                time.sleep(1)
            else:
                print("         [警告] build 目录清理失败（文件被占用），将跳过清理继续构建")
                # 即使清理失败，PyInstaller 也能处理（只是可能有旧缓存）


def build_exe():
    """构建 EXE 并替换 dist\SmartRing.exe"""
    # 1. 环境检查
    print("  [1/6] 检查环境...")
    print(f"         Python {python_version()}  ({sys.executable})")
    print(f"         项目目录: {PROJECT_DIR}")

    try:
        import PyQt5
        print("         依赖 PyQt5: OK")
    except ImportError:
        print("         依赖缺失，正在安装...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS],
            cwd=PROJECT_DIR,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            cwd=PROJECT_DIR,
        )

    # 2. 图标检查
    print("  [2/6] 检查图标...")
    if not os.path.isfile(ICON):
        print("         生成 smartring.ico...")
        subprocess.run([sys.executable, GENERATE_ICON], cwd=PROJECT_DIR)
        if not os.path.isfile(ICON):
            print("         [警告] 图标生成失败")
    else:
        print("         smartring.ico OK")

    # 3. 同步配置（在构建前，保证 dist 中的配置是最新的）
    print("  [3/6] 同步配置...")
    sync_config()

    # 4. 清理旧 build 缓存（手动清理，避免 PyInstaller --clean 的权限错误）
    print("  [4/6] 清理旧的构建缓存...")
    clean_build_dir()

    # 5. PyInstaller 构建（不使用 --clean，已经手动清理过了）
    print("  [5/6] 构建 SmartRing.exe (2-5 分钟)...")
    print("  ─────────────────────────────────────────")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", SPEC, "--noconfirm"],
        cwd=PROJECT_DIR,
    )
    if result.returncode != 0:
        print()
        print("  ─────────────────────────────────────────")
        print("  [失败] PyInstaller 构建失败！")
        print("  请查看上方错误信息，常见原因：")
        print("    - 依赖缺失: pip install -r requirements.txt")
        print("    - 磁盘空间不足")
        print("    - 杀毒软件拦截")
        return False
    print("  ─────────────────────────────────────────")
    print()

    # 6. 构建后再次同步配置（确保 dist\ 中的 config 是最新的）
    print("  [6/6] 最终同步配置到 dist\\...")
    if os.path.isfile(CONFIG):
        os.makedirs(os.path.dirname(DIST_CONFIG), exist_ok=True)
        shutil.copy2(CONFIG, DIST_CONFIG)
        print("         config.json → dist\\config.json")
    print()

    return True


def launch_exe():
    """启动构建好的 EXE（使用 os.startfile，Windows 原生方式最可靠）"""
    if not os.path.isfile(DIST_EXE):
        print("  [失败] dist\\SmartRing.exe 未找到！")
        return False

    size_mb = os.path.getsize(DIST_EXE) / (1024 * 1024)
    print(f"  输出文件: dist\\SmartRing.exe ({size_mb:.1f} MB)")
    print()
    print("  正在启动 SmartRing...")
    try:
        os.startfile(DIST_EXE)
        print()
        print("  ============================================")
        print("    SmartRing 已启动！查看系统托盘图标。")
        print("    新版本已覆盖 dist\\SmartRing.exe")
        print("    配置文件已同步。")
        print("  ============================================")
        return True
    except OSError as e:
        print(f"  [失败] 启动 EXE 时出错: {e}")
        return False


# ============================================================================
# 帮助
# ============================================================================

def print_help():
    print("SmartRing — 一键覆盖 & 启动工具")
    print()
    print("用法:")
    print("  python rebuild.py         构建 EXE + 替换 dist\\ + 启动 (默认)")
    print("  python rebuild.py exe     同上")
    print("  python rebuild.py fast    仅从源码快速启动 (开发测试，秒级)")
    print()
    print("默认模式会做以下事情:")
    print("  1. 关闭正在运行的旧版 SmartRing")
    print("  2. 双向同步配置文件 (不丢失任何设置)")
    print("  3. 重新构建 EXE 并覆盖 dist\\SmartRing.exe")
    print("  4. 启动新版")
    print()
    print("快速开发流程:")
    print("  1. 修改 smartring.py")
    print("  2. python rebuild.py fast   ← 快速测试 (秒级)")
    print("  3. python rebuild.py        ← 最终覆盖 dist\\EXE")
    print()
    print(f"Python: {sys.executable}")
    print(f"项目:   {PROJECT_DIR}")


# ============================================================================
# 入口
# ============================================================================

def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "exe"

    print()
    print("  ============================================")
    print("    SmartRing - Rebuild and Launch")
    print("  ============================================")
    print()

    if mode in ("help", "--help", "-h"):
        print_help()
        print()
        print("  按 Enter 退出...", end="")
        input()
        return

    if mode == "fast":
        print("  模式: 快速测试 (源码运行)")
        print()
        kill_old()
        sync_config()
        launch_source()
    elif mode == "exe":
        print("  模式: 完整构建 + 覆盖 + 启动")
        print()
        kill_old()
        if build_exe():
            launch_exe()
    else:
        print(f"  未知参数: {mode}")
        print_help()

    print()
    print("  按 Enter 退出...", end="")
    input()
    print()


if __name__ == "__main__":
    main()
