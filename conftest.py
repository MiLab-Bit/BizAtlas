"""Pytest 全局夹具：测试套件默认离线。

原因：仓库 .env 现含真实 LLM 网关凭据（FastToken，www.abc-ai.cn）与真实 SMTP 授权码。
- run_analyze 等核心路径在 llm_configured() 为 True 时会调用 polish_* → 真实网络；
- 邮箱验证/密码找回在 smtp_enabled / email_verification_enabled 为 True 时会真实发信，
  并让未验证账号登录被拦截，会拖慢/破坏离线确定性测试。

做法：用空字符串覆盖 LLM_API_KEY / LLM_API_BASE（环境变量优先于 .env 文件），
并把 EMAIL_VERIFICATION_ENABLED / SMTP_ENABLED 强制为 false，使整个测试会话离线且
不触网发信。运行时（uvicorn / 脚本，不加载本 conftest）仍按 .env 正常联网发信。
需要验证发信/拦截逻辑的新测试，可在用例内用 monkeypatch 重新启用并注入 fake sender。
"""

import os

import pytest

from bizatlas.config import get_settings

_LLM_ENV_KEYS = ("LLM_API_KEY", "LLM_API_BASE")
_EMAIL_ENV_KEYS = ("EMAIL_VERIFICATION_ENABLED", "SMTP_ENABLED")


@pytest.fixture(autouse=True, scope="session")
def _force_offline_llm_for_tests():
    saved = {k: os.environ.get(k) for k in _LLM_ENV_KEYS + _EMAIL_ENV_KEYS}
    for k in _LLM_ENV_KEYS:
        os.environ[k] = ""  # 空值覆盖 .env 文件中的真实凭据
    for k in _EMAIL_ENV_KEYS:
        os.environ[k] = "false"  # 隔离邮件发信与验证拦截，保护离线测试
    get_settings.cache_clear()
    yield
    for k, val in saved.items():
        if val is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = val
    get_settings.cache_clear()
