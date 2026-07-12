# -*- coding: utf-8 -*-
"""
AI 晨報模組
============
把 engine.run_analysis() 回傳的 summary_data（每檔個股的完整分析結果）
整理成精簡 JSON，交給 Gemini API，請它以「20年經驗基金經理人」的角度
生成一份中文晨報（今日盤勢 / 操作策略 / 風險 / 推薦股票 / 一句總結）。
"""

import json
import os

import requests

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)


def _to_compact_record(d: dict) -> dict:
    """
    只挑晨報真正需要的欄位，避免把整份 summary_data（含大量細節）
    全部丟給 AI，浪費 token 也稀釋重點。
    """
    return {
        "股號": d.get("stock_id"),
        "名稱": d.get("company"),
        "排名": d.get("rank"),
        "收盤價": d.get("current_price"),
        "5日預測動能": d.get("pred_return"),
        "20日預測趨勢": d.get("pred_20d"),
        "AI上漲機率": d.get("up_prob"),
        "歷史波段勝率": d.get("val_hit_rate"),
        "趨勢評級": d.get("trend_stars"),
        "交易信號": d.get("signal"),
        "最終決策": d.get("final_decision"),
        "操作建議": d.get("advice"),
        "黑馬星等": d.get("horse_stars"),
        "AI信心等級": d.get("confidence_stars"),
        "風險模式": d.get("risk_regime"),
        "市場模式": d.get("market_mode"),
        "類股": d.get("sector_tag"),
        "類股熱度": d.get("sector_heat"),
        "Profit Factor": d.get("profit_factor"),
        "Expectancy": d.get("expectancy"),
    }


def build_horse_rank(summary_data: list, top_n: int = 10) -> list:
    """
    黑馬排行榜：依 horse_score 由高到低排序，取前 top_n 檔。
    對齊 engine.write_horse_rank_sheet 的邏輯（同樣是用 horse_score 排序），
    但這裡直接從 summary_data 現有欄位算，不用另外去動 engine.py。
    """
    ranked = sorted(
        summary_data,
        key=lambda d: d.get("horse_score", 0) or 0,
        reverse=True,
    )
    return [
        {
            "股號": d.get("stock_id"),
            "名稱": d.get("company"),
            "HorseScore": d.get("horse_score"),
            "黑馬星等": d.get("horse_stars"),
            "黑馬評分細項": d.get("horse_breakdown_str"),
        }
        for d in ranked[:top_n]
    ]


def build_sector_heat_ranking(summary_data: list) -> list:
    """
    類股資金輪動熱度排行：把每檔個股的 sector_tag / sector_heat 去重後，
    依熱度由高到低排序，呈現「目前資金往哪個類股集中」。
    """
    heat_map = {}
    for d in summary_data:
        tag = d.get("sector_tag")
        heat = d.get("sector_heat")
        if tag and heat is not None and tag not in heat_map:
            heat_map[tag] = heat

    ranked = sorted(heat_map.items(), key=lambda kv: kv[1], reverse=True)
    return [{"類股": tag, "熱度分數(0-100)": heat} for tag, heat in ranked]


