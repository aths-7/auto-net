"""跨平台自启动开关：Windows 注册表 / Linux systemd(user) / macOS LaunchAgent。

设计原则：不开管理员权限、不写系统目录、随时可一键关掉。
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import config as config_mod

WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_APP_NAME = os.environ.get("CAMPUSNET_AUTOSTART_NAME", "CampusNetAutoLogin")

LINUX_UNIT = """[Unit]
Description=Campus network auto login
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python} -m campusnet daemon --quiet
Environment=PYTHONPATH={pkg_parent}
Restart=always
RestartSec=15

[Install]
WantedBy=default.target
"""

MAC_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>-m</string>
    <string>campusnet</string>
    <string>daemon</string>
    <string>--quiet</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONPATH</key><string>{pkg_parent}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


# ---------------------------------------------------------------- 命令行拼装
def pkg_parent() -> str:
    """campusnet 包的父目录，用来在启动时补 sys.path。"""
    return str(Path(__file__).resolve().parent.parent)


def python_executable(hidden: bool = True) -> str:
    """Windows 上优先用 pythonw.exe，否则每次开机都会弹个黑窗口。"""
    exe = Path(sys.executable)
    if hidden and os.name == "nt":
        candidate = exe.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)


def command(hidden: bool = True) -> str:
    return f'"{python_executable(hidden)}" -m campusnet daemon --quiet'


def _launcher_script() -> Path:
    """生成一个自带 sys.path 修补的启动脚本，供注册表/计划任务调用。"""
    target = config_mod.app_dir() / "autostart_entry.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# 由 campusnet autostart 自动生成，请勿手改\n"
        "import sys\n"
        f"sys.path.insert(0, {pkg_parent()!r})\n"
        "from campusnet.cli import main\n"
        "sys.exit(main(['daemon', '--quiet']))\n"
    )
    target.write_text(body, encoding="utf-8")
    return target


# ------------------------------------------------------------------- Windows
def _win_status(name: str) -> Tuple[bool, str]:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return True, str(value)
    except FileNotFoundError:
        return False, "未设置"
    except OSError as exc:
        return False, f"读取注册表失败: {exc}"


def _win_enable(name: str, dry_run: bool) -> Tuple[bool, str]:
    import winreg

    entry = _launcher_script()
    value = f'"{python_executable(True)}" "{entry}"'
    if dry_run:
        return True, value
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    except OSError as exc:
        return False, f"写入注册表失败: {exc}"
    return True, value


def _win_disable(name: str) -> Tuple[bool, str]:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
        return True, "已移除自启动项"
    except FileNotFoundError:
        return True, "本来就没开"
    except OSError as exc:
        return False, f"删除失败: {exc}"


# --------------------------------------------------------------------- Linux
def _linux_paths() -> Tuple[Path, Path]:
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    xdg_dir = Path.home() / ".config" / "autostart"
    return unit_dir / "campusnet.service", xdg_dir / "campusnet.desktop"


def _linux_enable(name: str, dry_run: bool) -> Tuple[bool, str]:
    unit_path, xdg_path = _linux_paths()
    if dry_run:
        return True, str(unit_path)
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(
        LINUX_UNIT.format(
            python=python_executable(hidden=False),
            pkg_parent=pkg_parent(),
            log=config_mod.log_path(),
        ),
        encoding="utf-8",
    )

    if _has_systemd():
        for args in (["systemctl", "--user", "daemon-reload"],
                     ["systemctl", "--user", "enable", "--now", "campusnet.service"]):
            subprocess.run(args, capture_output=True, text=True, check=False)
        return True, f"systemd user unit: {unit_path}"

    # 没有 systemd 就退回 XDG autostart
    xdg_path.parent.mkdir(parents=True, exist_ok=True)
    xdg_path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Campus Network Auto Login\n"
        f"Exec={python_executable(hidden=False)} -m campusnet daemon --quiet\n"
        f"Path={pkg_parent()}\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
    return True, f"XDG autostart: {xdg_path}"


def _linux_disable(name: str) -> Tuple[bool, str]:
    unit_path, xdg_path = _linux_paths()
    removed = []
    if _has_systemd() and unit_path.exists():
        subprocess.run(["systemctl", "--user", "disable", "--now", "campusnet.service"],
                       capture_output=True, text=True, check=False)
    for path in (unit_path, xdg_path):
        if path.exists():
            try:
                path.unlink()
                removed.append(path.name)
            except OSError as exc:
                return False, f"删除 {path} 失败: {exc}"
    return True, ("已移除: " + ", ".join(removed)) if removed else "本来就没开"


def _has_systemd() -> bool:
    if not Path("/run/systemd/system").exists():
        return False
    from shutil import which

    return which("systemctl") is not None


# --------------------------------------------------------------------- macOS
def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.campusnet.autologin.plist"


def _mac_enable(name: str, dry_run: bool) -> Tuple[bool, str]:
    path = _mac_plist_path()
    if dry_run:
        return True, str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        MAC_PLIST.format(
            label="com.campusnet.autologin",
            python=python_executable(hidden=False),
            pkg_parent=pkg_parent(),
            log=config_mod.log_path(),
        ),
        encoding="utf-8",
    )
    subprocess.run(["launchctl", "unload", str(path)], capture_output=True, check=False)
    subprocess.run(["launchctl", "load", str(path)], capture_output=True, check=False)
    return True, f"LaunchAgent: {path}"


def _mac_disable(name: str) -> Tuple[bool, str]:
    path = _mac_plist_path()
    if path.exists():
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True, check=False)
        path.unlink()
        return True, f"已移除 {path.name}"
    return True, "本来就没开"


# ---------------------------------------------------------------------- 对外
def enable(name: str = DEFAULT_APP_NAME, dry_run: bool = False) -> Tuple[bool, str]:
    if os.name == "nt":
        return _win_enable(name, dry_run)
    if sys.platform == "darwin":
        return _mac_enable(name, dry_run)
    return _linux_enable(name, dry_run)


def disable(name: str = DEFAULT_APP_NAME) -> Tuple[bool, str]:
    if os.name == "nt":
        return _win_disable(name)
    if sys.platform == "darwin":
        return _mac_disable(name)
    return _linux_disable(name)


def is_enabled(name: str = DEFAULT_APP_NAME) -> Tuple[bool, str]:
    if os.name == "nt":
        return _win_status(name)
    if sys.platform == "darwin":
        path = _mac_plist_path()
        return (path.exists(), str(path) if path.exists() else "未设置")
    unit_path, xdg_path = _linux_paths()
    if unit_path.exists():
        enabled = True
        if _has_systemd():
            proc = subprocess.run(["systemctl", "--user", "is-enabled", "campusnet.service"],
                                  capture_output=True, text=True, check=False)
            enabled = proc.stdout.strip() in ("enabled", "enabled-runtime", "static")
        return enabled, str(unit_path)
    if xdg_path.exists():
        return True, str(xdg_path)
    return False, "未设置"


def summary() -> Dict[str, Any]:
    enabled, detail = is_enabled()
    return {
        "platform": config_mod.platform_name(),
        "enabled": enabled,
        "detail": detail,
        "command": command(),
    }
