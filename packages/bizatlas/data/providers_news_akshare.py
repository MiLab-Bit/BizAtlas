from __future__ import annotations

from typing import Any


def news_akshare_configured() -> bool:
    try:
        import akshare  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _norm_code(symbol: str) -> str:
    """东财新闻接口用纯数字代码（600519），去掉交易所后缀。"""
    s = symbol.strip().upper()
    if "." in s:
        s = s.split(".", 1)[0]
    return s


def fetch_company_news(symbol: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """经 AKShare（东方财富个股新闻）拉取企业相关新闻舆情。

    返回新闻 dict 列表：title / content / pub_time / source / url / keyword。
    与 providers_tianyancha 的舆情字段解耦，供风险研判的「新闻舆情」维度使用。
    """
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("未安装 akshare，请 pip install akshare") from exc

    code = _norm_code(symbol)
    if not code:
        raise ValueError("symbol 为空")

    try:
        df = ak.stock_news_em(symbol=code)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"AKShare 新闻拉取失败：{exc}") from exc

    if df is None or df.empty:
        raise RuntimeError("AKShare 新闻返回空数据")

    cols = set(df.columns)
    news: list[dict[str, Any]] = []
    for _, row in df.head(limit).iterrows():
        title = str(row.get("新闻标题") or "")
        content = str(row.get("新闻内容") or "")
        pub = str(row.get("发布时间") or "")
        src = str(row.get("文章来源") or "")
        url = str(row.get("新闻链接") or "")
        kw = str(row.get("关键词") or code)
        news.append(
            {
                "keyword": kw,
                "title": title,
                "content": content[:500],
                "pub_time": pub,
                "source": src,
                "url": url,
            }
        )
    if not news:
        raise RuntimeError("AKShare 未解析到新闻条目")
    return news
