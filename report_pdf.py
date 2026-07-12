# -*- coding: utf-8 -*-
"""
PDF 晨報模組（V19.4）
======================
把 ai_report.py 生成的 Markdown 晨報文字轉成 PDF。

選用 reportlab 而不是 weasyprint 的原因：
- reportlab 是純 Python 套件，pip install 就能用
- weasyprint 需要系統層的 Pango / Cairo 函式庫，GitHub Actions 預設環境沒有，
  還要另外 apt-get install，較不穩定、容易在排程執行時失敗
- reportlab 內建 CID 字型（MSung-Light，繁體中文 Big5），不需要额外上傳字型檔即可顯示中文
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_FONT_NAME = "MSung-Light"  # reportlab 內建繁體中文 (Big5) CID 字型，不需要額外字型檔
pdfmetrics.registerFont(UnicodeCIDFont(_FONT_NAME))


def _escape(text: str) -> str:
    """reportlab 的 Paragraph 支援類似 HTML 的簡易標記，一般文字要先跳脫特殊符號。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_pdf(md_text: str, output_path: str, title: str = "AI 晨報") -> str:
    """
    把簡易 Markdown（## 標題 + 純文字段落）轉成 PDF，存到 output_path，並回傳該路徑。
    只處理晨報會用到的簡單格式，不追求完整 Markdown 規格。
    """
    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        "TitleCJK", parent=styles["Title"], fontName=_FONT_NAME, fontSize=20, leading=26,
    )
    style_h2 = ParagraphStyle(
        "H2CJK", parent=styles["Heading2"], fontName=_FONT_NAME, fontSize=14, leading=20,
        spaceBefore=14, spaceAfter=6,
    )
    style_body = ParagraphStyle(
        "BodyCJK", parent=styles["BodyText"], fontName=_FONT_NAME, fontSize=11, leading=18,
    )

    story = [Paragraph(_escape(title), style_title), Spacer(1, 0.6 * cm)]

    for raw_line in md_text.strip().split("\n"):
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 0.3 * cm))
        elif line.startswith("## "):
            story.append(Paragraph(_escape(line[3:]), style_h2))
        elif line.startswith("# "):
            story.append(Paragraph(_escape(line[2:]), style_h2))
        else:
            story.append(Paragraph(_escape(line), style_body))

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    doc.build(story)
    return output_path
