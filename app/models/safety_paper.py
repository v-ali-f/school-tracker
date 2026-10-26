"""Physical journal custody and immutable scan versions."""

from app.core.extensions import db
from app.models.safety_passport import utc_now


class SafetyJournalPaperRecord(db.Model):
    __tablename__ = "safety_journal_paper_record"

    page_id = db.Column(db.Integer, db.ForeignKey("safety_journal_page.id", ondelete="RESTRICT"), primary_key=True)
    checked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    checked_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)
    check_note = db.Column(db.Text, nullable=True)
    issue_at = db.Column(db.DateTime(timezone=True), nullable=True)
    issue_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)
    issue_note = db.Column(db.Text, nullable=True)
    filed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    filed_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)
    binder_ref = db.Column(db.String(255), nullable=True)
    sheet_ref = db.Column(db.String(80), nullable=True)

    page = db.relationship("SafetyJournalPage", back_populates="paper_record")
    checked_by = db.relationship("User", foreign_keys=[checked_by_id])
    issue_by = db.relationship("User", foreign_keys=[issue_by_id])
    filed_by = db.relationship("User", foreign_keys=[filed_by_id])


class SafetyJournalPaperScan(db.Model):
    __tablename__ = "safety_journal_paper_scan"

    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey("safety_journal_page.id", ondelete="RESTRICT"), nullable=False, index=True)
    version_number = db.Column(db.Integer, nullable=False)
    stored_filename = db.Column(db.String(80), nullable=False, unique=True)
    original_filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(50), nullable=False)
    file_sha256 = db.Column(db.String(64), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    page = db.relationship("SafetyJournalPage", back_populates="paper_scans")
    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])

    __table_args__ = (db.UniqueConstraint("page_id", "version_number", name="uq_safety_journal_paper_scan_version"),)


__all__ = ["SafetyJournalPaperRecord", "SafetyJournalPaperScan"]
