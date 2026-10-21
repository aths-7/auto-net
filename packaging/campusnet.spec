# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：一次分析，产出两个 exe。

- campusnet.exe          控制台版，日常敲命令用
- campusnet-daemon.exe   无窗口版，开机自启动用它，不闪黑框
两个 exe 共用同一份 _internal 依赖，所以体积不会翻倍。
"""
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(Path(SPECPATH) / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "test", "distutils", "setuptools", "pip"],
    noarchive=False,
)

pyz = PYZ(a.pure)

console_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="campusnet",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

windowed_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="campusnet-daemon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 关键：无控制台窗口
)

coll = COLLECT(
    console_exe,
    windowed_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="auto-net",
)
