import hashlib

import pytest
from unittest.mock import patch

import bizatlas.data.providers_qichacha as qc


def test_sign_deterministic():
    params = {"keyword": "foo", "pageIndex": "1"}
    sig = qc._sign(params, "appkey", "secret")
    assert len(sig) == 32 and sig.isupper()
    expected = hashlib.md5(("appkey" + "secret" + "keyword=foo&pageIndex=1").encode()).hexdigest().upper()
    assert sig == expected


def test_configured_requires_secret(monkeypatch):
    monkeypatch.setenv("QICHACHA_TOKEN", "appkey")
    monkeypatch.setenv("QICHACHA_SECRET", "")
    qc.get_settings.cache_clear()
    assert qc.qichacha_configured() is False
    monkeypatch.setenv("QICHACHA_SECRET", "sec")
    qc.get_settings.cache_clear()
    assert qc.qichacha_configured() is True


def test_call_raises_without_secret():
    class FakeSettings:
        qichacha_token = "appkey"
        qichacha_secret = ""

    with patch.object(qc, "get_settings", return_value=FakeSettings()):
        with pytest.raises(RuntimeError, match="qichacha_secret"):
            qc._call("/ECIEnterpriseInfoSearch", {"keyword": "x"})


def test_fetch_company_profile_handles_missing_secret():
    class FakeSettings:
        qichacha_token = "appkey"
        qichacha_secret = ""

    with patch.object(qc, "get_settings", return_value=FakeSettings()):
        prof = qc.fetch_company_profile("测试公司")
    assert prof["ok"] is False
    assert "qichacha_secret" in prof["message"]


def test_fetch_company_profile_mock(monkeypatch):
    monkeypatch.setenv("QICHACHA_TOKEN", "appkey")
    monkeypatch.setenv("QICHACHA_SECRET", "sec")
    qc.get_settings.cache_clear()
    search = {"Status": "200", "Result": {"ECIList": [{"Name": "测试公司", "KeyNo": "K1", "CreditCode": "X1"}]}}
    info = {"Status": "200", "Result": {"Name": "测试公司", "CreditCode": "X1", "LegalPerson": "张三", "Status": "存续", "RegistCapi": "100万"}}
    dish = {"Status": "200", "Result": {"Total": 0, "DishonestList": []}}

    def fake_call(api, params):
        if api.endswith("Search"):
            return search
        if api.endswith("Info"):
            return info
        return dish

    with patch.object(qc, "_call", side_effect=fake_call):
        prof = qc.fetch_company_profile("测试公司")
    assert prof["ok"] is True
    assert prof["basic"]["legalPerson"] == "张三"
    assert prof["basic"]["regStatus"] == "存续"
