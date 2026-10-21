"""各适配器的端到端测试（对着本机假 portal 跑）。"""
from __future__ import annotations

import json
import unittest

from campusnet.crypto import xdecode
from campusnet.providers import DrcomProvider, EportalProvider, SrunProvider, CustomProvider
from tests.mock_portal import MockPortal, jsonp, srun_chksum

TOKEN = "testtoken"


def srun_cfg(base: str, password: str = "pass123") -> dict:
    return {
        "provider": "srun",
        "portal": base,
        "username": "20230001",
        "password": password,
        "client_ip": "127.0.0.1",
        "verify_tls": False,
        "timeout": 5,
        "srun": {"ac_id": "1", "n": "200", "type": "1", "os": "Windows",
                 "name": "Windows", "double_stack": "0"},
    }


class TestSrunProvider(unittest.TestCase):
    def _install(self, portal: MockPortal, seen: dict) -> None:
        def challenge(h) -> None:
            seen["challenge_query"] = h.query
            h._send(200, jsonp(h.query["callback"], {
                "challenge": TOKEN, "client_ip": "127.0.0.1", "res": "ok", "error": "ok",
            }), ctype="text/javascript")

        def login(h) -> None:
            q = h.query
            seen["login_query"] = q
            info_raw = q.get("info", "")
            seen["info"] = json.loads(xdecode(info_raw[len("{SRBX1}"):], TOKEN)) if info_raw.startswith("{SRBX1}") else None
            seen["chksum_expected"] = srun_chksum(
                TOKEN, q["username"],
                __import__("hashlib").md5(("pass123" + TOKEN).encode()).hexdigest(),
                q["ac_id"], q["ip"], q["n"], q["type"], info_raw,
            )
            h._send(200, jsonp(q["callback"], {
                "error": "ok", "res": "ok", "suc_msg": "login_ok", "uid": 12345,
            }), ctype="text/javascript")

        portal.route("/cgi-bin/get_challenge", challenge)
        portal.route("/cgi-bin/srun_portal", login)

    def test_login_success(self) -> None:
        seen: dict = {}
        with MockPortal() as portal:
            self._install(portal, seen)
            result = SrunProvider(srun_cfg(portal.base)).login()

        self.assertTrue(result.ok, result.message)
        q = seen["login_query"]
        self.assertEqual(q["action"], "login")
        self.assertEqual(q["username"], "20230001")
        self.assertTrue(q["password"].startswith("{MD5}"))
        self.assertTrue(q["info"].startswith("{SRBX1}"))
        self.assertEqual(q["ac_id"], "1")
        self.assertEqual(q["chksum"], seen["chksum_expected"])
        self.assertEqual(seen["info"]["username"], "20230001")
        self.assertEqual(seen["info"]["enc_ver"], "srun_bx1")
        self.assertEqual(seen["info"]["acid"], "1")

    def test_wrong_password(self) -> None:
        with MockPortal() as portal:
            portal.route("/cgi-bin/get_challenge", lambda h: h._send(
                200, jsonp(h.query["callback"], {"challenge": TOKEN, "client_ip": "127.0.0.1"}),
                ctype="text/javascript"))
            portal.route("/cgi-bin/srun_portal", lambda h: h._send(
                200, jsonp(h.query["callback"], {"error": "password_error", "error_msg": "E2553: 密码错误"}),
                ctype="text/javascript"))
            result = SrunProvider(srun_cfg(portal.base, "wrong")).login()

        self.assertFalse(result.ok)
        self.assertIn("密码错误", result.message)

    def test_already_online_is_success(self) -> None:
        with MockPortal() as portal:
            portal.route("/cgi-bin/get_challenge", lambda h: h._send(
                200, jsonp(h.query["callback"], {"challenge": TOKEN, "client_ip": "127.0.0.1"}),
                ctype="text/javascript"))
            portal.route("/cgi-bin/srun_portal", lambda h: h._send(
                200, jsonp(h.query["callback"], {"error": "ip_already_online_error", "error_msg": "already online"}),
                ctype="text/javascript"))
            result = SrunProvider(srun_cfg(portal.base)).login()

        self.assertTrue(result.ok)
        self.assertTrue(result.already)

    def test_missing_challenge(self) -> None:
        with MockPortal() as portal:
            portal.route("/cgi-bin/get_challenge", lambda h: h._send(404, "nope"))
            result = SrunProvider(srun_cfg(portal.base)).login()
        self.assertFalse(result.ok)
        self.assertIn("challenge", result.message)


