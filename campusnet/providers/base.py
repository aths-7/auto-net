"""Provider 基类与统一返回结构。"""
from __future__ import annotations

import socket
import urllib.parse
from typing import Any, Dict, Optional

from ..http import HttpClient


class LoginResult:
    def __init__(self, ok: bool, message: str, raw: str = "", already: bool = False):
        self.ok = ok
        self.message = message
        self.raw = raw
        self.already = already  # 本来就在线 / 已认证

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return f"<LoginResult ok={self.ok} {self.message!r}>"


class BaseProvider:
    name = "base"
    display = "基础适配器"

    def __init__(self, cfg: Dict[str, Any], client: Optional[HttpClient] = None):
        self.cfg = cfg
        self.client = client or HttpClient(
            use_proxy=bool(cfg.get("use_proxy")),
            proxies=cfg.get("proxies") or {},
            verify_tls=bool(cfg.get("verify_tls")),
            timeout=float(cfg.get("timeout", 8)),
        )

    # ---------------------------------------------------------------- 工具方法
    @property
    def portal(self) -> str:
        return str(self.cfg.get("portal", "")).rstrip("/")

    @property
    def username(self) -> str:
        return str(self.cfg.get("username", ""))

    @property
    def password(self) -> str:
        return str(self.cfg.get("password", ""))

    def local_ip_for_portal(self) -> str:
        """拿到本机出去访问 portal 时用的源 IP（portal 认证需要它）。

        用 UDP socket 连一下 portal 的 host，不真发包，只为让内核选出路由。
        """
        host = urllib.parse.urlparse(self.portal).hostname or "10.0.0.1"
        try:
            port = urllib.parse.urlparse(self.portal).port or 80
        except ValueError:
            port = 80
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((host, port))
            return sock.getsockname()[0]
        except OSError:
            return ""
        finally:
            sock.close()

    def client_ip(self) -> str:
        return str(self.cfg.get("client_ip") or self.local_ip_for_portal())

    # ------------------------------------------------------------------- 接口
    def login(self) -> LoginResult:
        raise NotImplementedError

    def logout(self) -> LoginResult:
        raise NotImplementedError(f"{self.display} 暂不支持主动下线")
