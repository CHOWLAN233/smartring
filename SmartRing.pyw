"""
SmartRing — 无控制台启动器

双击此文件即可在后台启动 SmartRing（不显示命令行窗口）。
程序启动后出现在系统托盘中。

要求: Python 3 已安装，依赖已安装 (pip install -r requirements.txt)
"""

import sys
import os

# Ensure the script directory is on the path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Run the main application
if __name__ == "__main__":
    import smartring
    sys.exit(smartring.main())
