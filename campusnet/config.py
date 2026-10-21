"""配置读写。单个 JSON 文件，路径 ~/.campusnet/config.json。"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

APP_DIR_NAME = ".campusnet"
CONFIG_NAME = "config.json"
LOG_NAME = "campusnet.log"

# 检测“有没有真正联上网”的探测地址。
# generate_204 系列最可靠：未登录时会被 portal 劫持成 302，登录后返回空 204。
DEFAULT_CHECK_URLS = [
    {"url": "http://connect.rom.miui.com/generate_204", "expect": 204},
    {"url": "http://www.gstatic.com/generate_204", "expect": 204},
    {"url": "http://captive.apple.com/hotspot-detect.html", "expect": 200, "contains": "Success"},
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "provider": "srun",
    "username": "",
    "password": "",
    "portal": "http://10.0.0.55",
    "client_ip": "",
    "use_proxy": False,
    "proxies": {},
    "verify_tls": False,
    "timeout": 8,
    "check": {
        "urls": DEFAULT_CHECK_URLS,
        "timeout": 5,
    },
    "daemon": {
        "interval": 30,
        "max_backoff": 300,
        "startup_delay": 0,
        "retry_on_fail": True,
    },
    "srun": {
        "ac_id": "1",
        "n": "200",
        "type": "1",
        "os": "Windows",
        "name": "Windows",
        "double_stack": "0",
    },
    "eportal": {
        "encrypt": "plain",
        "rc4_key": "",
        "query_string": "",
        "service": "",
        "valid_code": "",
    },
    "drcom": {
        "key": "123456",
        "success_marker": "Dr.COMWebLoginID_3",
    },
    "custom": {
        "login_url": "",
        "method": "POST",
        "body": "",
        "success_regex": "",
        "headers": {},
    },
}

ENV_CONFIG = "CAMPUSNET_CONFIG"
ENV_PASSWORD = "CAMPUSNET_PASSWORD"


def app_dir() -> Path:
    override = os.environ.get("CAMPUSNET_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / APP_DIR_NAME


def config_path() -> Path:
    override = os.environ.get(ENV_CONFIG)
    if override:
        return Path(override).expanduser()
    return app_dir() / CONFIG_NAME


def log_path() -> Path:
    return app_dir() / LOG_NAME


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """把用户配置叠到默认值上，缺失的键用默认值兜底。"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load(path: Optional[Path] = None) -> Dict[str, Any]:
    target = Path(path) if path else config_path()
    if not target.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {target}\n先跑一次 `campusnet init` 生成配置。"
        )
    with target.open("r", encoding="utf-8") as fh:
        user_cfg = json.load(fh)
    cfg = deep_merge(DEFAULT_CONFIG, user_cfg)

    # 环境变量优先级最高，方便把密码从配置文件里挪出去
    env_pwd = os.environ.get(ENV_PASSWORD)
    if env_pwd:
        cfg["password"] = env_pwd
    return cfg


def save(cfg: Dict[str, Any], path: Optional[Path] = None) -> Path:
    target = Path(path) if path else config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    merged = deep_merge(DEFAULT_CONFIG, cfg)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    try:  # 权限收紧，别把明文密码敞着给人看
        os.chmod(target, 0o600)
    except OSError:  # pragma: no cover - Windows 上语义有限
        pass
    return target


def mask(secret: str) -> str:
    if not secret:
        return "(未设置)"
    if len(secret) <= 2:
        return "*" * len(secret)
    return secret[0] + "*" * (len(secret) - 2) + secret[-1]


def require(cfg: Dict[str, Any], key: str, hint: str = "") -> Any:
    value = cfg.get(key)
    if value in ("", None, [], {}):
        msg = f"配置项 `{key}` 未填写"
        if hint:
            msg += f"（{hint}）"
        raise SystemExit(msg)
    return value


def platform_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"
