"""PyInstaller 打包入口。

源码运行时是 `python -m campusnet`，打包后同一个入口被编译成
`campusnet.exe`（控制台版）和 `campusnet-daemon.exe`（无窗口版）。
"""
import sys

from campusnet.cli import main

if __name__ == "__main__":
    sys.exit(main())
