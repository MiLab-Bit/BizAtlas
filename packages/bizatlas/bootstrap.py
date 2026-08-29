"""冷启动引导：从 .env 播种平台 LLM，并做合规对账自检。

解决交付清单 5-3：新机器只有 LLM_* 环境变量、SQLite 无 provider 时，
前端「模型配置」为空、部分链路误以为 LLM 未就绪。

平台 Settings 仍是 chat_completion 的最终回退；本模块额外保证：
1) model_providers 表有一条 owner=platform 的 active 配置（可被 UI/排查看见）；
2) 启动时跑合规 reconcile，running_not_declared 打警告并写入 readiness。
"""

from __future__ import annotations

import logging
from typing import Any

from bizatlas.config import get_settings

logger = logging.getLogger("bizatlas.bootstrap")

PLATFORM_OWNER_ID = "platform"


def seed_platform_llm_from_env() -> dict[str, Any]:
    """若 .env 已配置 LLM_* 且平台槽位无 active provider，则自动播种。

    返回 {seeded: bool, reason: str, provider_id?: str}。
    """
    settings = get_settings()
    base = (settings.llm_api_base or "").strip()
    key = (settings.llm_api_key or "").strip()
    model = (settings.llm_model or "").strip() or "gpt-4o-mini"
    if not base or not key:
        return {"seeded": False, "reason": "LLM_API_BASE / LLM_API_KEY 未配置，跳过播种"}

    try:
        from bizatlas.identity import model_providers as mp

        existing = mp.get_active_provider(PLATFORM_OWNER_ID, "text")
        if existing:
            # 已有 active：若 base/model 漂移则更新，key 以库内为准（避免每次覆盖用户改动）
            return {
                "seeded": False,
                "reason": "platform text provider 已存在",
                "provider_id": existing.get("id"),
            }

        pid = mp.create_model_provider(
            owner_id=PLATFORM_OWNER_ID,
            name="platform-env",
            provider=settings.llm_provider or "openai_compatible",
            api_key=key,
            base_url=base,
            model=model,
            slot="text",
        )
        # 直接标 active，免人工 /test 一步（密钥来自运维可控的 .env）
        from bizatlas.identity.model_providers import update_status
        import time

        update_status(
            pid,
            PLATFORM_OWNER_ID,
            "active",
            None,
            time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        )
        logger.info("seeded platform LLM provider from .env id=%s model=%s", pid, model)
        return {"seeded": True, "reason": "已从 .env 播种 platform provider", "provider_id": pid}
    except Exception as exc:  # noqa: BLE001
        logger.warning("seed_platform_llm_from_env failed: %s", exc)
        return {"seeded": False, "reason": f"播种失败: {type(exc).__name__}: {exc}"}


def check_compliance_reconciliation() -> dict[str, Any]:
    """启动时对账合规声明与运行时数据源；缺口只告警不阻断启动。"""
    try:
        from bizatlas.compliance.statement import load_compliance_statement

        data = load_compliance_statement()
        if not data.get("available"):
            result = {
                "checked": False,
                "consistent": False,
                "reason": data.get("reason") or "合规声明不可用",
                "running_not_declared": [],
                "declared_not_running": [],
            }
            logger.warning("compliance statement unavailable: %s", result["reason"])
            return result

        recon = data.get("reconciliation") or {}
        running_gap = list(recon.get("running_not_declared") or [])
        declared_gap = list(recon.get("declared_not_running") or [])
        consistent = bool(recon.get("consistent"))
        if running_gap:
            logger.warning(
                "compliance gap running_not_declared=%s (须补声明)",
                running_gap,
            )
        if declared_gap:
            logger.info(
                "compliance declared_not_running=%s (声明了但运行时未启用)",
                declared_gap,
            )
        return {
            "checked": True,
            "consistent": consistent,
            "running_not_declared": running_gap,
            "declared_not_running": declared_gap,
            "reason": "" if consistent else "存在运行中未声明的数据源",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("compliance reconcile failed: %s", exc)
        return {
            "checked": False,
            "consistent": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "running_not_declared": [],
            "declared_not_running": [],
        }


# 进程内缓存最近一次启动检查，供 readiness 读取
_LAST_BOOT: dict[str, Any] = {}


def run_startup_bootstrap() -> dict[str, Any]:
    """lifespan 调用的总入口。"""
    llm_seed = seed_platform_llm_from_env()
    compliance = check_compliance_reconciliation()
    result = {"llm_seed": llm_seed, "compliance": compliance}
    _LAST_BOOT.clear()
    _LAST_BOOT.update(result)
    return result


def last_bootstrap() -> dict[str, Any]:
    return dict(_LAST_BOOT)
