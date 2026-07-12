# -*- coding: utf-8 -*-
"""
Dashboard 模組（V20 雛形）
===========================
把每次執行的分析結果，整理成一個簡單的靜態網頁，交給 GitHub Pages 展示。
不需要資料庫、不需要後端伺服器，純粹是「每天執行完，重新產生 HTML 檔案」，
GitHub Actions 執行完 main.py 後會把 docs/ 資料夾 commit 回 repo，
GitHub Pages 設定成從 /docs 發佈，就能看到隨每日執行自動更新的網頁。

網頁結構：
    docs/
    ├── index.html              ← 首頁，顯示「今天」每個類股的卡片
    └── reports/
        ├── 2026-07-13.html     ← 當天的完整存檔頁（含所有類股）
        └── 2026-07-12.html     ← 之前每一天的存檔，index.html 下方會列出連結
"""

import os
from collections import Counter
from datetime import datetime

import ai_report

DOCS_DIR = "docs"
REPORTS_DIR = os.path.join(DOCS_DIR, "reports")

_CARD_CSS = """
body { font-family: -apple-system, "PingFang TC", "Microsoft JhengHei", Arial, sans-serif;
       background:#f4f5f7; margin:0; padding:24px; color:#222; }
h1 { font-size:22px; }
.date { color:#888; margin-bottom:20px; }
.grid { display:flex; flex-wrap:wrap; gap:16px; }
.card { background:#fff; border-radius:12px; padding:18px 20px; width:320px;
        box-shadow:0 1px 4px rgba(0,0,0,0.08); }
.card h2 { margin:0 0 8px 0; font-size:18px; }
.tag { display:inline-block; padding:2px 8px; border-radius:6px; font-size:12px;
       background:#eef2ff; color:#3949ab; margin-right:6px; }
.risk-NORMAL { background:#e8f5e9; color:#2e7d32; }
.risk-CAUTION { background:#fff8e1; color:#f9a825; }
.risk-HIGH_RISK { background:#ffebee; color:#c62828; }
.risk-CRASH { background:#efebe9; color:#4e342e; }
.signals { margin:10px 0; font-size:13px; color:#444; }
.stocks { margin:10px 0; font-size:14px; }
.summary { margin-top:10px; padding-top:10px; border-top:1px dashed #ddd;
           font-size:13px; color:#555; line-height:1.5; }
.archive { margin-top:30px; font-size:13px; }
.archive a { color:#3949ab; text-decoration:none; margin-right:10px; }
.disclaimer { margin-top:24px; font-size:12px; color:#999; }
"""


def _signal_counts(summary_data: list) -> dict:
    return dict(Counter(d.get("signal", "未知") for d in summary_data))


def _top_picks(summary_data: list, n: int = 3) -> list:
    """優先取 signal 為 買入/強力買入 的個股，依 rank 排序；不足 n 檔就用整體 rank 補齊。"""
    buy_like = [d for d in summary_data if "買入" in (d.get("signal") or "")]
    buy_like_sorted = sorted(buy_like, key=lambda d: d.get("rank", 999))
    picks = buy_like_sorted[:n]
    if len(picks) < n:
        rest = sorted(summary_data, key=lambda d: d.get("rank", 999))
        for d in rest:
            if d not in picks:
                picks.append(d)
            if len(picks) >= n:
                break
    return picks[:n]


def _render_card(result: dict) -> str:
    tab_name = result["tab_name"]
    summary_data = result["summary_data"]
    briefing = result.get("ai_briefing", "")

    risk_regime = summary_data[0].get("risk_regime", "NORMAL") if summary_data else "NORMAL"
    market_mode = summary_data[0].get("market_mode", "N/A") if summary_data else "N/A"

    counts = _signal_counts(summary_data)
    signal_line = " ".join(f"{k}:{v}檔" for k, v in counts.items())

    picks = _top_picks(summary_data)
    picks_html = "、".join(f"{d.get('stock_id')} {d.get('company')}" for d in picks)

    one_liner = ai_report.extract_section(briefing, "一句總結") or "（無總結）"

    return f"""
    <div class="card">
        <h2>{tab_name}</h2>
        <span class="tag risk-{risk_regime}">風險模式：{risk_regime}</span>
        <span class="tag">市場模式：{market_mode}</span>
        <div class="signals">訊號分布：{signal_line}</div>
        <div class="stocks"><b>推薦關注：</b>{picks_html}</div>
        <div class="summary">{one_liner}</div>
    </div>
    """


def _render_page(category_results: list, date_str: str, archive_links_html: str = "") -> str:
    cards_html = "\n".join(_render_card(r) for r in category_results)
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>每日 AI 晨報 Dashboard - {date_str}</title>
<style>{_CARD_CSS}</style>
</head>
<body>
<h1>📊 每日 AI 晨報 Dashboard</h1>
<div class="date">{date_str} 自動產生</div>
<div class="grid">
{cards_html}
</div>
<div class="archive">
    <b>歷史紀錄：</b>{archive_links_html}
</div>
<div class="disclaimer">內容為量化模型 + AI 輸出，僅供參考，不構成投資建議。</div>
</body>
</html>
"""


def update_dashboard(category_results: list) -> None:
    """
    主要進入點：輸入 main.py 收集好的 category_results
    （每個元素需要有 tab_name / summary_data / ai_briefing），
    產生今天的存檔頁 + 更新首頁 index.html。
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")

    # 先列出既有的歷史存檔（不含今天），組出「歷史紀錄」連結列
    existing_dates = sorted(
        (f[:-5] for f in os.listdir(REPORTS_DIR) if f.endswith(".html") and f[:-5] != date_str),
        reverse=True,
    )
    archive_links = "".join(
        f'<a href="reports/{d}.html">{d}</a>' for d in existing_dates[:14]
    )

    page_html = _render_page(category_results, date_str, archive_links)

    # 寫入今天的存檔頁
    with open(os.path.join(REPORTS_DIR, f"{date_str}.html"), "w", encoding="utf-8") as f:
        f.write(page_html)

    # 更新首頁（跟今天的存檔頁內容一樣，但路徑在 docs/index.html，GitHub Pages 預設進入點）
    # 首頁裡的歷史連結需要補上「今天」自己也算一筆歷史（給明天之後的頁面連過來用）
    index_archive_links = f'<a href="reports/{date_str}.html">{date_str}</a>' + archive_links
    index_html = _render_page(category_results, date_str, index_archive_links)
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"🖥️ Dashboard 已更新：{DOCS_DIR}/index.html, {REPORTS_DIR}/{date_str}.html")
