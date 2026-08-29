from __future__ import annotations

import json
import time
from typing import Any

from bizatlas.data.db import get_connection

_CACHE_TTL = 12 * 3600.0  # 12h：财务日更，日内复用即可


def _cache_get(symbol: str) -> list[dict[str, Any]] | None:
    try:
        conn = get_connection()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS provider_cache ("
                "cache_key TEXT PRIMARY KEY, content TEXT NOT NULL, "
                "created_at REAL NOT NULL, hits INT NOT NULL DEFAULT 0)"
            )
            key = f"akshare:stock_basic:{symbol}"
            row = conn.execute(
                "SELECT content, created_at FROM provider_cache WHERE cache_key=?", (key,)
            ).fetchone()
            if not row:
                return None
            if time.time() - float(row["created_at"]) > _CACHE_TTL:
                conn.execute("DELETE FROM provider_cache WHERE cache_key=?", (key,))
                conn.commit()
                return None
            conn.execute("UPDATE provider_cache SET hits=hits+1 WHERE cache_key=?", (key,))
            conn.commit()
            data = json.loads(row["content"])
            return data if isinstance(data, list) else None
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return None


def _cache_put(symbol: str, metrics: list[dict[str, Any]]) -> None:
    try:
        conn = get_connection()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS provider_cache ("
                "cache_key TEXT PRIMARY KEY, content TEXT NOT NULL, "
                "created_at REAL NOT NULL, hits INT NOT NULL DEFAULT 0)"
            )
            key = f"akshare:stock_basic:{symbol}"
            conn.execute(
                "INSERT INTO provider_cache (cache_key, content, created_at, hits) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(cache_key) DO UPDATE SET content=excluded.content, "
                "created_at=excluded.created_at, hits=1",
                (key, json.dumps(metrics, ensure_ascii=False), time.time()),
            )
            # 简单容量控制：最多 500 条
            n = conn.execute("SELECT COUNT(*) AS n FROM provider_cache").fetchone()["n"]
            if n > 500:
                excess = n - 500
                old = conn.execute(
                    "SELECT cache_key FROM provider_cache ORDER BY created_at ASC LIMIT ?",
                    (excess,),
                ).fetchall()
                for r in old:
                    conn.execute("DELETE FROM provider_cache WHERE cache_key=?", (r["cache_key"],))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return None


def fetch_stock_basic_metrics(symbol: str) -> list[dict[str, Any]]:
    """Best-effort AKShare fetch. Returns metric dicts or raises with readable error.

    命中 SQLite 缓存（12h TTL）时直接返回，避免重复冷拉拖垮 896MB 单机。
    """
    symbol = symbol.strip()
    if not symbol:
        raise ValueError("symbol 为空")

    cached = _cache_get(symbol)
    if cached is not None:
        return cached

    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("未安装 akshare，请 pip install akshare") from exc

    # 尝试关键财务指标（接口可能随版本变化，失败则明确报错）
    metrics: list[dict[str, Any]] = []
    try:
        # 东财财务分析指标：可能较慢
        df = ak.stock_financial_analysis_indicator(symbol=symbol)
        if df is None or df.empty:
            raise RuntimeError("AKShare 返回空数据")
        row = df.iloc[0].to_dict()
        mapping = {
            "流动比率": ["流动比率"],
            "速动比率": ["速动比率"],
            "资产负债率": ["资产负债率"],
            "毛利率": ["销售毛利率", "毛利率"],
            "ROE": ["净资产收益率", "ROE"],
        }
        for name, keys in mapping.items():
            for k in keys:
                if k in row and row[k] is not None:
                    try:
                        val = float(row[k])
                    except Exception:  # noqa: BLE001
                        continue
                    # 常见百分比字段
                    if name in {"资产负债率", "毛利率", "ROE"} and val > 1:
                        val = val / 100.0
                    metrics.append(
                        {
                            "name": name,
                            "value": val,
                            "unit": "ratio",
                            "tier": "L1",
                            "source": {
                                "type": "api",
                                "ref": f"akshare:{symbol}",
                                "page": None,
                            },
                            "confidence": 0.7,
                        }
                    )
                    break
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"AKShare 拉取失败：{exc}") from exc

    if not metrics:
        raise RuntimeError("AKShare 未解析到可用指标字段")
    _cache_put(symbol, metrics)
    return metrics
