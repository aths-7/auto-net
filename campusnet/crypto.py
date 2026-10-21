"""加密/编码工具：RC4、Srun 自定义 Base64、HMAC-MD5、chksum。

全部基于标准库实现，不引入 pycryptodome 之类的重依赖 —— 为了一个校园网
自动登录脚本装一堆 C 扩展，不值当。
"""
from __future__ import annotations

import base64
import hashlib

# 深澜(Srun) portal 客户端 JS 里硬编码的自定义 base64 字母表
SRUN_ALPHABET = "LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA"
_STD_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_SRUN_TRANS = str.maketrans(_STD_ALPHABET, SRUN_ALPHABET)
_SRUN_UNTRANS = str.maketrans(SRUN_ALPHABET, _STD_ALPHABET)


def rc4(data: bytes, key: str) -> bytes:
    """标准 RC4。data 为原始字节，key 为字符串。"""
    if not key:
        raise ValueError("RC4 key 不能为空")
    key_bytes = key.encode("utf-8")
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key_bytes[i % len(key_bytes)]) & 0xFF
        s[i], s[j] = s[j], s[i]

    out = bytearray()
    i = j = 0
    for ch in data:
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out.append(ch ^ s[(s[i] + s[j]) & 0xFF])
    return bytes(out)


def hmac_md5(password: str, token: str) -> str:
    """深澜用 md5(password + token)，注意不是标准的 HMAC 结构。"""
    return hashlib.md5((password + token).encode("utf-8")).hexdigest()


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def xencode(msg: str, key: str) -> str:
    """深澜的 xencode：RC4 -> 标准 base64 -> 换成自定义字母表。"""
    if msg == "":
        return ""
    raw = rc4(msg.encode("utf-8"), key)
    b64 = base64.b64encode(raw).decode("ascii")
    return b64.translate(_SRUN_TRANS)


def xdecode(encoded: str, key: str) -> str:
    """xencode 的逆运算，主要给单元测试和排障用。"""
    if encoded == "":
        return ""
    b64 = encoded.translate(_SRUN_UNTRANS)
    raw = base64.b64decode(b64)
    return rc4(raw, key).decode("utf-8", "replace")


def eportal_encrypt(password: str, key: str) -> str:
    """锐捷 ePortal 的密码加密：RC4(pwd, key) -> 标准 base64。"""
    return base64.b64encode(rc4(password.encode("utf-8"), key)).decode("ascii")


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()
