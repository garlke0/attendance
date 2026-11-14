"""Attendance PDF in Arabic.

PDF libraries draw letters one by one, left to right. Arabic needs two fixes:
- arabic_reshaper joins the letters into their connected shapes;
- python-bidi puts the text in right-to-left visual order.
"""

import io
import re
from pathlib import Path
from urllib.parse import quote

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

FONT_DIR = Path(__file__).parent / "fonts"
FONT = "NotoNaskh"
FONT_BOLD = "NotoNaskh-Bold"
pdfmetrics.registerFont(TTFont(FONT, str(FONT_DIR / "NotoNaskhArabic-Regular.ttf")))
pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "NotoNaskhArabic-Bold.ttf")))

HEADERS = ["الاسم", "الرقم الجامعي", "التخصص", "الحالة"]
STATUS_PRESENT = "حاضر"


def ar(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text or ""))


def build_pdf(lecture_name: str, lecture_date: str, lecture_time: str | None,
              rows: list[tuple[str, str, str]]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
        title=lecture_name,
    )

    # Header: lecture name, date, time (only if the doctor entered it)
    info = [[ar(lecture_name), ar("المحاضرة:")], [lecture_date, ar("التاريخ:")]]
    if lecture_time:
        info.append([ar(lecture_time), ar("الوقت:")])
    info_table = Table(info, colWidths=[140 * mm, 40 * mm], hAlign="RIGHT")
    info_table.setStyle(TableStyle([
        ("FONT", (0, 0), (0, -1), FONT, 12),
        ("FONT", (1, 0), (1, -1), FONT_BOLD, 12),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
    ]))

    # Right-to-left: the first column (name) is drawn on the right.
    header = [ar(h) for h in reversed(HEADERS)]
    body = [
        [ar(STATUS_PRESENT), ar(major), student_id, ar(name)]
        for name, student_id, major in rows
    ]
    widths = [22 * mm, 55 * mm, 38 * mm, 65 * mm]
    table = Table([header] + body, colWidths=widths, repeatRows=1, hAlign="CENTER")
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), FONT_BOLD, 11),
        ("FONT", (0, 1), (-1, -1), FONT, 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))

    doc.build([info_table, Spacer(1, 8 * mm), table])
    return buf.getvalue()


def pdf_filename(lecture_name: str, lecture_date: str) -> str:
    """'<lecture name> <date>.pdf' with characters Windows forbids removed."""
    safe = re.sub(r'[\\/:*?"<>|\r\n]+', " ", lecture_name)
    safe = re.sub(r"\s+", " ", safe).strip() or "attendance"
    return f"{safe} {lecture_date}.pdf"


def content_disposition(filename: str) -> str:
    # ASCII fallback for old browsers + the real (Arabic-capable) name.
    fallback = filename.encode("ascii", "ignore").decode().strip() or "attendance.pdf"
    if not fallback.lower().endswith(".pdf"):
        fallback = "attendance.pdf"
    fallback = fallback.replace('"', "")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"
