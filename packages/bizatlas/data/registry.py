from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bizatlas.config import get_settings
from bizatlas.contracts.models import ProviderHealth


def load_registry(path: str | Path | None = None) -> dict[str, Any]:
    settings = get_settings()
    registry_path = Path(path or settings.bizatlas_providers_registry)
    if not registry_path.exists():
        return {"version": 1, "providers": []}
    with registry_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "providers": []}


def _env_ready(env_keys: list[str]) -> tuple[bool, str]:
    settings = get_settings()
    missing: list[str] = []
    for key in env_keys:
        attr = key.lower()
        val = getattr(settings, attr, "") or ""
        if not str(val).strip():
            missing.append(key)
    if missing:
        return False, f"missing env: {', '.join(missing)}"
    return True, "ok"


def provider_health_list() -> list[ProviderHealth]:
    registry = load_registry()
    out: list[ProviderHealth] = []
    for item in registry.get("providers", []):
        enabled = bool(item.get("enabled", False))
        status = str(item.get("status", "stub"))
        env_keys = list(item.get("env") or [])
        needs_key = bool(item.get("needs_key", False))
        key_ok, key_msg = _env_ready(env_keys) if needs_key else (True, "ok")
        ok = enabled and status == "ready" and key_ok
        message = key_msg
        if not enabled:
            message = "disabled in registry (placeholder)"
        elif status == "stub":
            message = "stub implementation — not wired yet"
            ok = False
        out.append(
            ProviderHealth(
                id=str(item.get("id")),
                name=str(item.get("name", item.get("id"))),
                enabled=enabled,
                status=status if enabled else "disabled",
                ok=ok,
                message=message,
            )
        )
    return out
