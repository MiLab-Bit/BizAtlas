from __future__ import annotations

from typing import Any


def fetch_stock_basic_metrics(symbol: str) -> list[dict[str, Any]]:
    """Best-effort AKShare fetch. Returns metric dicts or raises with readable error."""
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("未安装 akshare，请 pip install akshare") from exc

    symbol = symbol.strip()
    if not symbol:
        raise ValueError("symbol 为空")

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
                            "source": {"type": "api", "ref": f"akshare:{symbol}", "page": None},
                            "confidence": 0.7,
                        }
                    )
                    break
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"AKShare 拉取失败：{exc}") from exc

    if not metrics:
        raise RuntimeError("AKShare 未解析到可用指标字段")
    return metrics
