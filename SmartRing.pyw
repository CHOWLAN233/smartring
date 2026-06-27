"""
SmartRing — 无控制台启动器 (pythonw)

双击此文件即可在后台启动 SmartRing。
前提: Python 3 + 依赖已安装。

如果已构建了 EXE，请直接运行 dist\SmartRing.exe。
"""

import sys
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

if __name__ == "__main__":
    import smartring
    sys.exit(smartring.main())
