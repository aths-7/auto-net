"""联网状态检测。

思路：挑几个 captive-portal 探测地址（generate_204 之类），
- 返回预期的 204/200 且内容符合 => 在线
- 被 302 到别处、或者内容被替换 => 离线（顺便还能把 portal 地址捞出来）
"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from .http import HttpClient


class ProbeResult:
    def __init__(self, url: str, ok: bool, detail: str, redirect: Optional[str] = None):
        self.url = url
        self.ok = ok
        self.detail = detail
        self.redirect = redirect

    def __repr__(self) -> str:
        return f"<Probe {self.url} ok={self.ok} {self.detail}>"


def _looks_like_portal(resp, expect: int, contains: Optional[str]) -> bool:
    if resp.status == expect:
        if contains and contains not in resp.text:
            return False
        return True
    return False


def probe_one(client: HttpClient, item: Dict[str, Any], timeout: float = 5.0) -> ProbeResult:
    url = item["url"]
    expect = int(item.get("expect", 204))
    contains = item.get("contains")
    try:
        resp = client.get(url, timeout=timeout)
    except Exception as exc:  # 网络不可达 / DNS 挂了
        return ProbeResult(url, False, f"请求失败: {type(exc).__name__}: {exc}")

    final_url = resp.url or url
    host_changed = urllib.parse.urlparse(final_url).netloc != urllib.parse.urlparse(url).netloc

    if _looks_like_portal(resp, expect, contains):
        return ProbeResult(url, True, f"HTTP {resp.status}")

    if resp.status in (301, 302, 303, 307, 308) or host_changed:
        return ProbeResult(url, False, f"被重定向 (HTTP {resp.status})", final_url)

    if resp.status == 200 and expect == 204:
        # 门户把 204 顶替成 200 的登录页 —— 典型未认证特征
        return ProbeResult(url, False, "返回 200 而非 204，疑似被 portal 劫持", final_url)

    return ProbeResult(url, False, f"HTTP {resp.status}，不符合预期 {expect}")


def is_online(cfg: Dict[str, Any], client: Optional[HttpClient] = None) -> Tuple[bool, List[ProbeResult]]:
    check = cfg.get("check", {})
    items = check.get("urls") or []
    timeout = float(check.get("timeout", 5))
    own_client = client is None
    if own_client:
        client = HttpClient(
            use_proxy=bool(cfg.get("use_proxy")),
            proxies=cfg.get("proxies") or {},
            verify_tls=bool(cfg.get("verify_tls")),
            timeout=timeout,
        )

    results = [probe_one(client, item, timeout) for item in items]
    # 只要有一个探测点正常，就认为在线（避免某个探测域名本身被墙的误判）
    online = any(r.ok for r in results)
    return online, results


def guess_portal(results: List[ProbeResult]) -> Optional[str]:
    """从重定向结果里猜 portal 根地址，给 `campusnet doctor` 用。"""
    for r in results:
        if r.redirect:
            parsed = urllib.parse.urlparse(r.redirect)
            if parsed.netloc:
                return f"{parsed.scheme or 'http'}://{parsed.netloc}"
    return None
