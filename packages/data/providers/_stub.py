"""Shared stub provider: returns empty list, declares not configured."""

from __future__ import annotations

from typing import Any


class StubProvider:
    """未配密钥 / 未实现时的安全占位：不抛错、不中断流水线。"""

    def __init__(self, provider_id: str, name: str) -> None:
        self.id = provider_id
        self.name = name

    def enabled(self) -> bool:
        return False

    def health(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ok": False,
            "status": "stub",
            "message": "placeholder — enable in content/providers/registry.yaml after configuring .env",
        }

    def fetch(self, company_key: str, fields: list[str]) -> list[dict[str, Any]]:
        return []