class TestEportalProvider(unittest.TestCase):
    def test_login_success(self) -> None:
        seen: dict = {}
        with MockPortal() as portal:
            def eportal_root(h) -> None:
                h._send(200, "<html><script>var queryString='wlanuserip=10.0.0.7&mac=aa'</script></html>")

            def interface(h) -> None:
                method = h.query.get("method")
                form = h.form
                seen[method] = form
                if method == "pageInfo":
                    h._send(200, json.dumps({"result": "success", "service": "internet"}),
                            ctype="application/json")
                elif method == "login":
                    h._send(200, json.dumps({"result": "success", "message": "认证成功"}),
                            ctype="application/json")
                else:
                    h._send(200, json.dumps({"result": "fail", "message": "unknown"}))

            portal.route("/eportal/", eportal_root)
            portal.route("/eportal/InterFace.do", interface)

            cfg = {
                "provider": "eportal", "portal": portal.base,
                "username": "stu001", "password": "pwd", "verify_tls": False, "timeout": 5,
                "eportal": {"encrypt": "plain"},
            }
            result = EportalProvider(cfg).login()

        self.assertTrue(result.ok, result.message)
        self.assertEqual(seen["login"]["userId"], "stu001")
        self.assertEqual(seen["login"]["password"], "pwd")
        self.assertEqual(seen["login"]["passwordEncrypt"], "false")
        self.assertIn("wlanuserip", seen["login"]["queryString"])

    def test_rc4_encrypt_mode(self) -> None:
        from campusnet.crypto import rc4
        import base64

        seen: dict = {}
        with MockPortal() as portal:
            portal.route("/eportal/", lambda h: h._send(
                200, "<script>var key = '0123456789abcdef';</script>"))

            def interface(h) -> None:
                if h.query.get("method") == "login":
                    seen["login"] = h.form
                    h._send(200, json.dumps({"result": "success"}), ctype="application/json")
                else:
                    h._send(200, json.dumps({"result": "success", "service": "s"}), ctype="application/json")

            portal.route("/eportal/InterFace.do", interface)
            cfg = {
                "provider": "eportal", "portal": portal.base,
                "username": "u", "password": "明文密码", "verify_tls": False, "timeout": 5,
                "eportal": {"encrypt": "rc4"},
            }
            result = EportalProvider(cfg).login()

        self.assertTrue(result.ok, result.message)
        self.assertEqual(seen["login"]["passwordEncrypt"], "true")
        decoded = rc4(base64.b64decode(seen["login"]["password"]), "0123456789abcdef").decode("utf-8")
        self.assertEqual(decoded, "明文密码")

    def test_failure_message(self) -> None:
        with MockPortal() as portal:
            portal.route("/eportal/", lambda h: h._send(200, ""))
            portal.route("/eportal/InterFace.do", lambda h: h._send(
                200, json.dumps({"result": "fail", "message": "用户不存在"}), ctype="application/json"))
            cfg = {
                "provider": "eportal", "portal": portal.base,
                "username": "u", "password": "p", "verify_tls": False, "timeout": 5,
                "eportal": {"encrypt": "plain"},
            }
            result = EportalProvider(cfg).login()
        self.assertFalse(result.ok)
        self.assertIn("用户不存在", result.message)


class TestDrcomProvider(unittest.TestCase):
    def test_success_marker(self) -> None:
        seen: dict = {}
        with MockPortal() as portal:
            def root(h) -> None:
                if h.command == "POST":
                    seen["form"] = h.form
                    h._send(200, '<html><!--Dr.COMWebLoginID_3.htm--></html>')
                else:
                    h._send(200, '<form><input name="DDDDD"></form>')

            portal.route("/", root)
            cfg = {"provider": "drcom", "portal": portal.base, "username": "13800000000",
                   "password": "123456", "verify_tls": False, "timeout": 5,
                   "drcom": {"key": "123456", "success_marker": "Dr.COMWebLoginID_3"}}
            result = DrcomProvider(cfg).login()

        self.assertTrue(result.ok, result.message)
        self.assertEqual(seen["form"]["DDDDD"], "13800000000")
        self.assertEqual(seen["form"]["upass"], "123456")
        self.assertEqual(seen["form"]["0MKKey"], "123456")

    def test_wrong_password(self) -> None:
        with MockPortal() as portal:
            portal.route("/", lambda h: h._send(200, "<!--Dr.COMWebLoginID_2.htm-->"))
            cfg = {"provider": "drcom", "portal": portal.base, "username": "u",
                   "password": "bad", "verify_tls": False, "timeout": 5, "drcom": {}}
            result = DrcomProvider(cfg).login()
        self.assertFalse(result.ok)


class TestCustomProvider(unittest.TestCase):
    def test_template_and_regex(self) -> None:
        with MockPortal() as portal:
            def login(h) -> None:
                form = h.form
                if form.get("user") == "alice" and form.get("pw") == "s3cret":
                    h._send(200, '{"code":0,"msg":"ok"}')
                else:
                    h._send(200, '{"code":1,"msg":"bad"}')

            portal.route("/api/login", login)
            cfg = {
                "provider": "custom", "portal": portal.base,
                "username": "alice", "password": "s3cret", "verify_tls": False, "timeout": 5,
                "custom": {
                    "login_url": "{portal}/api/login",
                    "method": "POST",
                    "body": "user={username}&pw={password}",
                    "success_regex": '"code":\\s*0',
                },
            }
            result = CustomProvider(cfg).login()
            self.assertTrue(result.ok, result.message)

            cfg["custom"]["success_regex"] = '"code":\\s*999'
            result = CustomProvider(cfg).login()
            self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
