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


def _fetch_google_news(keyword: str, max_items: int = 3) -> list:
    """用 Google News RSS 抓標題，不需要 API Key。失敗就回傳空列表。"""
    try:
        resp = requests.get(
            "https://news.google.com/rss/search",
            params={"q": keyword, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
            timeout=15,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")[:max_items]
        return [t for t in (item.findtext("title") for item in items) if t]
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
