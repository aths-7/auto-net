"""锐捷 ePortal 适配器。

流程：
    GET  {portal}/eportal/                      取 queryString（或从配置/重定向 URL 拿）
    POST {portal}/eportal/InterFace.do?method=pageInfo    body: queryString=...
    POST {portal}/eportal/InterFace.do?method=login
部分学校开了 passwordEncrypt=true，密码要用页面 JS 里的 key 走 RC4+base64。
key 可以手填 rc4_key，也可以让本适配器从 portal 首页的 JS 里自动抠。
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, Optional

from ..crypto import eportal_encrypt
from .base import BaseProvider, LoginResult

_KEY_PATTERNS = [
    r"key\s*=\s*['\"]([A-Za-z0-9+/=]{16,})['\"]",
    r"mk\s*=\s*['\"]([A-Za-z0-9+/=]{16,})['\"]",
    r"rc4\s*\(\s*['\"]([A-Za-z0-9+/=]{16,})['\"]",
]


class EportalProvider(BaseProvider):
    name = "eportal"
    display = "锐捷 ePortal"

    # ------------------------------------------------------------------ 工具
    def _query_string(self) -> str:
        conf_qs = str(self.cfg.get("eportal", {}).get("query_string") or "")
        if conf_qs:
            return conf_qs.lstrip("?")

        # 试着从 portal 首页/重定向里捞 queryString
        try:
            resp = self.client.get(f"{self.portal}/eportal/")
        except Exception:
            return ""
        if resp.url and "?" in resp.url:
            return urllib.parse.urlparse(resp.url).query
        m = re.search(r"(?:queryString|qs)\s*[:=]\s*['\"]([^'\"]+)['\"]", resp.text)
        if m:
            return m.group(1).lstrip("?")
        m = re.search(r"wlanuserip=([^&\"']+)", resp.text)
        if m:
            return "wlanuserip=" + m.group(1)
        return ""

    def _rc4_key(self) -> Optional[str]:
        conf_key = str(self.cfg.get("eportal", {}).get("rc4_key") or "")
        if conf_key:
            return conf_key
        try:
            resp = self.client.get(f"{self.portal}/eportal/")
        except Exception:
            return None
        for pattern in _KEY_PATTERNS:
            m = re.search(pattern, resp.text)
            if m:
                return m.group(1)
        return None

    # ------------------------------------------------------------------ 认证
    def login(self) -> LoginResult:
        ep = self.cfg.get("eportal", {})
        qs = self._query_string()
        service = str(ep.get("service") or "")
        encrypt = str(ep.get("encrypt", "plain")).lower()

        password = self.password
        password_encrypt = "false"
        if encrypt in ("rc4", "true", "1"):
            key = self._rc4_key()
            if not key:
                return LoginResult(False, "配置了 rc4 加密但找不到 key，请在 eportal.rc4_key 里手填")
            password = eportal_encrypt(self.password, key)
            password_encrypt = "true"

        # pageInfo 拿一下 service / 校验服务端会话
        page_info: Dict[str, Any] = {}
        try:
            resp = self.client.post(
                f"{self.portal}/eportal/InterFace.do?method=pageInfo",
                data={"queryString": qs},
                headers={"Referer": f"{self.portal}/eportal/"},
            )
            page_info = resp.json()
        except Exception:
            page_info = {}

        if not service:
            service = str(page_info.get("service") or page_info.get("serviceName") or "")

        payload = {
            "userId": self.username,
            "password": password,
            "service": service,
            "queryString": qs,
            "operatorPwd": "",
            "operatorUserId": "",
            "validcode": str(ep.get("valid_code") or ""),
            "passwordEncrypt": password_encrypt,
        }

        try:
            resp = self.client.post(
                f"{self.portal}/eportal/InterFace.do?method=login",
                data=payload,
                headers={
                    "Referer": f"{self.portal}/eportal/",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        except Exception as exc:
            return LoginResult(False, f"提交认证失败: {exc}")

        return self._interpret(resp.text)

    @staticmethod
    def _interpret(raw: str) -> LoginResult:
        text = (raw or "").strip()
        if not text:
            return LoginResult(False, "portal 返回空响应")

        result = ""
        message = ""
        if text.startswith("{"):
            import json

            try:
                data = json.loads(text)
                result = str(data.get("result", ""))
                message = str(data.get("message", "") or data.get("msg", ""))
            except json.JSONDecodeError:
                pass

        blob = (result + " " + message + " " + text).lower()
        if result.lower() == "success" or "认证成功" in text or "login success" in blob:
            return LoginResult(True, message or "认证成功", raw=raw)
        if "已在线" in text or "already" in blob:
            return LoginResult(True, message or "该账号已在线", raw=raw, already=True)
        if "流控" in text or "flow" in blob:
            return LoginResult(False, message or "流量超限（流控）", raw=raw)
        return LoginResult(False, message or (result or text[:200]), raw=raw)

    def logout(self) -> LoginResult:
        qs = self._query_string()
        try:
            resp = self.client.post(
                f"{self.portal}/eportal/InterFace.do?method=logout",
                data={"queryString": qs},
            )
        except Exception as exc:
            return LoginResult(False, f"下线失败: {exc}")
        ok = "success" in resp.text.lower()
        return LoginResult(ok, "已下线" if ok else "下线失败", raw=resp.text)
