from unittest.mock import MagicMock, patch

import bizatlas.data.providers_cninfo as ci


def test_configured():
    assert ci.cninfo_configured() is True


def test_fetch_announcements_mock():
    # 沪深京股票列表 JSON（orgId 映射） + 公告列表均走 httpx.Client
    client = MagicMock()
    client.get.return_value.raise_for_status.return_value = None
    client.get.return_value.json.return_value = {
        "stockList": [{"code": "600519", "orgId": "gssh0600519"}]
    }
    client.post.return_value.raise_for_status.return_value = None
    client.post.return_value.json.return_value = {
        "announcements": [
            {
                "announcementId": "1220000001",
                "announcementTitle": "年度报告",
                # 2024-01-01 00:00:00 CST -> 毫秒时间戳
                "announcementTime": 1704067200000,
                "adjunctType": "PDF",
                "secCode": "600519",
                "secName": "贵州茅台",
            }
        ]
    }

    with patch("bizatlas.data.providers_cninfo.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value = client
        out = ci.fetch_announcements("600519")

    assert len(out) == 1
    assert out[0]["title"] == "年度报告"
    assert out[0]["time"] == "2024-01-01"
    assert out[0]["sec_code"] == "600519"
    assert out[0]["announcement_id"] == "1220000001"
    assert out[0]["url"].startswith(f"{ci._DETAIL}?")
    assert "stockCode=600519" in out[0]["url"]
    assert "orgId=gssh0600519" in out[0]["url"]
    # 未传 orgId 时应从 mock 的股票列表解析到
    client.get.assert_called_once()


def test_fetch_requires_known_code():
    client = MagicMock()
    client.get.return_value.raise_for_status.return_value = None
    client.get.return_value.json.return_value = {"stockList": []}

    with patch("bizatlas.data.providers_cninfo.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value = client
        try:
            ci.fetch_announcements("999999")
        except RuntimeError as exc:
            assert "orgId" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for unknown code")
