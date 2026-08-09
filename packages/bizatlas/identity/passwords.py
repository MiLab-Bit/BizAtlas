"""密码哈希（零外部依赖）。

环境说明：当前 bizvenv 未安装 bcrypt/passlib/argon2，且 Python 3.13 已移除
标准库 `crypt`。故选用 hashlib.pbkdf2_hmac（SHA-256，per-password 随机盐，
默认 20 万迭代），完全离线、无依赖，且满足「慢哈希」抗暴力破解的基本要求。

存储格式：`<algo>$<iterations>$<salt_b64>$<hash_b64>`，便于未来平滑升级算法。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

ALGO = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 200_000


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGO}${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_b64, hash_b64 = stored.split("$")
        if algo != ALGO:
            return False
        iters = int(iters_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        return hmac.compare_digest(actual, expected)
    except Exception:  # noqa: BLE001
        return False
