"""Paper journal custody, corrected blank PDF, scans and access."""

from io import BytesIO
import re

import pdfplumber

from app.core.extensions import db
from app.models import SafetyInstructionVersion, SafetyJournalPage, SafetyJournalPaperRecord, SafetyJournalPaperScan
from app.services.safety_journal_pdf import build_journal_pdf
from test_safety_journals import _instruction_form, _setup


def _page(app, client, login, ids):
    login(ids["officer"])
    assert client.post("/safety/instructions/new", data=_instruction_form(ids["today"]), content_type="multipart/form-data").status_code == 302
    with app.app_context():
        version_id = SafetyInstructionVersion.query.one().id
    login(ids["teacher"])
    draft_url = client.post("/safety/journals/new").headers["Location"]
    assert client.post(f"{draft_url}/settings", data={
        "instructed_on": ids["today"].isoformat(), "briefing_at": f'{ids["today"].isoformat()}T10:30', "grade": "5",
        "instruction_version_id": version_id, "class_ids": [ids["class"]],
    }).status_code == 302
    preview = client.get(f"{draft_url}/preview").get_data(as_text=True)
    digest = re.search(r'name="preview_digest" value="([^"]+)"', preview).group(1)
    return client.post(f"{draft_url}/generate", data={"preview_digest": digest}).headers["Location"].split("?", 1)[0]


def test_paper_review_filing_scans_and_corrected_pdf(app, client, make_user, login, tmp_path):
    ids = _setup(app, make_user, tmp_path)
    page_url = _page(app, client, login, ids)
    with app.app_context():
        page = SafetyJournalPage.query.one()
        page_id = page.id
        original_hash = page.revisions[0].pdf_sha256
        pdf_content = build_journal_pdf(page, page.participants)
        with pdfplumber.open(BytesIO(pdf_content)) as document:
            text = "\n".join(sheet.extract_text() or "" for sheet in document.pages)
        assert ids["today"].strftime("%d.%m.%Y") not in text
        assert "ознакомлен" not in text
    login(ids["officer"])
    assert client.post(f"{page_url}/paper/check", data={"dates_checked": "on", "signatures_checked": "on", "roster_checked": "on"}).status_code == 409
    login(ids["teacher"])
    assert client.post(f"{page_url}/pdf/reissue").status_code == 302
    with app.app_context():
        page = db.session.get(SafetyJournalPage, page_id)
        assert len(page.revisions) == 2 and page.revisions[0].pdf_sha256 == original_hash
    detail_html = client.get(page_url).get_data(as_text=True)
    assert "/pdf/revisions/" in detail_html
    assert client.post(f"{page_url}/printed").status_code == 302
    login(ids["officer"])
    assert client.post(f"{page_url}/paper/check", data={"dates_checked": "on"}).status_code == 302
    with app.app_context():
        assert SafetyJournalPaperRecord.query.count() == 0
    assert client.post(f"{page_url}/paper/issue", data={"issue_note": "Нет даты в одной строке"}).status_code == 302
    login(ids["teacher"])
    assert client.post(f"{page_url}/pdf/reissue").status_code == 302
    assert client.post(f"{page_url}/printed").status_code == 302
    login(ids["officer"])
    assert client.post(f"{page_url}/paper/check", data={"dates_checked": "on", "signatures_checked": "on", "roster_checked": "on"}).status_code == 302
    assert client.post(f"{page_url}/paper/scans", data={"scan": (BytesIO(b"not a PDF"), "scan.pdf")}, content_type="multipart/form-data").status_code == 302
    with app.app_context():
        assert SafetyJournalPaperScan.query.count() == 0
    first_scan = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    assert client.post(f"{page_url}/paper/scans", data={"scan": (BytesIO(first_scan), "paper.pdf")}, content_type="multipart/form-data").status_code == 302
    assert client.post(f"{page_url}/paper/scans", data={"scan": (BytesIO(first_scan + b"%%EOF\n"), "paper-2.pdf")}, content_type="multipart/form-data").status_code == 302
    assert client.post(f"{page_url}/paper/file", data={"binder_ref": "Папка ОТ, 2026", "sheet_ref": "15"}).status_code == 302
    assert client.post(f"{page_url}/paper/issue", data={"issue_note": "Позднее замечание"}).status_code == 409
    with app.app_context():
        paper = db.session.get(SafetyJournalPaperRecord, page_id)
        assert paper.checked_at and paper.filed_at and paper.binder_ref == "Папка ОТ, 2026"
        assert [scan.version_number for scan in SafetyJournalPaperScan.query.order_by(SafetyJournalPaperScan.version_number)] == [1, 2]
        scan_id = SafetyJournalPaperScan.query.order_by(SafetyJournalPaperScan.id).first().id
    scan_url = f"{page_url}/paper/scans/{scan_id}"
    assert client.get(scan_url).data == first_scan
    assert client.post(f"{page_url}/pdf/reissue").status_code == 409
    login(ids["other"])
    assert client.get(scan_url).status_code == 403
    assert client.post(f"{page_url}/paper/file", data={"binder_ref": "Другая папка"}).status_code == 403
    login(ids["teacher"])
    assert client.get(scan_url).data == first_scan
