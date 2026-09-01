"""validation/report.py 离线测试（0% → 全覆盖）。

load_backtest_report 在报告缺失/损坏时显式披露、不编造数字；
本文件覆盖缺失、损坏、有效三种路径，以及 report_path 的定位口径。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import json

from bizatlas.validation import report as rep


def _fake_settings(root):
    return SimpleNamespace(root=root)


def test_report_missing(tmp_path):
    fake = _fake_settings(tmp_path)
    with patch("bizatlas.validation.report.get_settings", return_value=fake):
        r = rep.load_backtest_report()
    assert r["available"] is False
    assert "尚未生成" in r["reason"]
    assert "不" in r["disclosure"]


def test_report_corrupt(tmp_path):
    p = tmp_path / "content" / "validation" / "backtest_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ 这不是合法 json", encoding="utf-8")
    fake = _fake_settings(tmp_path)
    with patch("bizatlas.validation.report.get_settings", return_value=fake):
        r = rep.load_backtest_report()
    assert r["available"] is False
    assert "解析失败" in r["reason"]


def test_report_valid(tmp_path):
    p = tmp_path / "content" / "validation" / "backtest_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"sample_size": 10, "auc": 0.82}), encoding="utf-8")
    fake = _fake_settings(tmp_path)
    with patch("bizatlas.validation.report.get_settings", return_value=fake):
        r = rep.load_backtest_report()
    assert r["available"] is True
    assert r["sample_size"] == 10
    assert r["auc"] == 0.82


def test_report_path(tmp_path):
    fake = _fake_settings(tmp_path)
    with patch("bizatlas.validation.report.get_settings", return_value=fake):
        assert rep.report_path() == tmp_path / "content" / "validation" / "backtest_report.json"
