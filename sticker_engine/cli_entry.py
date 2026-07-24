"""PyInstaller 打包入口（包外，用绝对 import 避免 relative import 问题）。

cli.py 在包内用 `from . import`（包内相对 import），作为 PyInstaller 顶层脚本运行时
没有包上下文会报 ImportError。这个入口在包外，用绝对 import 调用包内 main()。
"""
from sticker_engine.cli import main

if __name__ == "__main__":
    main()
