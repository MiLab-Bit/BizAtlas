"""Pytest 全局夹具：测试套件默认离线。

原因：仓库 .env 现含真实 LLM 网关凭据（FastToken，www.abc-ai.cn）。
run_analyze 等核心路径在 llm_configured() 为 True 时会调用 polish_* → 真实网络，
会让 golden / 确定性（writer-only 铁律）测试变慢、不确定甚至失败。

做法：用空字符串覆盖 LLM_API_KEY / LLM_API_BASE 的环境变量（pydantic-settings 中
环境变量优先于 .env 文件），并清掉 settings 缓存，使整个测试会话强制离线。
运行时（uvicorn / 脚本，不加载本 conftest）仍按 .env 正常联网。
"""

import os

import pytest

from bizatlas.config import get_settings

_LLM_ENV_KEYS = ("LLM_API_KEY", "LLM_API_BASE")


@pytest.fixture(autouse=True, scope="session")
def _force_offline_llm_for_tests():
    saved = {k: os.environ.get(k) for k in _LLM_ENV_KEYS}
    for k in _LLM_ENV_KEYS:
        os.environ[k] = ""  # 空值覆盖 .env 文件中的真实凭据
    get_settings.cache_clear()
    yield
    for k, val in saved.items():
        if val is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = val
    get_settings.cache_clear()
