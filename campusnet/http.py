"""极简 HTTP 会话：cookie 保持、可选忽略 TLS 校验、可选绕过系统代理。

校园网 portal 基本都是内网 IP + 自签证书，requests + 证书校验的组合
在这里只会给你添堵，所以直接用 urllib 手搓一个够用的会话。
"""
from __future__ import annotations

import gzip
import http.cookiejar
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping, Optional

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class Response:
    def __init__(self, status: int, url: str, headers: Mapping[str, str], body: bytes):
        self.status = status
        self.url = url
        self.headers = dict(headers)
        self.body = body

    @property
    def text(self) -> str:
        charset = "utf-8"
        ctype = self.headers.get("Content-Type", "")
        m = re.search(r"charset=([\w\-]+)", ctype, re.I)
        if m:
            charset = m.group(1)
        for enc in (charset, "utf-8", "gbk", "latin-1"):
            try:
                return self.body.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return self.body.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.text)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Response {self.status} {self.url} {len(self.body)}B>"


class HttpClient:
    def __init__(
        self,
        use_proxy: bool = False,
        proxies: Optional[Mapping[str, str]] = None,
        verify_tls: bool = False,
        timeout: float = 8.0,
        user_agent: str = DEFAULT_UA,
    ):
        self.timeout = timeout
        self.user_agent = user_agent
        self.cookies = http.cookiejar.CookieJar()

        handlers: list[Any] = [urllib.request.HTTPCookieProcessor(self.cookies)]

        if not verify_tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=ctx))

        if use_proxy:
            handlers.append(urllib.request.ProxyHandler(dict(proxies or {})))
        else:
            # 空 ProxyHandler 表示显式不走代理 —— 内网 portal 走代理必挂
            handlers.append(urllib.request.ProxyHandler({}))

        self.opener = urllib.request.build_opener(*handlers)

    # ------------------------------------------------------------------ 请求
    def request(
        self,
        method: str,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        data: Optional[Mapping[str, Any]] = None,
        body: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Response:
        if params:
            sep = "&" if urllib.parse.urlparse(url).query else "?"
            url = url + sep + urllib.parse.urlencode(params, doseq=True, safe="{}")

        payload: Optional[bytes] = None
        if body is not None:
            payload = body.encode("utf-8")
        elif data is not None:
            payload = urllib.parse.urlencode(data, doseq=True).encode("utf-8")

        req = urllib.request.Request(url, data=payload, method=method.upper())
        req.add_header("User-Agent", self.user_agent)
        req.add_header("Accept", "*/*")
        req.add_header("Accept-Encoding", "identity")
        req.add_header("Connection", "keep-alive")
        if payload is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
        for k, v in (headers or {}).items():
            req.add_header(k, v)

        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return Response(resp.status, resp.geturl(), resp.headers, raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read() or b""
            return Response(exc.code, url, exc.headers or {}, raw)

    def get(self, url: str, **kwargs: Any) -> Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Response:
        return self.request("POST", url, **kwargs)


def parse_jsonp(text: str) -> Any:
    """深澜 portal 返回的是 `callback({...})` 形式的 JSONP，剥壳。"""
    stripped = text.strip()
    if not stripped:
        raise ValueError("响应为空")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("(")
    end = stripped.rfind(")")
    if start == -1 or end <= start:
        # 有些部署直接返回 `&&&START&&&{...}`
        marker = stripped.find("&&&START&&&")
        if marker != -1:
            return json.loads(stripped[marker + len("&&&START&&&"):])
        raise ValueError(f"无法解析 JSONP 响应: {stripped[:200]}")

    inner = stripped[start + 1: end].strip()
    if inner in ("", "null"):
        return None
    return json.loads(inner)
