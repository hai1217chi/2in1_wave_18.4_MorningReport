# -*- coding: utf-8 -*-
"""
LINE 通知模組
==============
⚠️ 注意：LINE Notify 已於 2025 年 3 月 31 日正式停止服務（官方公告），
本模組改用官方建議的替代方案 —— LINE Messaging API 的「廣播訊息」功能。

事前準備（一次性）：
1. 到 https://developers.line.biz/console/ 建立 Provider + Messaging API Channel
2. 在 Channel 設定頁面，取得「Channel access token（長期）」
3. 用手機 LINE 掃描 Channel 頁面的 QR Code，把這個官方帳號加為好友
   （廣播訊息只會送給「已加此官方帳號為好友」的人，所以這一步必做）
4. 把 Channel access token 存進 GitHub Secrets，命名為 LINE_CHANNEL_ACCESS_TOKEN

免費額度：每月 200 則訊息，一天一次的晨報摘要完全用不完。
"""

import requests

LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

# LINE 文字訊息單則長度上限，超過要截斷，避免 API 回傳錯誤
_MAX_LEN = 4900


def send_line_broadcast(text: str, channel_access_token: str) -> None:
    """用 LINE 官方帳號廣播一則文字訊息給所有好友（適合個人使用：好友只有你自己）。"""
    if len(text) > _MAX_LEN:
        text = text[:_MAX_LEN - 20] + "\n...(內容過長，已截斷)"

    resp = requests.post(
        LINE_BROADCAST_URL,
        headers={
            "Authorization": f"Bearer {channel_access_token}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"type": "text", "text": text}]},
        timeout=30,
    )
    print("LINE Broadcast 回應狀態碼:", resp.status_code)
    if resp.text:
        print("LINE Broadcast 回應內容:", resp.text)
    resp.raise_for_status()


def build_digest_message(category_results: list) -> str:
    """
    組出給 LINE 的精簡摘要文字（不像 Email 那麼長，LINE 適合快速看重點）。
    category_results: main.py 裡收集的每個類股分析結果列表。
    """
    import ai_report  # 延遲 import，避免循環引用疑慮

    lines = ["📊 每日 AI 晨報摘要", ""]
    for r in category_results:
        tab_name = r["tab_name"]
        briefing = r.get("ai_briefing", "")
        one_liner = ai_report.extract_section(briefing, "一句總結") or "（本次無總結內容）"
        lines.append(f"【{tab_name}】")
        lines.append(one_liner)
        lines.append("")

    lines.append("完整晨報請見 Email 附件（Excel + PDF）。")
    return "\n".join(lines).strip()
