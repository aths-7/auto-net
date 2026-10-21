"""Dr.COM（城市热点 / 哆点客户端体系）适配器。

实现的是宿舍宽带最常见的“0MKKey”表单提交变体：
    POST {portal}/  DDDDD=<账号>&upass=<密码>&0MKKey=123456...
成功页返回里带 Dr.COMWebLoginID_3 标记。
"""
from __future__ import annotations

from typing import Any, Dict

from .base import BaseProvider, LoginResult


class DrcomProvider(BaseProvider):
    name = "drcom"
    display = "Dr.COM"

    def _payload(self) -> Dict[str, str]:
        dr = self.cfg.get("drcom", {})
        return {
            "DDDDD": self.username,
            "upass": self.password,
            "0MKKey": str(dr.get("key", "123456")),
            "R1": "0",
            "R2": "",
            "R3": "0",
            "R6": "0",
            "para": "00",
            "v6ip": "",
            "terminal_type": "1",
            "lang": "zh-cn",
            "jsVersion": "4.1.3",
            "v": "4031",
            "bb": "",
            "bbb": "",
            "ll": "",
        }

    def login(self) -> LoginResult:
        marker = str(self.cfg.get("drcom", {}).get("success_marker", "Dr.COMWebLoginID_3"))
        try:
            resp = self.client.post(self.portal + "/", data=self._payload())
        except Exception as exc:
            return LoginResult(False, f"提交认证失败: {exc}")

        text = resp.text or ""
        if marker in text:
            return LoginResult(True, "认证成功", raw=text)
        if "Dr.COMWebLoginID_2" in text:
            return LoginResult(False, "账号或密码错误（Dr.COM 错误页 2）", raw=text)
        if "注销" in text and "网络已连接" in text:
            return LoginResult(True, "已在线", raw=text, already=True)
        # 有些版本成功页不含标记，退化成看有没有登录表单
        if "DDDDD" not in text and "upass" not in text:
            return LoginResult(True, "portal 未返回登录表单，按成功处理", raw=text)
        return LoginResult(False, "认证失败，portal 仍返回登录表单", raw=text)

    def logout(self) -> LoginResult:
        try:
            resp = self.client.get(self.portal + "/")
        except Exception as exc:
            return LoginResult(False, f"下线失败: {exc}")
        ok = "DDDDD" in resp.text  # 又看到登录表单 == 已经掉线
        return LoginResult(ok, "已下线" if ok else "下线失败", raw=resp.text)
