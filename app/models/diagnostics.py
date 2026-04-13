"""Models for diagnostic imports (МЦКО / ЕКР / ФГ)."""
from datetime import datetime

from app.core.extensions import db


class DiagnosticSession(db.Model):
    __tablename__ = "diagnostic_session"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    diagnostic_type = db.Column(db.String(30), nullable=False, default="MCKO")
    subject = db.Column(db.String(120), nullable=True)
    parallel = db.Column(db.Integer, nullable=True)
    date_main = db.Column(db.Date, nullable=True)
    date_reserve = db.Column(db.Date, nullable=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="draft")
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    academic_year = db.relationship("AcademicYear")
    author = db.relationship("User")


class DiagnosticImportBatch(db.Model):
    __tablename__ = "diagnostic_import_batch"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("diagnostic_session.id"), nullable=False, index=True)
    import_kind = db.Column(db.String(30), nullable=False, default="main")  # main / reserve / codes
    filename = db.Column(db.String(255), nullable=True)
    file_hash = db.Column(db.String(64), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="processed")
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    session = db.relationship("DiagnosticSession", backref=db.backref("import_batches", lazy=True, cascade="all, delete-orphan"))
    author = db.relationship("User")


class DiagnosticStudentCode(db.Model):
    __tablename__ = "diagnostic_student_code"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("diagnostic_session.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=True, index=True)
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    full_name_raw = db.Column(db.String(255), nullable=True)
    class_name_raw = db.Column(db.String(50), nullable=True)
    participant_code = db.Column(db.String(50), nullable=True, index=True)
    list_number = db.Column(db.Integer, nullable=True)
    source_type = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    session = db.relationship("DiagnosticSession", backref=db.backref("student_codes", lazy=True, cascade="all, delete-orphan"))
    child = db.relationship("Child")
    school_class = db.relationship("SchoolClass")


class DiagnosticResult(db.Model):
    __tablename__ = "diagnostic_result"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("diagnostic_session.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=True, index=True)
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    import_batch_id = db.Column(db.Integer, db.ForeignKey("diagnostic_import_batch.id"), nullable=True, index=True)

    full_name_raw = db.Column(db.String(255), nullable=True)
    class_name_raw = db.Column(db.String(50), nullable=True)
    list_number = db.Column(db.Integer, nullable=True)
    participant_code = db.Column(db.String(50), nullable=True, index=True)
    variant = db.Column(db.String(50), nullable=True)

    total_score = db.Column(db.Float, nullable=True)
    percent = db.Column(db.Float, nullable=True)
    mark = db.Column(db.String(20), nullable=True)
    level = db.Column(db.String(50), nullable=True)

    source_kind = db.Column(db.String(20), nullable=False, default="main")
    is_final = db.Column(db.Boolean, nullable=False, default=True)
    replaced_result_id = db.Column(db.Integer, db.ForeignKey("diagnostic_result.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    session = db.relationship("DiagnosticSession", backref=db.backref("results", lazy=True, cascade="all, delete-orphan"))
    child = db.relationship("Child")
    school_class = db.relationship("SchoolClass")
    import_batch = db.relationship("DiagnosticImportBatch", backref=db.backref("results", lazy=True))
    replaced_result = db.relationship("DiagnosticResult", remote_side=[id])


class DiagnosticTeacherBinding(db.Model):
    __tablename__ = "diagnostic_teacher_binding"

    id = db.Column(db.Integer, primary_key=True)
    result_id = db.Column(db.Integer, db.ForeignKey("diagnostic_result.id"), nullable=False, unique=True, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    source = db.Column(db.String(20), nullable=False, default="manual")  # auto / manual
    comment = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    result = db.relationship("DiagnosticResult", backref=db.backref("teacher_binding", uselist=False, cascade="all, delete-orphan"))
    teacher = db.relationship("User")


class DiagnosticTaskResult(db.Model):
    __tablename__ = "diagnostic_task_result"

    id = db.Column(db.Integer, primary_key=True)
    result_id = db.Column(db.Integer, db.ForeignKey("diagnostic_result.id"), nullable=False, index=True)
    task_number = db.Column(db.String(20), nullable=False)
    raw_value = db.Column(db.String(50), nullable=True)
    topic = db.Column(db.String(500), nullable=True)
    skill = db.Column(db.String(500), nullable=True)
    kes_code = db.Column(db.String(100), nullable=True)
    block_name = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    result = db.relationship("DiagnosticResult", backref=db.backref("task_results", lazy=True, cascade="all, delete-orphan"))


class DiagnosticKesResult(db.Model):
    __tablename__ = "diagnostic_kes_result"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("diagnostic_session.id"), nullable=False, index=True)
    import_batch_id = db.Column(db.Integer, db.ForeignKey("diagnostic_import_batch.id"), nullable=True, index=True)
    class_name_raw = db.Column(db.String(50), nullable=True)
    kes_code = db.Column(db.String(100), nullable=False, index=True)
    kes_name = db.Column(db.String(1000), nullable=True)
    class_percent = db.Column(db.Float, nullable=True)
    city_percent = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    session = db.relationship("DiagnosticSession", backref=db.backref("kes_results", lazy=True, cascade="all, delete-orphan"))
    import_batch = db.relationship("DiagnosticImportBatch", backref=db.backref("kes_results", lazy=True, cascade="all, delete-orphan"))


class DiagnosticImportIssue(db.Model):
    __tablename__ = "diagnostic_import_issue"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("diagnostic_session.id"), nullable=False, index=True)
    import_batch_id = db.Column(db.Integer, db.ForeignKey("diagnostic_import_batch.id"), nullable=True, index=True)
    severity = db.Column(db.String(20), nullable=False, default="warning")
    issue_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    payload_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    session = db.relationship("DiagnosticSession", backref=db.backref("issues", lazy=True, cascade="all, delete-orphan"))
    import_batch = db.relationship("DiagnosticImportBatch", backref=db.backref("issues", lazy=True, cascade="all, delete-orphan"))


__all__ = [
    "DiagnosticSession",
    "DiagnosticImportBatch",
    "DiagnosticStudentCode",
    "DiagnosticResult",
    "DiagnosticTeacherBinding",
    "DiagnosticTaskResult",
    "DiagnosticKesResult",
    "DiagnosticImportIssue",
]
