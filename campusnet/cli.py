"""命令行入口：init / login / logout / status / daemon / autostart / doctor。"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from . import autostart as autostart_mod
from . import config as config_mod
from . import daemon, netcheck
from .providers import available, get_provider

PROVIDER_HINT = {
    "srun": "深澜 Srun（多数 985/211 在用，portal 常形如 http://10.x.x.x）",
    "eportal": "锐捷 ePortal（形如 https://10.x.x.x/eportal/）",
    "drcom": "Dr.COM 城市热点（宿舍宽带，客户端拨号式）",
    "custom": "自定义 URL 模板（上面都对不上就选这个）",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="campusnet",
        description="校园网自动登录 / 掉线重连 / 开机自启动",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "常用流程：\n"
            "  campusnet init                  # 交互式写配置\n"
            "  campusnet login                 # 认证一次\n"
            "  campusnet daemon                # 常驻守护（掉线自动重连）\n"
            "  campusnet autostart on          # 开机自启动\n"
        ),
    )
    parser.add_argument("-V", "--version", action="version", version=f"campusnet {__version__}")
    parser.add_argument("-c", "--config", help="配置文件路径（默认 ~/.campusnet/config.json）")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    parser.add_argument("--no-proxy", action="store_true", help="强制不走代理")

    sub = parser.add_subparsers(dest="command", metavar="<命令>")

    # ------------------------------------------------------------------ init
    p_init = sub.add_parser("init", help="创建/更新配置文件")
    p_init.add_argument("--provider", choices=available(), help="认证类型")
    p_init.add_argument("--portal", help="portal 根地址，如 http://10.0.0.55")
    p_init.add_argument("--username", help="账号")
    p_init.add_argument("--password", help="密码（不填则交互输入，建议用环境变量 CAMPUSNET_PASSWORD）")
    p_init.add_argument("--ac-id", help="深澜专用 ac_id")
    p_init.add_argument("--enable-autostart", action="store_true", help="保存后顺手开启自启动")
    p_init.add_argument("-y", "--yes", action="store_true", help="全部用默认值，不交互")

    # ----------------------------------------------------------------- login
    p_login = sub.add_parser("login", help="立即认证一次")
    p_login.add_argument("--force", action="store_true", help="已在线也重新认证")

    sub.add_parser("logout", help="主动下线")

    # ---------------------------------------------------------------- status
    sub.add_parser("status", help="查看联网状态 / 配置 / 自启动")

    # ---------------------------------------------------------------- daemon
    p_daemon = sub.add_parser("daemon", help="常驻守护，掉线自动重连")
    p_daemon.add_argument("--interval", type=float, help="检查间隔秒数（默认 30）")
    p_daemon.add_argument("--once", action="store_true", help="只跑一轮（调试用）")
    p_daemon.add_argument("--quiet", action="store_true", help="不输出到控制台（自启动时用）")
    p_daemon.add_argument("--max-rounds", type=int, help="跑 N 轮后退出（调试用）")

    # ------------------------------------------------------------- autostart
    p_auto = sub.add_parser("autostart", help="开机自启动开关")
    p_auto.add_argument("action", choices=["on", "off", "status"], help="on=开启 off=关闭 status=查看")
    p_auto.add_argument("--dry-run", action="store_true", help="只打印将要写入的内容")

    # ---------------------------------------------------------------- doctor
    sub.add_parser("doctor", help="诊断：探测网络、猜 portal 地址、检查配置")

    # ---------------------------------------------------------------- config
    p_cfg = sub.add_parser("config", help="打印或修改单项配置")
    p_cfg.add_argument("key", nargs="?", help="配置键，支持 a.b.c 形式")
    p_cfg.add_argument("value", nargs="?", help="要写入的值（缺省则只读取）")
    p_cfg.add_argument("--show-secret", action="store_true", help="显示未打码的密码")

    return parser


# --------------------------------------------------------------------- 工具
def load_cfg(args: argparse.Namespace) -> Dict[str, Any]:
    try:
        return config_mod.load(resolved_path(args))
    except FileNotFoundError as exc:
        raise SystemExit(f"{exc}")


def resolved_path(args: argparse.Namespace) -> Path:
    """真正生效的配置文件路径（--config > CAMPUSNET_CONFIG > ~/.campusnet/config.json）。"""
    return Path(args.config) if getattr(args, "config", None) else config_mod.config_path()


def _set_dotted(cfg: Dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    node = cfg
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise SystemExit(f"配置键 `{key}` 层级冲突")
    node[parts[-1]] = value


def _get_dotted(cfg: Dict[str, Any], key: str) -> Any:
    node: Any = cfg
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _print_kv(pairs: List[tuple], title: str = "") -> None:
    if title:
        print(f"\n{title}")
    width = max((len(str(k)) for k, _ in pairs), default=0)
    for key, value in pairs:
        print(f"  {str(key).ljust(width)} : {value}")


def _prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{text}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


# ------------------------------------------------------------------- 子命令
def cmd_init(args: argparse.Namespace) -> int:
    path = resolved_path(args)
    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except (OSError, json.JSONDecodeError):
            existing = {}

    cfg = config_mod.deep_merge(config_mod.DEFAULT_CONFIG, existing)
    interactive = not args.yes and sys.stdin.isatty()

    print("配置校园网自动登录" + ("（回车沿用中括号里的默认值）" if interactive else ""))
    for key, desc in PROVIDER_HINT.items():
        print(f"  - {key:<8} {desc}")

    provider = args.provider or (
        _prompt("认证类型", str(cfg.get("provider", "srun"))) if interactive else cfg.get("provider", "srun")
    )
    if provider not in available():
        raise SystemExit(f"未支持的认证类型: {provider}，可选: {', '.join(available())}")
    cfg["provider"] = provider

    portal = args.portal or (
        _prompt("portal 根地址", str(cfg.get("portal", ""))) if interactive else cfg.get("portal", "")
    )
    cfg["portal"] = portal.rstrip("/")

    cfg["username"] = args.username or (
        _prompt("账号", str(cfg.get("username", ""))) if interactive else cfg.get("username", "")
    )

    password = args.password
    if not password and interactive:
        typed = getpass.getpass("密码（不显示，直接回车则保留原值）: ")
        if typed:
            password = typed
    if password:
        cfg["password"] = password

    if args.ac_id:
        cfg.setdefault("srun", {})["ac_id"] = args.ac_id

    saved = config_mod.save(cfg, path)
    _print_kv(
        [
            ("配置文件", saved),
            ("认证类型", cfg["provider"]),
            ("portal", cfg["portal"] or "(未填)"),
            ("账号", cfg["username"] or "(未填)"),
            ("密码", config_mod.mask(str(cfg.get("password", "")))),
        ],
        "已保存",
    )

    if args.enable_autostart:
        ok, detail = autostart_mod.enable()
        print(f"\n自启动: {'已开启' if ok else '开启失败'} — {detail}")

    print("\n下一步：campusnet login  然后 campusnet autostart on")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    cfg = load_cfg(args)
    if args.no_proxy:
        cfg["use_proxy"] = False
    _validate(cfg)
    return daemon.login_once(cfg, force=args.force)


def cmd_logout(args: argparse.Namespace) -> int:
    cfg = load_cfg(args)
    _validate(cfg)
    result = get_provider(str(cfg["provider"]), cfg).logout()
    print(("✓ " if result.ok else "✗ ") + result.message)
    return 0 if result.ok else 1


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_cfg(args)
    online, probes = netcheck.is_online(cfg)
    auto_enabled, auto_detail = autostart_mod.is_enabled()

    _print_kv(
        [
            ("网络", "在线 ✓" if online else "离线 ✗"),
            ("认证类型", cfg.get("provider")),
            ("portal", cfg.get("portal")),
            ("账号", cfg.get("username")),
            ("密码", config_mod.mask(str(cfg.get("password", "")))),
            ("配置文件", resolved_path(args)),
            ("开机自启", f"{'已开启' if auto_enabled else '未开启'} — {auto_detail}"),
        ],
        "状态",
    )
    if not online:
        _print_kv([(p.url.split("//")[-1][:28], p.detail) for p in probes], "探测详情")
    return 0 if online else 1


def cmd_daemon(args: argparse.Namespace) -> int:
    cfg = load_cfg(args)
    if args.no_proxy:
        cfg["use_proxy"] = False
    _validate(cfg)
    return daemon.run(
        cfg,
        interval=args.interval,
        once=args.once,
        quiet=args.quiet,
        max_rounds=args.max_rounds,
    )


def cmd_autostart(args: argparse.Namespace) -> int:
    if args.action == "status":
        enabled, detail = autostart_mod.is_enabled()
        print(f"自启动: {'已开启' if enabled else '未开启'}")
        print(f"位置: {detail}")
        print(f"命令: {autostart_mod.command()}")
        return 0 if enabled else 1

    if args.action == "on":
        # 开启前先确认配置可用，避免开机跑一个必然失败的进程
        try:
            cfg = config_mod.load(resolved_path(args))
            _validate(cfg)
        except SystemExit as exc:
            print(f"配置不完整，先跑 campusnet init：{exc}")
            return 1
        ok, detail = autostart_mod.enable(dry_run=args.dry_run)
        print(("✓ 已开启自启动" if ok else "✗ 开启失败") + f" — {detail}")
        return 0 if ok else 1

    ok, detail = autostart_mod.disable()
    print(("✓ 已关闭自启动" if ok else "✗ 关闭失败") + f" — {detail}")
    return 0 if ok else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"campusnet {__version__}")
    _print_kv(
        [
            ("平台", config_mod.platform_name()),
            ("Python", sys.version.split()[0]),
            ("解释器", sys.executable),
            ("配置", resolved_path(args)),
            ("日志", config_mod.log_path()),
        ],
        "环境",
    )

    try:
        cfg = config_mod.load(resolved_path(args))
    except FileNotFoundError:
        # 诊断命令不该在「还没有配置」这种最常见的场景下崩掉
        print(f"\n配置文件不存在: {resolved_path(args)}（先跑 campusnet init）")
        cfg = config_mod.deep_merge(config_mod.DEFAULT_CONFIG, {})
    except SystemExit as exc:
        print(f"\n配置读取失败: {exc}")
        return 1

    online, probes = netcheck.is_online(cfg)
    _print_kv([(p.url.split("//")[-1][:30], ("OK " if p.ok else "FAIL ") + p.detail) for p in probes], "探测")
    print(f"\n网络: {'在线' if online else '离线'}")

    if not online:
        portal = netcheck.guess_portal(probes)
        if portal and portal != cfg.get("portal"):
            print(f"猜测 portal 地址: {portal}")
            print(f"  当前配置的是: {cfg.get('portal')}")
            print(f"  如果这个猜测更靠谱：campusnet config portal {portal}")

    problems = _validate(cfg, raise_error=False)
    if problems:
        _print_kv([(i + 1, msg) for i, msg in enumerate(problems)], "配置问题")
        return 1
    print("配置: 完整 ✓")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    cfg = load_cfg(args)
    if not args.key:
        shown = config_mod.deep_merge({}, cfg)
        shown = _redact(shown, show_secret=args.show_secret)
        print(json.dumps(shown, ensure_ascii=False, indent=2))
        return 0

    if args.value is None:
        value = _get_dotted(cfg, args.key)
        if value is None:
            print(f"配置项 `{args.key}` 不存在")
            return 1
        if args.key == "password" and not args.show_secret:
            print(config_mod.mask(str(value)))
        else:
            print(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value)
        return 0

    raw = args.value
    parsed: Any = raw
    for caster in (int, float):
        try:
            parsed = caster(raw)
            break
        except ValueError:
            continue
    if raw.lower() in ("true", "false"):
        parsed = raw.lower() == "true"

    _set_dotted(cfg, args.key, parsed)
    saved = config_mod.save(cfg, Path(args.config) if args.config else None)
    print(f"✓ {args.key} = {parsed}  已写入 {saved}")
    return 0


# ------------------------------------------------------------------- 校验器
def _redact(obj: Any, show_secret: bool = False) -> Any:
    if isinstance(obj, dict):
        return {
            k: (config_mod.mask(str(v)) if k == "password" and not show_secret else _redact(v, show_secret))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(item, show_secret) for item in obj]
    return obj


def _validate(cfg: Dict[str, Any], raise_error: bool = True) -> List[str]:
    problems: List[str] = []
    if not cfg.get("portal"):
        problems.append("portal 未填写（校园网登录页的内网地址）")
    if not cfg.get("username"):
        problems.append("username 未填写")
    if not cfg.get("password"):
        problems.append("password 未填写，可设置环境变量 CAMPUSNET_PASSWORD 代替")
    provider = str(cfg.get("provider", ""))
    if provider not in available():
        problems.append(f"provider `{provider}` 不受支持，可选 {', '.join(available())}")
    if provider == "custom" and not cfg.get("custom", {}).get("login_url"):
        problems.append("custom.login_url 未填写")

    if problems and raise_error:
        raise SystemExit("配置不完整：\n" + "\n".join(f"  - {p}" for p in problems) + "\n跑 `campusnet init` 补全。")
    return problems


def _harden_console() -> None:
    """把标准输出/错误切到 UTF-8。

    英文版 Windows 的控制台默认是 cp1252，直接 print 中文会抛
    UnicodeEncodeError —— 一个中文工具在中文 Windows 上没事，在英文
    Windows 上崩，属于必须兜住的边界。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # 被重定向成 StringIO 之类
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError, AttributeError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _harden_console()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    handlers = {
        "init": cmd_init,
        "login": cmd_login,
        "logout": cmd_logout,
        "status": cmd_status,
        "daemon": cmd_daemon,
        "autostart": cmd_autostart,
        "doctor": cmd_doctor,
        "config": cmd_config,
    }

    if args.verbose:
        import logging

        logging.getLogger("campusnet").setLevel(logging.DEBUG)

    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        print("\n已中断")
        return 130
