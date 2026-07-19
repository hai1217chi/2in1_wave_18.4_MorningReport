# -*- coding: utf-8 -*-
"""
市場資訊模組（V19.2）
======================
在 engine.run_analysis() 分析權值股「之前」，額外抓取更廣泛的市場背景資訊：
- 台股：加權指數、櫃買指數
- 美股：道瓊、那斯達克、S&P500、費半 SOX
- 國際：VIX、美元指數 DXY、美債10年殖利率、黃金、原油
- 新聞：Fed / NVIDIA / 台積電 ADR / OpenAI / Google AI / 中國經濟 相關頭條

這些資訊會一起塞進 ai_report.build_prompt()，讓晨報有更完整的市場背景可以參考。
全部都是公開資料源（yfinance + Google News RSS），不需要額外的 API Key。
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
import yfinance as yf

TW_TICKERS = {"加權指數": "^TWII", "櫃買指數": "^TWOII"}
US_TICKERS = {"道瓊": "^DJI", "那斯達克": "^IXIC", "S&P500": "^GSPC", "費半SOX": "^SOX"}
GLOBAL_TICKERS = {
    "VIX恐慌指數": "^VIX",
    "美元指數DXY": "DX-Y.NYB",
    "美債10年殖利率": "^TNX",
    "黃金": "GC=F",
    "原油WTI": "CL=F",
}

NEWS_KEYWORDS = ["Fed 利率", "NVIDIA", "台積電 ADR", "OpenAI", "Google AI", "中國 經濟"]


def _fetch_quote_change(ticker: str) -> dict | None:
    """抓最近兩個交易日的收盤價，算出漲跌幅。任何一步失敗就回傳 None，不中斷整體流程。"""
    try:
        data = yf.Ticker(ticker).history(period="5d")
        if len(data) < 2:
            return None
        close = data["Close"]
        last, prev = float(close.iloc[-1]), float(close.iloc[-2])
        return {"收盤": round(last, 2), "漲跌%": round((last / prev - 1) * 100, 2)}
    except Exception:
        return None


def fetch_market_snapshot() -> dict:
    """回傳 {"台股": {...}, "美股": {...}, "國際": {...}}，任何單一指標失敗都不影響其他指標。"""
    snapshot = {"台股": {}, "美股": {}, "國際": {}}
    for name, ticker in TW_TICKERS.items():
        q = _fetch_quote_change(ticker)
        if q:
            snapshot["台股"][name] = q
    for name, ticker in US_TICKERS.items():
        q = _fetch_quote_change(ticker)
        if q:
            snapshot["美股"][name] = q
    for name, ticker in GLOBAL_TICKERS.items():
        q = _fetch_quote_change(ticker)
        if q:
            snapshot["國際"][name] = q
    return snapshot


# 新聞抓取只保留最近 N 小時內的內容，避免抓到好幾天前的舊新聞
_NEWS_MAX_AGE_HOURS = 24


def _parse_pubdate(item: ET.Element):
    """解析 RSS <pubDate>，失敗回傳 None（該筆新聞就不會被時間過濾掉，只是排序時排最後）。"""
    pub_date_str = item.findtext("pubDate")
    if not pub_date_str:
        return None
    try:
        dt = parsedate_to_datetime(pub_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _fetch_google_news(keyword: str, max_items: int = 3) -> list:
    """
    用 Google News RSS 抓標題，不需要 API Key。
    在查詢字串加上 "when:2d"（Google News 的時間限定語法，限定近 48 小時），
    並且在程式端再用 <pubDate> 二次過濾（只留 _NEWS_MAX_AGE_HOURS 小時內）+ 依時間新到舊排序，
    避免 Google News 有時候把舊聞排在搜尋結果前面的問題。失敗就回傳空列表。
    """
    try:
        resp = requests.get(
            "https://news.google.com/rss/search",
            params={"q": f"{keyword} when:2d", "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
            timeout=15,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=_NEWS_MAX_AGE_HOURS)

        candidates = []
        for item in root.findall(".//item"):
            title = item.findtext("title")
            if not title:
                continue
            pub_date = _parse_pubdate(item)
            if pub_date and pub_date < cutoff:
                continue  # 太舊的新聞直接丟掉
            candidates.append((pub_date or cutoff, title))

        # 依時間新到舊排序，最新的排最前面
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [title for _, title in candidates[:max_items]]
    except Exception:
        return []


def fetch_news_headlines() -> dict:
    """回傳 {"Fed 利率": ["標題1", "標題2", ...], "NVIDIA": [...], ...}"""
    news = {}
    for kw in NEWS_KEYWORDS:
        headlines = _fetch_google_news(kw)
        if headlines:
            news[kw] = headlines
    return news
