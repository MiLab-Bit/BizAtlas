from __future__ import annotations

from typing import Any


class IndustryStaticProvider:
    id = "industry_static"
    name = "静态行业参数"

    def enabled(self) -> bool:
        try:
            from bizatlas.industry.benchmarks import load_benchmarks

            data = load_benchmarks()
            return bool(data.get("industries"))
        except Exception:  # noqa: BLE001
            return False

    def health(self) -> dict[str, Any]:
        ok = self.enabled()
        return {
            "id": self.id,
            "ok": ok,
            "status": "ready" if ok else "stub",
            "message": "content/industry/benchmarks.yaml" if ok else "missing benchmarks",
        }

    def fetch(self, company_key: str, fields: list[str]) -> list[dict[str, Any]]:
        _ = company_key, fields
        return []
