# -*- coding: utf-8 -*-
"""
每日主流程（GitHub Actions 用）
================================
1. 抓取市場快照 + 新聞（market.py）
2. 針對 CATEGORIES 清單裡的每個類股，各自呼叫 engine.run_analysis()
   （預設只有「權值股」，如果要一次分析多個類股，把下面 CATEGORIES 裡的註解取消即可）
3. 每個類股都用 ai_report.py 生成 AI 晨報、report_pdf.py 轉成 PDF
4. 全部跑完後：
   - 用 Resend 把「所有類股的 Excel + PDF」合併成一封信寄出
   - 用 LINE Messaging API 廣播精簡摘要
   - 用 dashboard.py 更新 GitHub Pages 網頁儀表板

用法：
    python main.py
需要的環境變數（在 GitHub Secrets 設定）：
    RESEND_API_KEY              Resend 的 API Key
    GEMINI_API_KEY              Gemini 的 API Key
    TO_EMAIL                    收件信箱（不填則預設 hai1217.chi@gmail.com）
    FINMIND_TOKEN                選填，FinMind 的 Token
    LINE_CHANNEL_ACCESS_TOKEN    選填，LINE Messaging API 的 Channel access token
                                 （沒有就不會發送 LINE 通知，其他功能不受影響）
"""

import base64
import os
import sys
from datetime import datetime

import requests

import engine
import ai_report
import market
import report_pdf
import dashboard

# ------------------------------------------------------------------
# 要跑哪些類股清單（對應 app.py 裡 CATEGORY_GID_MAP 的 gid）
# 預設只跑「權值股」；想一次跑多個類股，把下面對應那行的 "#" 拿掉即可，
# 但要注意：每多一個類股，總執行時間會等比例拉長（每個類股都要重新訓練模型）。
# ------------------------------------------------------------------
CATEGORIES = {
    "權值股": "630045424",
    # "面板股": "1749860219",
    # "AI概念股": "0",
    # "國防自主概念": "2037567856",
    # "低軌衛星概念股": "1594256368",
    # "無人機概念股": "327999020",
}

RESEND_API_URL = "https://api.resend.com/emails"

# 寄件人地址：
# - 如果你還沒在 Resend 驗證自己的網域，只能用官方的測試地址 onboarding@resend.dev
# - 用 onboarding@resend.dev 寄信時，收件人只能是「當初註冊 Resend 帳號」的那個信箱
FROM_EMAIL = "Stock Report <onboarding@resend.dev>"
TO_EMAIL = os.environ.get("TO_EMAIL", "hai1217.chi@gmail.com")


def fetch_market_context() -> tuple:
    """抓市場快照 + 新聞，任何一步失敗都不能讓整個流程掛掉。"""
    print("🌍 抓取大盤/美股/國際市場快照...")
    try:
        snapshot = market.fetch_market_snapshot()
        print(f"   完成，共 {sum(len(v) for v in snapshot.values())} 項指標")
    except Exception as e:
        print(f"   ⚠️ 市場快照抓取失敗（{e}），晨報將略過此部分")
        snapshot = {}

    print("📰 抓取相關新聞標題...")
    try:
        news = market.fetch_news_headlines()
        print(f"   完成，共 {len(news)} 組關鍵字有結果")
    except Exception as e:
        print(f"   ⚠️ 新聞抓取失敗（{e}），晨報將略過此部分")
        news = {}

    return snapshot, news


