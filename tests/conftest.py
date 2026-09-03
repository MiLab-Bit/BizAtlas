"""测试隔离：强制离线、确定性环境。

BizAtlas 测试套件按「离线优先」设计（数据源/SMTP/邮箱验证默认关闭），
但 bizatlas.config.Settings（pydantic-settings）会同时读取 os.environ 与仓库根
目录的 .env；生产环境已配置的密钥会泄漏进测试，使本应「未配置」的断言失准。
本 conftest 在任何 bizatlas 模块导入前覆盖关键环境变量（环境变量优先级高于
.env，空串会覆盖文件中的值），恢复离线语义。

副作用隔离：历史实现直接写仓库内文件，每跑一次测试都会污染工作区——
  * data/bizatlas.sqlite：塞入「离线测试企业 / 单测上传企业 / EvCo / E2E /
    CiteCo」等脏数据（2026-09-03 一次清理出 107 家企业 / 895 行关联记录）；
  * content/rules/custom_pilot.yaml：NL 编译器离线测试会 append 重复的
    pilot 规则（同一条「流动比率 < 0.9」被反复 seed，工作区永远不干净）。
这里把 DB / uploads / exports / rules 一并重定向到会话级临时目录（rules 先
复制一份作为初始状态），进程退出时自动清理，仓库与生产库保持干净。
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

# 邮箱验证默认关闭：注册即视为已验证（向后兼容旧演示/测试无感）。
os.environ["EMAIL_VERIFICATION_ENABLED"] = "false"
os.environ["SMTP_ENABLED"] = "false"

# 清空已配置的 TIANYANCHA_TOKEN（空串覆盖 .env 中的值），使 provider 健康度/
# 就绪检查回到「未配置」离线态，恢复 test_env_ready_both /
# test_provider_health_list / test_start_background_session_offline 的离线预期。
os.environ["TIANYANCHA_TOKEN"] = ""

REPO_ROOT = Path(__file__).resolve().parents[1]


def _isolate_test_dirs() -> Path:
    """把 DB / 上传 / 导出 / 规则目录重定向到会话级临时目录，避免污染工作区。

    环境变量优先级高于 .env；bizatlas.data.db 的 get_connection/init_db 全部走
    settings.bizatlas_db_path（自动 mkdir + CREATE TABLE IF NOT EXISTS），因此
    重定向后测试仍能完整建库建表，无需改动任何业务代码。

    rules 目录特殊处理：测试需要读到仓库内的既有规则（rules_loaded 断言依赖），
    因此先整体复制一份到临时目录再重定向，测试可自由写而仓库文件不受影响。
    """
    tmp = Path(tempfile.mkdtemp(prefix="bizatlas-test-"))
    os.environ["BIZATLAS_DB_PATH"] = str(tmp / "bizatlas.sqlite")
    os.environ["BIZATLAS_UPLOAD_DIR"] = str(tmp / "uploads")
    os.environ["BIZATLAS_EXPORT_DIR"] = str(tmp / "exports")

    rules_src = REPO_ROOT / "content" / "rules"
    rules_dst = tmp / "rules"
    if rules_src.is_dir():
        shutil.copytree(rules_src, rules_dst)
        os.environ["BIZATLAS_RULES_DIR"] = str(rules_dst)

    atexit.register(shutil.rmtree, tmp, ignore_errors=True)
    return tmp


_TEST_TMP_DIR = _isolate_test_dirs()


def pytest_configure(config):
    from bizatlas.config import get_settings

    get_settings.cache_clear()
