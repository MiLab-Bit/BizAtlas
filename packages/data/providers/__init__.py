"""Data providers — stubs until keys are configured in registry.yaml / .env."""

from __future__ import annotations

from typing import Any, Protocol


class DataProvider(Protocol):
    id: str
    name: str

    def enabled(self) -> bool: ...
    def health(self) -> dict[str, Any]: ...
    def fetch(self, company_key: str, fields: list[str]) -> list[dict[str, Any]]: ...


# 占位导出：实现文件稍后按 registry id 补齐
PROVIDER_MODULES = {
    "upload": "packages.data.providers.upload_financial",
    "fixture": "packages.data.providers.fixture_provider",
    "industry_static": "packages.data.providers.industry_static",
    "akshare": "packages.data.providers.akshare_financial",
    "tushare": "packages.data.providers.tushare_financial",
    "tianyancha": "packages.data.providers.tianyancha",
    "qichacha": "packages.data.providers.qichacha",
    "company_json_import": "packages.data.providers.company_json_import",
    "cninfo": "packages.data.providers.cninfo",
    "news_akshare": "packages.data.providers.news_akshare",
}
