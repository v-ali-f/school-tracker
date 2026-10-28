"""Stable nine-column PDF layout for a journal page."""

from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


FONT_NAME = "SafetyJournalSans"
FONT_BOLD = "SafetyJournalSansBold"


def _register_fonts():
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    regular = next((path for path in (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ) if Path(path).exists()), None)
    bold = next((path for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ) if Path(path).exists()), None)
    if not regular:
        raise RuntimeError("На сервере не найден шрифт с поддержкой кириллицы для журнала.")
    pdfmetrics.registerFont(TTFont(FONT_NAME, regular))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, bold or regular))


def _paragraph(value, style):
    return Paragraph(escape(str(value or "")).replace("\n", "<br/>"), style)


def _instruction_label(number, title):
    number = (number or "").strip()
    title = (title or "").strip()
    if title.casefold().startswith(number.casefold()) and number:
        title = title[len(number):].lstrip(" -—:№")
    return f"{number} — {title}" if title else number


def build_journal_pdf(page, participants):
    """Return immutable PDF bytes from already frozen page and participant data."""
    _register_fonts()
    stream = BytesIO()
    doc = SimpleDocTemplate(
        stream, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
        title=f"Журнал инструктажа {page.number}",
        author=page.instructor_name_snapshot,
    )
    normal = ParagraphStyle("SafetyNormal", fontName=FONT_NAME, fontSize=7.1, leading=9, alignment=TA_LEFT)
    heading = ParagraphStyle("SafetyHeading", parent=normal, fontName=FONT_BOLD, fontSize=10, leading=12, alignment=TA_CENTER)
    subheading = ParagraphStyle("SafetySubheading", parent=normal, fontSize=8, leading=10, alignment=TA_CENTER)
    table_head = ParagraphStyle("SafetyTableHead", parent=normal, fontName=FONT_BOLD, fontSize=6.5, leading=8, alignment=TA_CENTER)
    table_cell = ParagraphStyle("SafetyTableCell", parent=normal, fontSize=6.7, leading=8)
    centered = ParagraphStyle("SafetyCentered", parent=table_cell, alignment=TA_CENTER)

    header = [
        "№", "Фамилия, имя, отчество инструктируемого", "Дата рождения",
        "Класс", "Дата инструктажа", "Номер инструкции и краткое содержание",
        "Подпись инструктируемого", "ФИО проводившего", "Подпись проводившего",
    ]
    rows = [[_paragraph(value, table_head) for value in header]]
    for person in participants:
        rows.append([
            _paragraph(person.sequence, centered),
            _paragraph(person.full_name_snapshot, table_cell),
            _paragraph(person.birth_date_snapshot.strftime("%d.%m.%Y"), centered),
            _paragraph(person.class_name_snapshot, centered),
            "",  # The actual briefing date is entered on paper by hand.
            _paragraph(_instruction_label(page.instruction_number_snapshot, page.instruction_summary_snapshot), table_cell),
            "",  # Signatures are placed on the printed sheet by hand.
            _paragraph(page.instructor_name_snapshot, centered),
            "",
        ])
    # ReportLab's document frame adds 6 pt padding on each side.
    available_width = doc.width - 12
    proportions = [0.035, 0.17, 0.09, 0.055, 0.075, 0.25, 0.11, 0.135, 0.08]
    widths = [available_width * part for part in proportions]
    table = LongTable(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
    ]))
    trip = page.trip_snapshot or {}
    journal_title = "Страница журнала инструктажа обучающихся при выезде" if page.kind == "trip" else "Страница журнала регистрации инструктажа обучающихся"
    story = [
        _paragraph(page.organization_name_snapshot, heading),
        Spacer(1, 3 * mm),
        _paragraph(journal_title, heading),
        _paragraph(
            f"№ {page.number} · группа {page.group_label}",
            subheading,
        ),
        _paragraph(
            f"Инструкция: {_instruction_label(page.instruction_number_snapshot, page.instruction_title_snapshot)}",
            subheading,
        ),
        _paragraph(
            f"Вид инструктажа: {page.briefing_kind_snapshot or page.instruction_version.instruction.briefing_kind}",
            subheading,
        ),
        _paragraph(f"{'Мероприятие' if page.kind == 'trip' else 'Предмет'}: {getattr(page, 'subject_snapshot', None) or (page.instruction_version.instruction.category if page.instruction_version else '')}", subheading),
        _paragraph(f"Проводивший инструктаж: {page.instructor_name_snapshot}", subheading),
    ]
    if trip:
        if trip.get("order_number"):
            order_label = f"Приказ № {trip['order_number']}"
            if trip.get("order_date"):
                order_label += f" от {trip['order_date']}"
            if trip.get("order_title"):
                order_label += f" · {trip['order_title']}"
            story.append(_paragraph(order_label, subheading))
        story.append(_paragraph(
            f"{trip['trip_kind']} · {trip['destination']} · дата выезда {trip['trip_date']}",
            subheading,
        ))
    if page.header_note_snapshot:
        story.append(_paragraph(page.header_note_snapshot, subheading))
    story.extend([Spacer(1, 4 * mm), table])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT_NAME, 7)
        canvas.drawString(12 * mm, 7 * mm, f"Страница журнала № {page.number}")
        canvas.drawCentredString(landscape(A4)[0] / 2, 7 * mm, page.instructor_name_snapshot)
        canvas.drawRightString(landscape(A4)[0] - 12 * mm, 7 * mm, f"Лист {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
