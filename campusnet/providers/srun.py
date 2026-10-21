"""深澜（Srun / 哆点）portal 适配器。

走的是最通用的 V1 接口：
    GET  {portal}/cgi-bin/get_challenge
    GET  {portal}/cgi-bin/srun_portal   action=login
认证参数由 challenge token 派生：
    password = "{MD5}" + xencode(md5(pwd+token), token)
    info     = "{SRBX1}" + xencode(json(info), token)
    chksum   = sha1(token+user+token+hmd5+token+acid+token+ip+token+n+token+type+token+info+token)
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict

from ..crypto import hmac_md5, sha1, xencode
from ..http import parse_jsonp
from .base import BaseProvider, LoginResult


class SrunProvider(BaseProvider):
    name = "srun"
    display = "深澜 Srun"

    def _callback(self) -> str:
        return "jQuery%d_%d" % (int(time.time() * 1000), int(time.time()) % 100000)

    def login(self) -> LoginResult:
        cfg = self.cfg
        srun = cfg.get("srun", {})
        user = self.username
        pwd = self.password
        acid = str(srun.get("ac_id", "1"))
        n = str(srun.get("n", "200"))
        typ = str(srun.get("type", "1"))
        ts = str(int(time.time() * 1000))
        ip = self.client_ip()

        # 1) challenge
        cb = self._callback()
        try:
            resp = self.client.get(
                f"{self.portal}/cgi-bin/get_challenge",
                params={"callback": cb, "username": user, "ip": ip, "_": ts},
            )
            data = parse_jsonp(resp.text) or {}
        except Exception as exc:
            return LoginResult(False, f"获取 challenge 失败: {exc}", raw="")

        token = str(data.get("challenge", "") or "")
        if not token:
            return LoginResult(False, f"challenge 为空，portal 地址可能不对: {resp.text[:200]}", raw=resp.text)

        ip = str(data.get("client_ip") or ip)

        # 2) 派生认证参数
        hmd5 = hmac_md5(pwd, token)
        info_obj = {
            "username": user,
            "password": pwd,
            "ip": ip,
            "acid": acid,
            "enc_ver": "srun_bx1",
        }
        info_json = json.dumps(info_obj, separators=(",", ":"), ensure_ascii=False)
        info_enc = "{SRBX1}" + xencode(info_json, token)

        chk_src = "".join(
            [token, user, token, hmd5, token, acid, token, ip, token, n, token, typ, token, info_enc, token]
        )
        chksum = sha1(chk_src)

        params: Dict[str, Any] = {
            "callback": self._callback(),
            "action": "login",
            "username": user,
            "password": "{MD5}" + xencode(hmd5, token),
            "ac_id": acid,
            "ip": ip,
            "chksum": chksum,
            "info": info_enc,
            "n": n,
            "type": typ,
            "os": str(srun.get("os", "Windows")),
            "name": str(srun.get("name", "Windows")),
            "double_stack": str(srun.get("double_stack", "0")),
            "_": str(int(time.time() * 1000)),
        }

        try:
            resp = self.client.get(f"{self.portal}/cgi-bin/srun_portal", params=params)
            result = parse_jsonp(resp.text) or {}
        except Exception as exc:
            return LoginResult(False, f"提交认证失败: {exc}", raw="")

        return self._interpret(result, resp.text)

    @staticmethod
    def _interpret(result: Dict[str, Any], raw: str) -> LoginResult:
        error = str(result.get("error", "")).lower()
        suc_msg = str(result.get("suc_msg", ""))
        error_msg = str(result.get("error_msg", "") or result.get("res", "") or "")

        if error == "ok" or "login_ok" in suc_msg or result.get("res") == "ok":
            return LoginResult(True, suc_msg or "认证成功", raw=raw)
        # 已经在线也是好事，别当失败刷日志
        if "ip_already_online" in error or "already" in error_msg.lower():
            return LoginResult(True, "该 IP 已在线", raw=raw, already=True)
        if "logout" in suc_msg:
            return LoginResult(False, "portal 返回的结果像下线而非上线，检查 ac_id/账号", raw=raw)
        return LoginResult(False, error_msg or error or "未知失败", raw=raw)

    def logout(self) -> LoginResult:
        params = {
            "callback": self._callback(),
            "action": "logout",
            "username": self.username,
            "ip": self.client_ip(),
            "_": str(int(time.time() * 1000)),
        }
        try:
            resp = self.client.get(f"{self.portal}/cgi-bin/srun_portal", params=params)
            data = parse_jsonp(resp.text) or {}
        except Exception as exc:
            return LoginResult(False, f"下线失败: {exc}")
        ok = str(data.get("error", "")).lower() == "ok"
        return LoginResult(ok, data.get("error_msg") or ("已下线" if ok else "下线失败"), raw=resp.text)
