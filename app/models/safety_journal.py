"""Approved safety instructions and immutable journal pages."""

from app.core.extensions import db
from app.models.safety_passport import utc_now


class SafetyInstruction(db.Model):
    __tablename__ = "safety_instruction"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(80), nullable=False, unique=True)
    title = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(120), nullable=False)
    briefing_kind = db.Column(db.String(80), nullable=False)
    scope = db.Column(db.Text, nullable=True)
    classroom_type = db.Column(db.String(80), nullable=True)
    event_kind = db.Column(db.String(80), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    versions = db.relationship(
        "SafetyInstructionVersion", back_populates="instruction",
        order_by="SafetyInstructionVersion.version_number",
    )


class SafetyInstructionVersion(db.Model):
    __tablename__ = "safety_instruction_version"

    id = db.Column(db.Integer, primary_key=True)
    instruction_id = db.Column(db.Integer, db.ForeignKey("safety_instruction.id", ondelete="RESTRICT"), nullable=False, index=True)
    version_number = db.Column(db.Integer, nullable=False)
    title_snapshot = db.Column(db.String(500), nullable=False)
    approved_on = db.Column(db.Date, nullable=False)
    effective_from = db.Column(db.Date, nullable=False)
    effective_to = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active")
    approval_basis = db.Column(db.String(500), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(80), nullable=False, unique=True)
    file_sha256 = db.Column(db.String(64), nullable=False)
    file_mime_type = db.Column(db.String(120), nullable=False)
    replaced_version_id = db.Column(db.Integer, db.ForeignKey("safety_instruction_version.id", ondelete="RESTRICT"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    instruction = db.relationship("SafetyInstruction", back_populates="versions")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    replaced_version = db.relationship("SafetyInstructionVersion", remote_side=[id], foreign_keys=[replaced_version_id])

    __table_args__ = (
        db.UniqueConstraint("instruction_id", "version_number", name="uq_safety_instruction_version_number"),
        db.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_safety_instruction_period"),
    )


class SafetyInstructionAccessEvent(db.Model):
    __tablename__ = "safety_instruction_access_event"

    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey("safety_instruction_version.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class SafetyJournalDraft(db.Model):
    __tablename__ = "safety_journal_draft"

    id = db.Column(db.String(36), primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True)
    instruction_version_id = db.Column(db.Integer, db.ForeignKey("safety_instruction_version.id", ondelete="RESTRICT"), nullable=True)
    library_item_id = db.Column(db.String(64), nullable=True)
    subject = db.Column(db.String(120), nullable=True)
    briefing_kind = db.Column(db.String(80), nullable=True)
    header_note = db.Column(db.String(500), nullable=True)
    instructed_on = db.Column(db.Date, nullable=True)
    grade = db.Column(db.Integer, nullable=True)
    class_ids = db.Column(db.JSON, nullable=False, default=list)
    selected_child_ids = db.Column(db.JSON, nullable=False, default=list)
    removed_child_ids = db.Column(db.JSON, nullable=False, default=list)
    status = db.Column(db.String(20), nullable=False, default="draft")
    page_id = db.Column(db.Integer, db.ForeignKey("safety_journal_page.id", ondelete="SET NULL"), nullable=True)
    trip_order_id = db.Column(db.Integer, db.ForeignKey("safety_trip_order.order_id", ondelete="RESTRICT"), nullable=True, index=True)
    trip_assignment_id = db.Column(db.Integer, db.ForeignKey("safety_trip_assignment.id", ondelete="RESTRICT"), nullable=True)
    trip_order_revision = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    author = db.relationship("User", foreign_keys=[author_id])
    instruction_version = db.relationship("SafetyInstructionVersion", foreign_keys=[instruction_version_id])
    page = db.relationship("SafetyJournalPage", foreign_keys=[page_id])
    trip_order = db.relationship("SafetyTripOrder", foreign_keys=[trip_order_id])
    trip_assignment = db.relationship("SafetyTripAssignment", foreign_keys=[trip_assignment_id])
    events = db.relationship("SafetyJournalDraftEvent", back_populates="draft", order_by="SafetyJournalDraftEvent.created_at")


class SafetyJournalDraftEvent(db.Model):
    __tablename__ = "safety_journal_draft_event"

    id = db.Column(db.Integer, primary_key=True)
    draft_id = db.Column(db.String(36), db.ForeignKey("safety_journal_draft.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id", ondelete="SET NULL"), nullable=True)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    draft = db.relationship("SafetyJournalDraft", back_populates="events")
    actor = db.relationship("User", foreign_keys=[actor_id])


class SafetyJournalPage(db.Model):
    __tablename__ = "safety_journal_page"

    id = db.Column(db.Integer, primary_key=True)
    source_draft_id = db.Column(db.String(36), nullable=False, unique=True)
    number = db.Column(db.String(50), nullable=False, unique=True)
    kind = db.Column(db.String(20), nullable=False, default="ordinary")
    trip_order_id = db.Column(db.Integer, db.ForeignKey("safety_trip_order.order_id", ondelete="RESTRICT"), nullable=True, index=True)
    trip_assignment_id = db.Column(db.Integer, db.ForeignKey("safety_trip_assignment.id", ondelete="RESTRICT"), nullable=True)
    trip_order_revision = db.Column(db.Integer, nullable=True)
    trip_snapshot = db.Column(db.JSON, nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True)
    instruction_version_id = db.Column(db.Integer, db.ForeignKey("safety_instruction_version.id", ondelete="RESTRICT"), nullable=True, index=True)
    library_item_id = db.Column(db.String(64), nullable=True)
    subject_snapshot = db.Column(db.String(120), nullable=True)
    instructed_on = db.Column(db.Date, nullable=False, index=True)
    group_label = db.Column(db.String(255), nullable=False)
    organization_name_snapshot = db.Column(db.String(500), nullable=False)
    instructor_name_snapshot = db.Column(db.String(255), nullable=False)
    instruction_number_snapshot = db.Column(db.String(80), nullable=False)
    instruction_title_snapshot = db.Column(db.String(500), nullable=False)
    instruction_summary_snapshot = db.Column(db.Text, nullable=False)
    instruction_file_sha256_snapshot = db.Column(db.String(64), nullable=False)
    instruction_version_number_snapshot = db.Column(db.Integer, nullable=False)
    briefing_kind_snapshot = db.Column(db.String(80), nullable=True)
    header_note_snapshot = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="generated", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    printed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    annulled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    annulled_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=True)
    annul_reason = db.Column(db.Text, nullable=True)

    author = db.relationship("User", foreign_keys=[author_id])
    annulled_by = db.relationship("User", foreign_keys=[annulled_by_id])
    instruction_version = db.relationship("SafetyInstructionVersion", foreign_keys=[instruction_version_id])
    trip_order = db.relationship("SafetyTripOrder", foreign_keys=[trip_order_id])
    trip_assignment = db.relationship("SafetyTripAssignment", foreign_keys=[trip_assignment_id])
    participants = db.relationship("SafetyJournalParticipant", back_populates="page", order_by="SafetyJournalParticipant.sequence")
    classes = db.relationship("SafetyJournalPageClass", back_populates="page")
    revisions = db.relationship("SafetyJournalPageRevision", back_populates="page", order_by="SafetyJournalPageRevision.version_number")
    events = db.relationship("SafetyJournalPageEvent", back_populates="page", order_by="SafetyJournalPageEvent.created_at")
    paper_record = db.relationship("SafetyJournalPaperRecord", back_populates="page", uselist=False)
    paper_scans = db.relationship("SafetyJournalPaperScan", back_populates="page", order_by="SafetyJournalPaperScan.version_number")


class SafetyJournalPageClass(db.Model):
    __tablename__ = "safety_journal_page_class"

    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey("safety_journal_page.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id", ondelete="SET NULL"), nullable=True, index=True)
    class_name_snapshot = db.Column(db.String(30), nullable=False)
    building_id_snapshot = db.Column(db.Integer, nullable=True, index=True)

    page = db.relationship("SafetyJournalPage", back_populates="classes")


class SafetyJournalParticipant(db.Model):
    __tablename__ = "safety_journal_participant"

    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey("safety_journal_page.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = db.Column(db.Integer, nullable=False)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id", ondelete="SET NULL"), nullable=True)
    full_name_snapshot = db.Column(db.String(400), nullable=False)
    birth_date_snapshot = db.Column(db.Date, nullable=False)
    class_name_snapshot = db.Column(db.String(30), nullable=False)
    class_id_snapshot = db.Column(db.Integer, nullable=True)
    signature_rule = db.Column(db.String(20), nullable=False)

    page = db.relationship("SafetyJournalPage", back_populates="participants")

    __table_args__ = (
        db.UniqueConstraint("page_id", "sequence", name="uq_safety_journal_participant_sequence"),
        db.UniqueConstraint("page_id", "child_id", name="uq_safety_journal_participant_child"),
    )


class SafetyJournalPageRevision(db.Model):
    __tablename__ = "safety_journal_page_revision"

    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey("safety_journal_page.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = db.Column(db.Integer, nullable=False)
    stored_filename = db.Column(db.String(80), nullable=False, unique=True)
    pdf_sha256 = db.Column(db.String(64), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    page = db.relationship("SafetyJournalPage", back_populates="revisions")
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        db.UniqueConstraint("page_id", "version_number", name="uq_safety_journal_page_revision_number"),
    )


class SafetyJournalPageEvent(db.Model):
    __tablename__ = "safety_journal_page_event"

    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey("safety_journal_page.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    page = db.relationship("SafetyJournalPage", back_populates="events")
    actor = db.relationship("User", foreign_keys=[actor_id])


__all__ = [
    "SafetyInstruction", "SafetyInstructionVersion", "SafetyInstructionAccessEvent", "SafetyJournalDraft",
    "SafetyJournalDraftEvent", "SafetyJournalPage", "SafetyJournalPageClass",
    "SafetyJournalParticipant", "SafetyJournalPageRevision", "SafetyJournalPageEvent",
]
