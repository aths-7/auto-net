"""常驻守护：轮询联网状态，掉线就重新认证。

几点工程上的小讲究：
- 单实例锁用「绑定 127.0.0.1 固定端口」实现，比 pidfile 靠谱（进程崩了端口自动释放）
- 失败按指数退避，别拿 1 秒一次的频率去撞 portal，容易被拉黑
- 已经在线时什么都不做，避免把正常会话顶掉
"""
from __future__ import annotations

import socket
import time
from typing import Any, Dict, Optional

from . import config as config_mod
from . import logging_setup, netcheck
from .providers import get_provider

LOCK_PORT = 53417


class InstanceLock:
    def __init__(self, port: int = LOCK_PORT):
        self.port = port
        self.sock: Optional[socket.socket] = None

    def acquire(self) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:  # pragma: no cover
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", self.port))
            sock.listen(1)
        except OSError:
            sock.close()
            return False
        self.sock = sock
        return True

    def release(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None


def run(
    cfg: Dict[str, Any],
    interval: Optional[float] = None,
    once: bool = False,
    quiet: bool = False,
    max_rounds: Optional[int] = None,
) -> int:
    logger = logging_setup.setup(quiet=quiet)
    daemon_cfg = cfg.get("daemon", {})
    interval = float(interval if interval is not None else daemon_cfg.get("interval", 30))
    max_backoff = float(daemon_cfg.get("max_backoff", 300))
    startup_delay = float(daemon_cfg.get("startup_delay", 0))

    lock = InstanceLock()
    if not once and not lock.acquire():
        logger.warning("已有守护进程在运行，本次退出（单实例锁端口 %d）", LOCK_PORT)
        return 1

    provider_name = str(cfg.get("provider", "srun"))
    if startup_delay > 0:
        logger.info("启动延迟 %.0f 秒，等待网络就绪", startup_delay)
        time.sleep(startup_delay)

    backoff = interval
    rounds = 0
    try:
        while True:
            rounds += 1
            try:
                online, probes = netcheck.is_online(cfg)
                if online:
                    logger.debug("网络正常，跳过认证")
                    backoff = interval
                else:
                    reason = probes[0].detail if probes else "所有探测点失败"
                    logger.info("检测到离线（%s），尝试认证…", reason)
                    provider = get_provider(provider_name, cfg)
                    result = provider.login()
                    if result.ok:
                        logger.info("认证成功: %s", result.message)
                        backoff = interval
                    else:
                        backoff = min(max_backoff, max(interval, backoff * 2))
                        logger.warning("认证失败: %s（%d 秒后重试）", result.message, backoff)
            except Exception as exc:  # 守护进程不能因为单个异常就死掉
                backoff = min(max_backoff, max(interval, backoff * 2))
                logger.exception("本轮出现异常: %s（%d 秒后重试）", exc, backoff)

            if once or (max_rounds and rounds >= max_rounds):
                break
            time.sleep(backoff)
    except KeyboardInterrupt:
        logger.info("收到中断，守护进程退出")
    finally:
        lock.release()
    return 0


def login_once(cfg: Dict[str, Any], force: bool = False) -> int:
    logger = logging_setup.get()
    if not force:
        online, probes = netcheck.is_online(cfg)
        if online:
            logger.info("当前已在线（%s），无需认证。要强制重登请加 --force", probes[0].detail)
            return 0

    provider = get_provider(str(cfg.get("provider", "srun")), cfg)
    result = provider.login()
    if result.ok:
        logger.info("认证成功: %s", result.message)
        return 0
    logger.error("认证失败: %s", result.message)
    if result.raw:
        logger.debug("原始响应: %s", result.raw[:500])
    return 1
