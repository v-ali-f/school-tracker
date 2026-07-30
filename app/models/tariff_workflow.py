from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB

from app.core.extensions import db


WORKFLOW_JSON_TYPE = db.JSON().with_variant(JSONB(), "postgresql")

VALIDATION_RUN_STATUSES = ("PASSED", "FAILED", "TECHNICAL_ERROR")
VALIDATION_SEVERITIES = ("BLOCKER", "ERROR", "WARNING", "INFO")
REVIEW_STAGES = ("ACADEMIC", "HR", "FINANCE")
REVIEW_DECISIONS = ("APPROVED", "CHANGES_REQUESTED")
REVIEW_CYCLE_STATUSES = ("OPEN", "RETURNED", "COMPLETED")
REVIEW_COMMENT_KINDS = ("BLOCKING", "RECOMMENDATION")
REVIEW_COMMENT_STATUSES = ("OPEN", "ANSWERED", "CLOSED")
APPROVAL_DECISIONS = ("APPROVED", "REJECTED")
TARIFF_DOCUMENT_STATUSES = ("PROJECT", "OFFICIAL", "ARCHIVED", "ERROR")
TARIFF_DOCUMENT_TYPES = (
    "SUMMARY_TARIFF",
    "PERSONAL_TARIFF",
    "REVIEW_PROTOCOL",
    "APPROVAL_SHEET",
    "ORDER_DRAFT",
    "CHANGE_ORDER_DRAFT",
)


class TariffValidationRun(db.Model):
    __tablename__ = "tariff_validation_run"

    id = db.Column(db.Integer, primary_key=True)
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculation_run_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_calculation_run.id"),
        nullable=True,
        index=True,
    )
    run_no = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, index=True)
    rule_set_version = db.Column(db.String(80), nullable=False)
    input_hash = db.Column(db.String(128), nullable=False, index=True)
    summary_data = db.Column(WORKFLOW_JSON_TYPE, nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=False)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "validation_runs",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    calculation_run = db.relationship("TariffCalculationRun")
    created_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('PASSED','FAILED','TECHNICAL_ERROR')",
            name="ck_tariff_validation_run_status",
        ),
        db.CheckConstraint(
            "run_no > 0",
            name="ck_tariff_validation_run_number",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "run_no",
            name="uq_tariff_validation_run_version_number",
        ),
        db.Index(
            "ix_tariff_validation_run_version_status",
            "tariff_version_id",
            "status",
        ),
    )


class TariffValidationIssue(db.Model):
    __tablename__ = "tariff_validation_issue"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    validation_run_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_validation_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_code = db.Column(db.String(80), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False, index=True)
    object_type = db.Column(db.String(80), nullable=True)
    object_id = db.Column(db.Integer, nullable=True)
    message = db.Column(db.String(700), nullable=False)
    remediation = db.Column(db.String(700), nullable=True)
    fingerprint = db.Column(db.String(128), nullable=False)

    validation_run = db.relationship(
        "TariffValidationRun",
        backref=db.backref(
            "issues",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="TariffValidationIssue.id",
        ),
    )
    tariff_version = db.relationship("TariffVersion")

    __table_args__ = (
        db.CheckConstraint(
            "severity IN ('BLOCKER','ERROR','WARNING','INFO')",
            name="ck_tariff_validation_issue_severity",
        ),
        db.UniqueConstraint(
            "validation_run_id",
            "fingerprint",
            name="uq_tariff_validation_issue_fingerprint",
        ),
        db.Index(
            "ix_tariff_validation_issue_version_severity",
            "tariff_version_id",
            "severity",
        ),
    )


class TariffReviewCycle(db.Model):
    __tablename__ = "tariff_review_cycle"

    id = db.Column(db.Integer, primary_key=True)
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    validation_run_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_validation_run.id"),
        nullable=False,
        index=True,
    )
    round_no = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.String(30),
        nullable=False,
        default="OPEN",
        server_default="OPEN",
        index=True,
    )
    started_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    started_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    completed_at = db.Column(db.DateTime, nullable=True)

    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "review_cycles",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    validation_run = db.relationship("TariffValidationRun")
    started_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('OPEN','RETURNED','COMPLETED')",
            name="ck_tariff_review_cycle_status",
        ),
        db.CheckConstraint(
            "round_no > 0",
            name="ck_tariff_review_cycle_round",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "round_no",
            name="uq_tariff_review_cycle_version_round",
        ),
    )


class TariffReviewDecision(db.Model):
    __tablename__ = "tariff_review_decision"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    review_cycle_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_review_cycle.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_stage = db.Column(db.String(30), nullable=False, index=True)
    decision = db.Column(db.String(30), nullable=False, index=True)
    comment = db.Column(db.Text, nullable=True)
    validation_input_hash = db.Column(db.String(128), nullable=False)
    decided_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    decided_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    review_cycle = db.relationship(
        "TariffReviewCycle",
        backref=db.backref(
            "decisions",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="TariffReviewDecision.decided_at",
        ),
    )
    tariff_version = db.relationship("TariffVersion")
    decided_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "review_stage IN ('ACADEMIC','HR','FINANCE')",
            name="ck_tariff_review_decision_stage",
        ),
        db.CheckConstraint(
            "decision IN ('APPROVED','CHANGES_REQUESTED')",
            name="ck_tariff_review_decision_value",
        ),
        db.UniqueConstraint(
            "review_cycle_id",
            "review_stage",
            name="uq_tariff_review_decision_cycle_stage",
        ),
    )


