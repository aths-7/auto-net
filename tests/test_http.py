"""HTTP 会话与 JSONP 解析的测试。"""
from __future__ import annotations

import json
import unittest

from campusnet.http import HttpClient, parse_jsonp
from tests.mock_portal import MockPortal


class TestParseJsonp(unittest.TestCase):
    def test_plain_json(self) -> None:
        self.assertEqual(parse_jsonp('{"a":1}'), {"a": 1})

    def test_jsonp(self) -> None:
        self.assertEqual(parse_jsonp('jQuery123_456({"challenge":"abc"})'), {"challenge": "abc"})

    def test_marker_form(self) -> None:
        self.assertEqual(parse_jsonp('&&&START&&&{"res":"ok"}'), {"res": "ok"})

    def test_null(self) -> None:
        self.assertIsNone(parse_jsonp("cb(null)"))

    def test_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_jsonp("<<<not json>>>")


class TestHttpClient(unittest.TestCase):
    def test_get_and_cookie(self) -> None:
        with MockPortal() as portal:
            portal.route("/hello", lambda h: h._send(200, "world"))

            def set_cookie(h) -> None:
                h._send(200, "ok", headers={"Set-Cookie": "sid=abc123; Path=/"})

            portal.route("/set", set_cookie)
            client = HttpClient()
            self.assertEqual(client.get(portal.base + "/hello").text, "world")
            client.get(portal.base + "/set")
            names = {c.name: c.value for c in client.cookies}
            self.assertEqual(names.get("sid"), "abc123")

    def test_post_form(self) -> None:
        with MockPortal() as portal:
            portal.route("/submit", lambda h: h._send(200, json.dumps(h.form)))
            client = HttpClient()
            resp = client.post(portal.base + "/submit", data={"u": "张三", "p": "a b"})
            self.assertEqual(resp.json(), {"u": "张三", "p": "a b"})

    def test_params_encoding(self) -> None:
        with MockPortal() as portal:
            portal.route("/q", lambda h: h._send(200, json.dumps(h.query)))
            client = HttpClient()
            resp = client.get(portal.base + "/q", params={"password": "{MD5}abc+/="})
            self.assertEqual(resp.json()["password"], "{MD5}abc+/=")

    def test_404_not_raise(self) -> None:
        with MockPortal() as portal:
            client = HttpClient()
            self.assertEqual(client.get(portal.base + "/nope").status, 404)


if __name__ == "__main__":
    unittest.main()
