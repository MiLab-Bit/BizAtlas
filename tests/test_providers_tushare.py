from unittest.mock import patch

import bizatlas.data.providers_tushare as ts


def test_to_ts_code():
    assert ts._to_ts_code("600519") == "600519.SH"
    assert ts._to_ts_code("000001.SZ") == "000001.SZ"
    assert ts._to_ts_code("300750") == "300750.SZ"
    assert ts._to_ts_code("830799") == "830799.BJ"


def test_fetch_fina_metrics():
    fina = {
        "fields": ["end_date", "roe", "debt_to_assets", "current_ratio", "quick_ratio", "gross_margin", "net_profit_margin"],
        "items": [["20231231", 25.5, 40.2, 2.1, 1.5, 55.3, 30.1]],
    }
    with patch.object(ts, "_post", return_value=fina):
        metrics = ts.fetch_stock_basic_metrics("600519")
    names = {m["name"] for m in metrics}
    assert "ROE" in names
    assert next(m for m in metrics if m["name"] == "ROE")["value"] == 0.255  # /100
    assert next(m for m in metrics if m["name"] == "流动比率")["value"] == 2.1  # as-is


def test_fetch_daily_fallback_on_permission():
    fina_err = RuntimeError("Tushare 业务错误 40203: 访问权限")
    daily = {
        "fields": ["trade_date", "close", "open", "high", "low", "vol", "amount", "pct_chg"],
        "items": [["20240102", 100.0, 99.0, 101.0, 98.0, 1000.0, 50000.0, 1.5]],
    }

    def fake_post(api, params, fields=""):
        if api == "fina_indicator":
            raise fina_err
        return daily

    with patch.object(ts, "_post", side_effect=fake_post):
        metrics = ts.fetch_stock_basic_metrics("600519")
    names = {m["name"] for m in metrics}
    assert "最新价" in names
    assert next(m for m in metrics if m["name"] == "涨跌幅")["value"] == 0.015  # /100


def test_configured(monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "x")
    ts.get_settings.cache_clear()
    assert ts.tushare_configured() is True
    monkeypatch.setenv("TUSHARE_TOKEN", "")
    ts.get_settings.cache_clear()
    assert ts.tushare_configured() is False