class TariffReviewComment(db.Model):
    __tablename__ = "tariff_review_comment"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    review_cycle_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_review_cycle.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_stage = db.Column(db.String(30), nullable=False, index=True)
    comment_kind = db.Column(db.String(30), nullable=False, index=True)
    status = db.Column(
        db.String(30),
        nullable=False,
        default="OPEN",
        server_default="OPEN",
        index=True,
    )
    object_type = db.Column(db.String(80), nullable=True)
    object_id = db.Column(db.Integer, nullable=True)
    text = db.Column(db.Text, nullable=False)
    response_text = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    answered_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    answered_at = db.Column(db.DateTime, nullable=True)
    closed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    closed_at = db.Column(db.DateTime, nullable=True)

    review_cycle = db.relationship(
        "TariffReviewCycle",
        backref=db.backref(
            "comments",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="TariffReviewComment.created_at",
        ),
    )
    tariff_version = db.relationship("TariffVersion")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    answered_by = db.relationship("User", foreign_keys=[answered_by_user_id])
    closed_by = db.relationship("User", foreign_keys=[closed_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "review_stage IN ('ACADEMIC','HR','FINANCE')",
            name="ck_tariff_review_comment_stage",
        ),
        db.CheckConstraint(
            "comment_kind IN ('BLOCKING','RECOMMENDATION')",
            name="ck_tariff_review_comment_kind",
        ),
        db.CheckConstraint(
            "status IN ('OPEN','ANSWERED','CLOSED')",
            name="ck_tariff_review_comment_status",
        ),
        db.Index(
            "ix_tariff_review_comment_version_status",
            "tariff_version_id",
            "status",
        ),
    )


class TariffApprovalDecision(db.Model):
    __tablename__ = "tariff_approval_decision"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_cycle_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_review_cycle.id"),
        nullable=False,
        index=True,
    )
    decision_no = db.Column(db.Integer, nullable=False)
    decision = db.Column(db.String(30), nullable=False, index=True)
    comment = db.Column(db.Text, nullable=True)
    version_checksum = db.Column(db.String(128), nullable=False)
    effective_from = db.Column(db.Date, nullable=False)
    decided_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    decided_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "approval_decisions",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="TariffApprovalDecision.decided_at",
        ),
    )
    review_cycle = db.relationship("TariffReviewCycle")
    decided_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "decision IN ('APPROVED','REJECTED')",
            name="ck_tariff_approval_decision_value",
        ),
        db.CheckConstraint(
            "decision_no > 0",
            name="ck_tariff_approval_decision_number",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "decision_no",
            name="uq_tariff_approval_decision_version_number",
        ),
    )


class TariffDocumentArtifact(db.Model):
    __tablename__ = "tariff_document_artifact"

    id = db.Column(db.Integer, primary_key=True)
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calculation_run_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_calculation_run.id"),
        nullable=True,
        index=True,
    )
    document_type = db.Column(db.String(40), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, index=True)
    revision_no = db.Column(db.Integer, nullable=False)
    employee_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True,
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("department.id"),
        nullable=True,
        index=True,
    )
    scope_key = db.Column(db.String(80), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False)
    checksum_sha256 = db.Column(db.String(64), nullable=False, index=True)
    version_checksum = db.Column(db.String(128), nullable=True)
    template_version = db.Column(db.String(80), nullable=False)
    generation_parameters = db.Column(WORKFLOW_JSON_TYPE, nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    archived_at = db.Column(db.DateTime, nullable=True)

    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "document_artifacts",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    calculation_run = db.relationship("TariffCalculationRun")
    employee = db.relationship(
        "User",
        foreign_keys=[employee_user_id],
    )
    department = db.relationship("Department")
    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_user_id],
    )

    __table_args__ = (
        db.CheckConstraint(
            "document_type IN ("
            "'SUMMARY_TARIFF','PERSONAL_TARIFF','REVIEW_PROTOCOL',"
            "'APPROVAL_SHEET','ORDER_DRAFT','CHANGE_ORDER_DRAFT'"
            ")",
            name="ck_tariff_document_artifact_type",
        ),
        db.CheckConstraint(
            "status IN ('PROJECT','OFFICIAL','ARCHIVED','ERROR')",
            name="ck_tariff_document_artifact_status",
        ),
        db.CheckConstraint(
            "revision_no > 0 AND file_size >= 0",
            name="ck_tariff_document_artifact_values",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "document_type",
            "scope_key",
            "revision_no",
            name="uq_tariff_document_artifact_scope_revision",
        ),
        db.Index(
            "ix_tariff_document_artifact_version_type_status",
            "tariff_version_id",
            "document_type",
            "status",
        ),
    )


__all__ = [
    "APPROVAL_DECISIONS",
    "REVIEW_COMMENT_KINDS",
    "REVIEW_COMMENT_STATUSES",
    "REVIEW_CYCLE_STATUSES",
    "REVIEW_DECISIONS",
    "REVIEW_STAGES",
    "TARIFF_DOCUMENT_STATUSES",
    "TARIFF_DOCUMENT_TYPES",
    "VALIDATION_RUN_STATUSES",
    "VALIDATION_SEVERITIES",
    "TariffApprovalDecision",
    "TariffDocumentArtifact",
    "TariffReviewComment",
    "TariffReviewCycle",
    "TariffReviewDecision",
    "TariffValidationIssue",
    "TariffValidationRun",
]
