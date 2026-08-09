from __future__ import annotations

import hashlib
from typing import Any

import httpx

from bizatlas.config import get_settings

_TUSHARE_API = "https://api.tushare.pro"


def tushare_configured() -> bool:
    return bool(get_settings().tushare_token.strip())


def _to_ts_code(symbol: str) -> str:
    """把 akshare 风格代码（600519 / 000001）归一为 Tushare ts_code（600519.SH）。

    已带交易所后缀的（600519.SH）原样返回。无法判断时回退 .SH。
    """
    s = symbol.strip().upper()
    if not s:
        raise ValueError("symbol 为空")
    if "." in s:
        return s
    if s.startswith(("60", "68", "9", "5", "11", "113", "110")):
        return f"{s}.SH"
    if s.startswith(("0", "3", "2", "12", "123", "127", "15")):
        return f"{s}.SZ"
    if s.startswith(("4", "8", "43", "83", "87", "88")):
        return f"{s}.BJ"
    return f"{s}.SH"


def _post(api_name: str, params: dict[str, Any], *, fields: str = "") -> dict[str, Any]:
    token = get_settings().tushare_token.strip()
    if not token:
        raise RuntimeError("未配置 tushare_token，请在 .env 设置 TUSHARE_TOKEN")
    body = {"api_name": api_name, "token": token, "params": params, "fields": fields}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(_TUSHARE_API, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise RuntimeError(f"Tushare 网络错误：{exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Tushare 返回非 JSON")
    if data.get("code", 0) != 0:
        raise RuntimeError(f"Tushare 业务错误 {data.get('code')}: {data.get('msg')}")
    return data.get("data") or {}


def _fina_metrics(ts_code: str) -> list[dict[str, Any]] | None:
    """尝试 fina_indicator（需 500 积分权限）。无权限/空数据返回 None。"""
    try:
        data = _post(
            "fina_indicator",
            {"ts_code": ts_code, "period": "", "fields": "end_date,roe,debt_to_assets,current_ratio,quick_ratio,gross_margin,net_profit_margin"},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "40203" in msg or "访问权限" in msg:
            return None  # 免费 token 无 fina_indicator 权限，走行情降级
        raise
    fields = data.get("fields") or []
    items = data.get("items") or []
    if not fields or not items:
        return None

    row = dict(zip(fields, items[0]))
    end_date = row.get("end_date")
    # name -> (tushare field, 是否百分比需 /100)
    spec: dict[str, tuple[str, bool]] = {
        "ROE": ("roe", True),
        "资产负债率": ("debt_to_assets", True),
        "流动比率": ("current_ratio", False),
        "速动比率": ("quick_ratio", False),
        "毛利率": ("gross_margin", True),
        "净利率": ("net_profit_margin", True),
    }
    metrics: list[dict[str, Any]] = []
    for name, (field, is_pct) in spec.items():
        raw = row.get(field)
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if is_pct and val > 1:
            val = val / 100.0
        metrics.append(
            {
                "name": name,
                "value": val,
                "unit": "ratio",
                "tier": "L1",
                "source": {"type": "api", "ref": f"tushare:{ts_code}:{end_date}", "page": None},
                "confidence": 0.8,
            }
        )
    return metrics or None


def _daily_metrics(ts_code: str) -> list[dict[str, Any]]:
    """免费行情降级：取最近一个交易日 daily 数据，派生基础行情指标。"""
    import datetime as _dt

    end = _dt.date.today().strftime("%Y%m%d")
    start = (_dt.date.today() - _dt.timedelta(days=365)).strftime("%Y%m%d")
    data = _post("daily", {"ts_code": ts_code, "start_date": start, "end_date": end, "fields": "trade_date,close,open,high,low,vol,amount,pct_chg"})
    fields = data.get("fields") or []
    items = data.get("items") or []
    if not fields or not items:
        raise RuntimeError("Tushare daily 返回空数据")
    row = dict(zip(fields, items[0]))  # 最新交易日（按 trade_date 倒序）
    trade_date = row.get("trade_date")

    spec: dict[str, tuple[str, bool, str]] = {
        "最新价": ("close", False, "price"),
        "开盘价": ("open", False, "price"),
        "最高价": ("high", False, "price"),
        "最低价": ("low", False, "price"),
        "涨跌幅": ("pct_chg", True, "ratio"),
        "成交量(手)": ("vol", False, "count"),
        "成交额(千元)": ("amount", False, "amount"),
    }
    metrics: list[dict[str, Any]] = []
    for name, (field, is_pct, unit) in spec.items():
        raw = row.get(field)
        if raw is None or raw == "":
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if is_pct and abs(val) > 1:
            val = val / 100.0
        metrics.append(
            {
                "name": name,
                "value": val,
                "unit": unit,
                "tier": "L1",
                "source": {"type": "api", "ref": f"tushare:{ts_code}:{trade_date}", "page": None},
                "confidence": 0.6,
            }
        )
    if not metrics:
        raise RuntimeError("Tushare 未解析到可用行情字段")
    return metrics


def fetch_stock_basic_metrics(symbol: str) -> list[dict[str, Any]]:
    """经 Tushare Pro 拉取股票基础指标，返回与 akshare 适配器同构的指标 dict 列表。

    优先 fina_indicator（财务比率，需 500 积分权限）；若 token 等级不足（40203），
    自动降级到免费的 daily 行情指标（最新价/涨跌幅/成交量等），保证免费 token 也能出数。
    与 providers_akshare.fetch_stock_basic_metrics 保持相同返回结构，便于按 provider 切换。
    """
    ts_code = _to_ts_code(symbol)
    fina = _fina_metrics(ts_code)
    if fina is not None:
        return fina
    return _daily_metrics(ts_code)
