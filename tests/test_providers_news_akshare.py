import pandas as pd
from unittest.mock import patch

import bizatlas.data.providers_news_akshare as ns


def test_configured():
    assert ns.news_akshare_configured() is True


def test_fetch_company_news_mock():
    df = pd.DataFrame(
        [
            {
                "关键词": "600519",
                "新闻标题": "t",
                "新闻内容": "c" * 600,
                "发布时间": "2024-01-01 10:00:00",
                "文章来源": "s",
                "新闻链接": "u",
            }
        ]
    )
    with patch("akshare.stock_news_em", return_value=df):
        n = ns.fetch_company_news("600519")
    assert len(n) == 1
    assert n[0]["title"] == "t"
    assert n[0]["source"] == "s"
    assert len(n[0]["content"]) <= 500  # 截断
