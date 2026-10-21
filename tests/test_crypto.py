"""加密与编码工具的测试。"""
from __future__ import annotations

import base64
import hashlib
import unittest

from campusnet.crypto import (
    SRUN_ALPHABET,
    eportal_encrypt,
    hmac_md5,
    rc4,
    sha1,
    xdecode,
    xencode,
)


class TestRC4(unittest.TestCase):
    def test_known_vector(self) -> None:
        # RC4 经典测试向量：key="Key", plaintext="Plaintext"
        expected = bytes.fromhex("BBF316E8D940AF0AD3")
        self.assertEqual(rc4(b"Plaintext", "Key"), expected)

    def test_wiki_vector(self) -> None:
        # key="Wiki", plaintext="pedia" -> 1021BF0420
        self.assertEqual(rc4(b"pedia", "Wiki").hex().upper(), "1021BF0420")

    def test_roundtrip(self) -> None:
        data = "中文密码 with space".encode("utf-8")
        self.assertEqual(rc4(rc4(data, "secret"), "secret"), data)

    def test_empty_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            rc4(b"x", "")


class TestXEncode(unittest.TestCase):
    def test_roundtrip_ascii(self) -> None:
        encoded = xencode("hello world", "token123")
        self.assertEqual(xdecode(encoded, "token123"), "hello world")

    def test_roundtrip_unicode(self) -> None:
        text = '{"username":"张三","password":"p@ss:中文"}'
        self.assertEqual(xdecode(xencode(text, "tok"), "tok"), text)

    def test_empty(self) -> None:
        self.assertEqual(xencode("", "tok"), "")
        self.assertEqual(xdecode("", "tok"), "")

    def test_alphabet_is_a_permutation(self) -> None:
        std = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")
        self.assertEqual(len(SRUN_ALPHABET), 64)
        self.assertEqual(len(set(SRUN_ALPHABET)), 64)
        self.assertEqual(set(SRUN_ALPHABET), std)  # 必须是标准字母表的排列

    def test_uses_custom_alphabet(self) -> None:
        encoded = xencode("hello world", "token123")
        self.assertEqual(len(encoded), len(base64.b64encode(b"hello world").decode()))
        # 除了 base64 的补位符，其余字符都必须落在自定义字母表里
        self.assertTrue(set(encoded.replace("=", "")) <= set(SRUN_ALPHABET))
        # 输出不应等于标准 base64，否则说明翻译没生效
        self.assertNotEqual(encoded, base64.b64encode(rc4(b"hello world", "token123")).decode())


class TestHashHelpers(unittest.TestCase):
    def test_hmac_md5_is_md5_of_concat(self) -> None:
        self.assertEqual(
            hmac_md5("pwd", "tok"),
            hashlib.md5(b"pwdtok").hexdigest(),
        )

    def test_sha1(self) -> None:
        self.assertEqual(sha1("abc"), "a9993e364706816aba3e25717850c26c9cd0d89d")


class TestEportalEncrypt(unittest.TestCase):
    def test_roundtrip(self) -> None:
        key = "5opkytHOleCjXA=="
        cipher = eportal_encrypt("mypassword", key)
        plain = rc4(base64.b64decode(cipher), key).decode("utf-8")
        self.assertEqual(plain, "mypassword")

    def test_is_base64(self) -> None:
        cipher = eportal_encrypt("abc", "0123456789abcdef")
        base64.b64decode(cipher)  # 不抛异常即可


if __name__ == "__main__":
    unittest.main()
