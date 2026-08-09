from datetime import date, datetime

from app.core.extensions import db
from app.models import (
    TeacherAttestation,
    TeacherMckoResult,
    TeacherProfessionalRecordChange,
)


RECORD_TYPE_MCKO = "MCKO"
RECORD_TYPE_ATTESTATION = "ATTESTATION"

CHANGE_CREATED = "CREATED"
CHANGE_UPDATED = "UPDATED"
CHANGE_ARCHIVED = "ARCHIVED"


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _snapshot(record):
    if isinstance(record, TeacherMckoResult):
        fields = (
            "education_activity_id",
            "subject_id",
            "passed_at",
            "expires_at",
            "level",
            "certificate_number",
            "result_text",
            "entry_source",
            "is_archived",
        )
    elif isinstance(record, TeacherAttestation):
        fields = (
            "category",
            "position_title",
            "decision_date",
            "valid_until",
            "is_indefinite",
            "order_number",
            "notes",
            "entry_source",
            "is_archived",
        )
    else:
        raise TypeError("Unsupported professional record type")
    return {
        field: _json_value(getattr(record, field, None))
        for field in fields
    }


def record_professional_change(record, *, change_kind, actor_id):
    if record.id is None:
        db.session.flush()
    if isinstance(record, TeacherMckoResult):
        record_type = RECORD_TYPE_MCKO
    elif isinstance(record, TeacherAttestation):
        record_type = RECORD_TYPE_ATTESTATION
    else:
        raise TypeError("Unsupported professional record type")
    change = TeacherProfessionalRecordChange(
        record_type=record_type,
        record_id=record.id,
        teacher_id=record.teacher_id,
        change_kind=change_kind,
        changed_by_user_id=actor_id,
        snapshot=_snapshot(record),
    )
    db.session.add(change)
    return change
