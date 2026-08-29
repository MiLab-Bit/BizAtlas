import json

import bizatlas.data.providers_company_json_import as cj


def test_fetch_found(tmp_path, monkeypatch):
    d = tmp_path / "company_json"
    d.mkdir()
    (d / "foo.json").write_text(
        json.dumps({"name": "foo公司", "legalPerson": "李四", "regStatus": "存续", "creditCode": "C1"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANY_JSON_DIR", str(d))
    cj.get_settings.cache_clear()
    prof = cj.fetch_company_profile("foo公司")
    assert prof["ok"] is True
    assert prof["basic"]["legalPerson"] == "李四"
    assert prof["basic"]["regStatus"] == "存续"


def test_fetch_missing(tmp_path, monkeypatch):
    d = tmp_path / "company_json"
    d.mkdir()
    monkeypatch.setenv("COMPANY_JSON_DIR", str(d))
    cj.get_settings.cache_clear()
    prof = cj.fetch_company_profile("不存在")
    assert prof["ok"] is False
    assert "未找到" in prof["message"]
