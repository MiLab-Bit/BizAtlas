"""测试隔离：强制离线、确定性环境。

BizAtlas 测试套件按「离线优先」设计（数据源/SMTP/邮箱验证默认关闭），
但 bizatlas.config.Settings（pydantic-settings）会同时读取 os.environ 与仓库根
目录的 .env；生产环境已配置的密钥会泄漏进测试，使本应「未配置」的断言失准。
本 conftest 在任何 bizatlas 模块导入前覆盖关键环境变量（环境变量优先级高于
.env，空串会覆盖文件中的值），恢复离线语义。
"""
from __future__ import annotations

import os

# 邮箱验证默认关闭：注册即视为已验证（向后兼容旧演示/测试无感）。
os.environ["EMAIL_VERIFICATION_ENABLED"] = "false"
os.environ["SMTP_ENABLED"] = "false"

# 清空已配置的 TIANYANCHA_TOKEN（空串覆盖 .env 中的值），使 provider 健康度/
# 就绪检查回到「未配置」离线态，恢复 test_env_ready_both /
# test_provider_health_list / test_start_background_session_offline 的离线预期。
os.environ["TIANYANCHA_TOKEN"] = ""


def pytest_configure(config):
    from bizatlas.config import get_settings

    get_settings.cache_clear()
