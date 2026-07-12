# -*- coding: utf-8 -*-
"""
每日主流程（GitHub Actions 用）
================================
1. 直接呼叫 engine.py 的 run_analysis()，在 GitHub Actions 的機器上就地執行分析
   （不再需要連到 Hugging Face Space，也不需要 Gradio / gradio_client）
2. 用 ai_report.py 把分析結果整理成 JSON，交給 Gemini API 生成中文 AI 晨報
3. 把「Excel 報告」+「AI 晨報」一起用 Resend 寄出

用法：
    python main.py
需要的環境變數（在 GitHub Secrets 設定）：
    RESEND_API_KEY   Resend 的 API Key
    GEMINI_API_KEY   Gemini 的 API Key
    TO_EMAIL         收件信箱（不填則預設 hai1217.chi@gmail.com）
    FINMIND_TOKEN    選填，FinMind 的 Token（沒有就留空，走免費額度）
"""

import base64
import os
import sys
from datetime import datetime

import requests

import engine
import ai_report

RESEND_API_URL = "https://api.resend.com/emails"

# 寄件人地址：
# - 如果你還沒在 Resend 驗證自己的網域，只能用官方的測試地址 onboarding@resend.dev
# - 用 onboarding@resend.dev 寄信時，收件人只能是「當初註冊 Resend 帳號」的那個信箱
FROM_EMAIL = "Stock Report <onboarding@resend.dev>"
TO_EMAIL = os.environ.get("TO_EMAIL", "hai1217.chi@gmail.com")


def run_engine_analysis():
    """直接呼叫 engine.py，沿用模組內建的 SHEET_ID / GID / SHEET_TAB_NAME（權值股）。"""
    if os.environ.get("FINMIND_TOKEN"):
        engine.FINMIND_TOKEN = os.environ["FINMIND_TOKEN"]

    print(f"🚀 開始分析：{engine.SHEET_TAB_NAME}（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）")
    output_file, summary_data, val_data_all = engine.run_analysis(
        gid=engine.GID,
        tab_name=engine.SHEET_TAB_NAME,
        sheet_id=engine.SHEET_ID,
    )
    print(f"✅ 分析完成，共 {len(summary_data)} 檔個股，Excel 已存至：{output_file}")
    return output_file, summary_data


def markdown_to_html(md_text: str) -> str:
    """
    非常簡易的 Markdown → HTML 轉換，只處理 email 晨報會用到的樣式：
    ## 標題、換行段落。不追求完整 Markdown 規格，夠用即可。
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


def send_email_with_report(excel_path: str, ai_briefing_md: str) -> None:
    api_key = os.environ["RESEND_API_KEY"]

    with open(excel_path, "rb") as f:
        encoded_excel = base64.b64encode(f.read()).decode("utf-8")

    briefing_html = markdown_to_html(ai_briefing_md)
    html_body = f"""
    <div style="font-family: -apple-system, Arial, sans-serif; max-width: 640px;">
        <h2>📊 {engine.SHEET_TAB_NAME} AI 晨報</h2>
        <p style="color:#666;">{datetime.now().strftime('%Y-%m-%d')} 自動產生</p>
        <hr>
        {briefing_html}
        <hr>
        <p style="color:#999; font-size: 12px;">
            本郵件由 GitHub Actions 排程自動產生，完整量化數據請見附件 Excel 檔案。
            內容為量化模型輸出，僅供參考，不構成投資建議。
        </p>
    </div>
    """

    payload = {
        "from": FROM_EMAIL,
        "to": [TO_EMAIL],
        "subject": f"{engine.SHEET_TAB_NAME} AI 晨報 {datetime.now().strftime('%Y-%m-%d')}",
        "html": html_body,
        "attachments": [
            {
                "filename": os.path.basename(excel_path),
                "content": encoded_excel,
            }
        ],
    }

    resp = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    print("Resend API 回應狀態碼:", resp.status_code)
    print("Resend API 回應內容:", resp.text)
    resp.raise_for_status()


def main() -> None:
    excel_path, summary_data = run_engine_analysis()

    print("🤖 呼叫 Gemini 生成 AI 晨報...")
    try:
        ai_briefing = ai_report.generate_daily_briefing(summary_data, engine.SHEET_TAB_NAME)
    except Exception as e:
        print(f"⚠️ AI 晨報生成失敗（{e}），改寄送純 Excel 報告。", file=sys.stderr)
        ai_briefing = "（AI 晨報生成失敗，本次僅提供 Excel 數據，請見附件。）"

    print("--- AI 晨報內容預覽 ---")
    print(ai_briefing)
    print("------------------------")

    send_email_with_report(excel_path, ai_briefing)
    print("📧 郵件已寄出。")


if __name__ == "__main__":
    main()
