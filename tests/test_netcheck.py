"""联网状态检测测试。"""
from __future__ import annotations

import unittest

from campusnet import netcheck
from campusnet.http import HttpClient
from tests.mock_portal import MockPortal


def make_cfg(base: str, paths=("/generate_204",)) -> dict:
    return {
        "use_proxy": False,
        "proxies": {},
        "verify_tls": False,
        "check": {
            "timeout": 3,
            "urls": [{"url": base + p, "expect": 204} for p in paths],
        },
    }


class TestNetcheck(unittest.TestCase):
    def test_204_means_online(self) -> None:
        with MockPortal() as portal:
            portal.route("/generate_204", lambda h: h._send(204, ""))
            online, results = netcheck.is_online(make_cfg(portal.base))
            self.assertTrue(online)
            self.assertTrue(results[0].ok)

    def test_200_page_means_offline(self) -> None:
        # 未认证时 portal 会把 204 顶替成登录页
        with MockPortal() as portal:
            portal.route("/generate_204", lambda h: h._send(200, "<html>请先登录</html>"))
            online, results = netcheck.is_online(make_cfg(portal.base))
            self.assertFalse(online)
            self.assertIn("portal", results[0].detail)

    def test_unreachable_is_offline(self) -> None:
        cfg = make_cfg("http://127.0.0.1:1")
        online, results = netcheck.is_online(cfg)
        self.assertFalse(online)
        self.assertFalse(results[0].ok)

    def test_contains_requirement(self) -> None:
        with MockPortal() as portal:
            portal.route("/detect", lambda h: h._send(200, "No"))
            cfg = {
                "check": {
                    "timeout": 3,
                    "urls": [{"url": portal.base + "/detect", "expect": 200, "contains": "Success"}],
                }
            }
            online, _ = netcheck.is_online(cfg)
            self.assertFalse(online)

    def test_any_ok_wins(self) -> None:
        with MockPortal() as portal:
            portal.route("/bad", lambda h: h._send(200, "portal"))
            portal.route("/generate_204", lambda h: h._send(204, ""))
            cfg = make_cfg(portal.base, paths=("/bad", "/generate_204"))
            online, results = netcheck.is_online(cfg)
            self.assertTrue(online)
            self.assertEqual([r.ok for r in results], [False, True])

    def test_guess_portal(self) -> None:
        results = [
            netcheck.ProbeResult("http://a/generate_204", False, "redirect", "https://10.0.0.55/eportal/x"),
        ]
        self.assertEqual(netcheck.guess_portal(results), "https://10.0.0.55")

    def test_redirect_followed_still_reports_target(self) -> None:
        with MockPortal() as portal:
            portal.route("/generate_204",
                         lambda h: h._send(302, "", headers={"Location": portal.base + "/login"}))
            portal.route("/login", lambda h: h._send(200, "login page"))
            online, results = netcheck.is_online(make_cfg(portal.base))
            self.assertFalse(online)
            self.assertTrue(results[0].redirect and "/login" in results[0].redirect)


if __name__ == "__main__":
    unittest.main()