def build_prompt(
    summary_data: list,
    tab_name: str,
    market_snapshot: dict | None = None,
    news_headlines: dict | None = None,
) -> str:
    """組出交給 Gemini 的完整 Prompt，固定格式，每天都用同一套。"""
    compact = [_to_compact_record(d) for d in summary_data]
    data_json = json.dumps(compact, ensure_ascii=False, indent=None)

    horse_rank = build_horse_rank(summary_data)
    horse_json = json.dumps(horse_rank, ensure_ascii=False, indent=None)

    sector_heat = build_sector_heat_ranking(summary_data)
    sector_json = json.dumps(sector_heat, ensure_ascii=False, indent=None)

    market_json = json.dumps(market_snapshot or {}, ensure_ascii=False, indent=None)
    news_json = json.dumps(news_headlines or {}, ensure_ascii=False, indent=None)

    prompt = f"""你是一位擁有20年以上經驗的基金經理人，專精台股權值股波段操作。

以下是「今日大盤/美股/國際市場快照」（收盤價與漲跌幅）：

{market_json}

以下是「今日相關新聞標題」（依關鍵字分組，可能不完整，僅供參考方向）：

{news_json}

以下是今天「{tab_name}」量化分析引擎產出的個股數據（JSON 格式，已按綜合排名排序）：

{data_json}

以下是「黑馬排行榜」（依 HorseScore 由高到低排序，分數越高代表爆發力訊號越強，
例如 BB 波動壓縮到位、爆量突破、法人資金進場等，屬於獨立於 AI 分數之外的短線黑馬評分機制）：

{horse_json}

以下是「類股資金輪動熱度排行」（0~100分，分數越高代表資金越集中在該類股，
分數 < 35 通常代表資金退潮警示）：

{sector_json}

請根據以上五份資料，撰寫一份繁體中文晨報，內容包含以下七個部分，請用 Markdown 標題分段：

## 今天盤勢
綜合台股大盤/美股/國際指標（VIX、美元指數、美債殖利率等）與量化引擎的風險模式/市場模式欄位，
簡短描述今天的市場氛圍與國際連動。

## 國際新聞觀察
從新聞標題中挑出 2-3 則可能影響台股或權值股的重點，用自己的話簡短說明（如果新聞資料是空的，
這段可以寫「今日無重大相關新聞」，不要編造內容）。

## 今日操作策略
根據整體訊號分佈（強力買入/買入/觀察/減碼/觀望的比例）與大盤氛圍，給出今天大方向的操作建議。

## 類股輪動觀察
根據「類股資金輪動熱度排行」，指出目前資金集中在哪些類股、哪些類股熱度偏低（資金退潮警示），
對操作策略有什麼影響（例如追高哪些類股風險較高、哪些類股可以留意進場）。

## 黑馬股觀察
從「黑馬排行榜」中，挑出 2-3 檔 HorseScore 較高、值得留意的短線黑馬候選股，說明評分細項透露出的訊號重點
（例如爆量、壓縮蓄勢、法人進場等），並提醒黑馬評分是短線爆發力訊號，不等於 AI 對趨勢方向的信心。

## 風險提醒
指出目前風險模式、有沒有需要特別留意的警示（例如風險模式轉為警戒、高風險或崩盤、國際指標異常，
或某些個股訊號互相矛盾）。

## 推薦股票
從個股數據中選出 3-5 檔最值得留意的個股，可以參考類股熱度與黑馬排行的結果交叉比對，
說明理由（不要只是複製建議欄位，要用自己的話統整重點）。

## 一句總結
用一句話總結今天整體策略方向。

注意：
- 語氣專業、精簡，避免空泛的廢話。
- 這份資料是量化模型的輸出，不是投資建議，你的角色是「協助解讀數據」，不需要加免責聲明章節，但可以在措辭上保持適度保守。
- 新聞資料可能不完整或抓取失敗，若資料為空請誠實說明，不要編造內容。
- 直接輸出內容本身，不要加開場白（例如「好的，以下是今天的晨報」）。
"""
    return prompt


def extract_section(md_text: str, heading: str) -> str:
    """
    從晨報 Markdown 文字中，擷取指定 "## 標題" 底下的內容，直到下一個 "##" 或結尾為止。
    給 dashboard.py / line_notify.py 共用，避免重複解析邏輯。
    """
    lines = md_text.split("\n")
    capture = False
    collected = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if capture:
                break
            if stripped[3:].strip() == heading:
                capture = True
                continue
        elif capture:
            collected.append(line)
    return "\n".join(collected).strip()


def markdown_to_html(md_text: str) -> str:
    """
    非常簡易的 Markdown → HTML 轉換，只處理晨報會用到的樣式（## 標題、純文字段落）。
    main.py（Email 內文）跟 dashboard.py（網頁卡片）共用這一份，避免各自維護不同邏輯。
    """
    lines = md_text.strip().split("\n")
    html_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            html_lines.append(f"<h3>{stripped[3:]}</h3>")
        elif stripped.startswith("# "):
            html_lines.append(f"<h2>{stripped[2:]}</h2>")
        elif stripped == "":
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p>{stripped}</p>")
    return "\n".join(html_lines)


def call_gemini(prompt: str, api_key: str) -> str:
    """呼叫 Gemini API，回傳生成的文字內容。"""
    resp = requests.post(
        GEMINI_URL,
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Gemini 回傳格式異常，無法解析內容: {data}") from e


def generate_daily_briefing(
    summary_data: list,
    tab_name: str,
    market_snapshot: dict | None = None,
    news_headlines: dict | None = None,
) -> str:
    """對外主要進入點：輸入 summary_data + 類股名稱 + 市場資訊，回傳晨報 Markdown 文字。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("找不到環境變數 GEMINI_API_KEY，請確認 GitHub Secrets 有設定。")

    if not summary_data:
        return "⚠️ 今日沒有任何個股通過篩選，無法生成晨報。"

    prompt = build_prompt(summary_data, tab_name, market_snapshot, news_headlines)
    return call_gemini(prompt, api_key)
