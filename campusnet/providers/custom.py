"""自定义适配器 —— 兜底方案。

不认识的 portal 就填个 URL 模板，占位符：
    {portal} {username} {password} {client_ip} {username_q} {password_q}
其中 *_q 版本已经做过 URL 编码，方便塞进 body 或 query。
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict

from .base import BaseProvider, LoginResult


class CustomProvider(BaseProvider):
    name = "custom"
    display = "自定义模板"

    def _render(self, template: str) -> str:
        values = {
            "portal": self.portal,
            "username": self.username,
            "password": self.password,
            "client_ip": self.client_ip(),
            "username_q": urllib.parse.quote(self.username, safe=""),
            "password_q": urllib.parse.quote(self.password, safe=""),
        }
        out = template
        for key, value in values.items():
            out = out.replace("{" + key + "}", value)
        return out

    def login(self) -> LoginResult:
        conf: Dict[str, Any] = self.cfg.get("custom", {})
        url_tpl = str(conf.get("login_url") or "")
        if not url_tpl:
            return LoginResult(False, "custom.login_url 未配置")

        url = self._render(url_tpl)
        method = str(conf.get("method", "POST")).upper()
        body = self._render(str(conf.get("body") or ""))
        headers = {str(k): str(v) for k, v in (conf.get("headers") or {}).items()}

        try:
            if method == "GET":
                resp = self.client.get(url, headers=headers)
            else:
                resp = self.client.post(url, body=body, headers=headers)
        except Exception as exc:
            return LoginResult(False, f"请求失败: {exc}")

        pattern = str(conf.get("success_regex") or "")
        if pattern:
            if re.search(pattern, resp.text):
                return LoginResult(True, "命中成功匹配规则", raw=resp.text)
            return LoginResult(False, f"未命中成功规则 /{pattern}/", raw=resp.text)

        # 没给规则就只能看 HTTP 状态
        if 200 <= resp.status < 400:
            return LoginResult(True, f"HTTP {resp.status}（未配置 success_regex，按成功处理）", raw=resp.text)
        return LoginResult(False, f"HTTP {resp.status}", raw=resp.text)
