"""测试用的假 portal 服务器：在本机回放深澜/锐捷/Dr.COM 的接口。"""
from __future__ import annotations

import hashlib
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple

Handler = Callable[["PortalHandler"], None]


class PortalHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MockPortal/1.0"

    routes: Dict[str, Handler] = {}
    requests: list = []

    # -------------------------------------------------------------- 基础工具
    def log_message(self, *args: Any) -> None:  # 静音
        pass

    def _send(self, status: int, body: str = "", ctype: str = "text/html; charset=UTF-8",
              headers: Optional[Dict[str, str]] = None) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    @property
    def query(self) -> Dict[str, str]:
        parsed = urllib.parse.urlparse(self.path)
        return {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

    @property
    def form(self) -> Dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}

    def _dispatch(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        PortalHandler.requests.append(
            {"method": self.command, "path": parsed.path, "query": self.query}
        )
        handler = PortalHandler.routes.get(parsed.path)
        if handler is None:
            self._send(404, "not found")
            return
        handler(self)

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()


class MockPortal:
    def __init__(self) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), PortalHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def route(self, path: str, handler: Handler) -> None:
        PortalHandler.routes[path] = handler

    def reset(self) -> None:
        PortalHandler.routes.clear()
        PortalHandler.requests.clear()

    def __enter__(self) -> "MockPortal":
        self.thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.reset()


# ------------------------------------------------------------------ 复用工具
def jsonp(callback: str, payload: Dict[str, Any]) -> str:
    return f"{callback}({json.dumps(payload, ensure_ascii=False)})"


def srun_chksum(token: str, user: str, hmd5: str, acid: str, ip: str,
                n: str, typ: str, info: str) -> str:
    """独立实现一遍深澜的 chksum，别复用被测代码。"""
    source = "".join([token, user, token, hmd5, token, acid, token, ip,
                      token, n, token, typ, token, info, token])
    return hashlib.sha1(source.encode("utf-8")).hexdigest()


def success_tuple() -> Tuple[bool, bool]:
    return True, True