def run_one_category(tab_name: str, gid: str, market_snapshot: dict, news_headlines: dict) -> dict:
    """跑完一個類股的完整流程（分析 → AI 晨報 → PDF），回傳結果 dict 供後續彙整。"""
    if os.environ.get("FINMIND_TOKEN"):
        engine.FINMIND_TOKEN = os.environ["FINMIND_TOKEN"]

    print(f"\n🚀 開始分析：{tab_name}（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）")
    output_file, summary_data, val_data_all = engine.run_analysis(
        gid=gid,
        tab_name=tab_name,
        sheet_id=engine.SHEET_ID,
    )
    print(f"✅ {tab_name} 分析完成，共 {len(summary_data)} 檔個股，Excel 已存至：{output_file}")

    print(f"🤖 呼叫 Gemini 生成 {tab_name} AI 晨報...")
    try:
        ai_briefing = ai_report.generate_daily_briefing(
            summary_data, tab_name, market_snapshot, news_headlines
        )
    except Exception as e:
        print(f"⚠️ AI 晨報生成失敗（{e}），改用純數據摘要。", file=sys.stderr)
        ai_briefing = "（AI 晨報生成失敗，本次僅提供 Excel 數據，請見附件。）"

    pdf_path = None
    try:
        pdf_path = report_pdf.markdown_to_pdf(
            ai_briefing,
            output_path=f"./AI晨報_{tab_name}_{datetime.now().strftime('%Y%m%d')}.pdf",
            title=f"{tab_name} AI 晨報 {datetime.now().strftime('%Y-%m-%d')}",
        )
        print(f"📄 {tab_name} PDF 晨報已產生：{pdf_path}")
    except Exception as e:
        print(f"⚠️ PDF 產生失敗（{e}），本次僅有 Excel + 信件內文。", file=sys.stderr)

    return {
        "tab_name": tab_name,
        "excel_path": output_file,
        "pdf_path": pdf_path,
        "ai_briefing": ai_briefing,
        "summary_data": summary_data,
    }


def send_email_with_report(category_results: list) -> None:
    api_key = os.environ["RESEND_API_KEY"]
    today = datetime.now().strftime("%Y-%m-%d")

    attachments = []
    sections_html = []

    for r in category_results:
        with open(r["excel_path"], "rb") as f:
            encoded_excel = base64.b64encode(f.read()).decode("utf-8")
        attachments.append({"filename": os.path.basename(r["excel_path"]), "content": encoded_excel})

        if r.get("pdf_path") and os.path.exists(r["pdf_path"]):
            with open(r["pdf_path"], "rb") as f:
                encoded_pdf = base64.b64encode(f.read()).decode("utf-8")
            attachments.append({"filename": os.path.basename(r["pdf_path"]), "content": encoded_pdf})

        sections_html.append(f"<h2>📌 {r['tab_name']}</h2>")
        sections_html.append(ai_report.markdown_to_html(r["ai_briefing"]))
        sections_html.append("<hr>")

    category_names = "、".join(r["tab_name"] for r in category_results)
    html_body = f"""
    <div style="font-family: -apple-system, Arial, sans-serif; max-width: 640px;">
        <h1>📊 AI 晨報：{category_names}</h1>
        <p style="color:#666;">{today} 自動產生</p>
        <hr>
        {''.join(sections_html)}
        <p style="color:#999; font-size: 12px;">
            本郵件由 GitHub Actions 排程自動產生，完整量化數據請見附件 Excel 檔案，
            各類股晨報 PDF 版本也一併附上。內容為量化模型輸出，僅供參考，不構成投資建議。
        </p>
    </div>
    """

    payload = {
        "from": FROM_EMAIL,
        "to": [TO_EMAIL],
        "subject": f"AI 晨報 {today}：{category_names}",
        "html": html_body,
        "attachments": attachments,
    }

    resp = requests.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    print("Resend API 回應狀態碼:", resp.status_code)
    print("Resend API 回應內容:", resp.text)
    resp.raise_for_status()


def send_line_digest(category_results: list) -> None:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        print("ℹ️ 未設定 LINE_CHANNEL_ACCESS_TOKEN，略過 LINE 通知。")
        return

    import line_notify

    try:
        message = line_notify.build_digest_message(category_results)
        line_notify.send_line_broadcast(message, token)
        print("📱 LINE 通知已發送。")
    except Exception as e:
        print(f"⚠️ LINE 通知發送失敗（{e}），不影響其他流程。", file=sys.stderr)


def update_dashboard_safe(category_results: list, market_snapshot: dict) -> None:
    try:
        dashboard.update_dashboard(category_results, market_snapshot)
    except Exception as e:
        print(f"⚠️ Dashboard 更新失敗（{e}），不影響其他流程。", file=sys.stderr)


def main() -> None:
    market_snapshot, news_headlines = fetch_market_context()

    category_results = []
    for tab_name, gid in CATEGORIES.items():
        result = run_one_category(tab_name, gid, market_snapshot, news_headlines)
        category_results.append(result)
        print(f"--- {tab_name} AI 晨報內容預覽 ---")
        print(result["ai_briefing"])
        print("------------------------")

    send_email_with_report(category_results)
    print("📧 郵件已寄出。")

    send_line_digest(category_results)
    update_dashboard_safe(category_results, market_snapshot)


if __name__ == "__main__":
    main()
