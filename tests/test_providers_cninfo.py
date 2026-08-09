from unittest.mock import MagicMock, patch

import bizatlas.data.providers_cninfo as ci


def test_configured():
    assert ci.cninfo_configured() is True


def test_fetch_announcements_mock():
    client = MagicMock()
    client.get.return_value.raise_for_status.return_value = None
    client.get.return_value.json.return_value = {"hits": [{"orgId": "org1", "name": "foo"}]}
    client.post.return_value.raise_for_status.return_value = None
    client.post.return_value.json.return_value = {
        "announcements": [
            {"announcementId": "1", "announcementTitle": "年报", "announcementTime": "2024-01-01", "adjunctType": "PDF", "adjunctUrl": "/a/b.pdf"}
        ]
    }

    with patch("bizatlas.data.providers_cninfo.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value = client
        out = ci.fetch_announcements("600519")

    assert len(out) == 1
    assert out[0]["title"] == "年报"
    assert out[0]["url"].startswith("https://www.cninfo.com.cn/")
    assert out[0]["time"] == "2024-01-01"
