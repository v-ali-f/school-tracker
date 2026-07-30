import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_

from app.core.extensions import db
from app.models import (
    EducationActivity,
    EducationActivityAlias,
    ExternalActivityMappingLog,
    Subject,
)


MATCHED = "MATCHED"
AMBIGUOUS = "AMBIGUOUS"
UNMATCHED = "UNMATCHED"


@dataclass(frozen=True)
class ActivityMatch:
    status: str
    activity: EducationActivity | None = None
    method: str | None = None
    confidence: Decimal | None = None
    candidates: tuple[EducationActivity, ...] = ()


def normalize_activity_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def normalize_activity_code(value: str | None) -> str:
    code = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    code = re.sub(r"[^A-Z0-9_]+", "_", code)
    return code.strip("_")


def _active_on(query, model, on_date: date):
    return query.filter(
        model.is_active.is_(True),
        or_(model.valid_from.is_(None), model.valid_from <= on_date),
        or_(model.valid_to.is_(None), model.valid_to >= on_date),
    )


def _scope_filter(query, model, organization_id):
    if organization_id is None:
        return query.filter(model.organization_id.is_(None))
    return query.filter(
        or_(
            model.organization_id == organization_id,
            model.organization_id.is_(None),
        )
    )


def _unique_match(candidates, method, confidence) -> ActivityMatch | None:
    by_id = {item.id: item for item in candidates}
    values = tuple(by_id.values())
    if len(values) == 1:
        return ActivityMatch(
            status=MATCHED,
            activity=values[0],
            method=method,
            confidence=Decimal(confidence),
            candidates=values,
        )
    if len(values) > 1:
        return ActivityMatch(
            status=AMBIGUOUS,
            method="AMBIGUOUS",
            confidence=Decimal("0"),
            candidates=values,
        )
    return None


def _prefer_organization(candidates, organization_id):
    values = list(candidates)
    if organization_id is None:
        return [item for item in values if item.organization_id is None]
    local = [item for item in values if item.organization_id == organization_id]
    if local:
        return local
    return [item for item in values if item.organization_id is None]


def resolve_education_activity(
    value: str | None,
    *,
    source_module: str = "GENERAL",
    source_system: str | None = None,
    organization_id: int | None = None,
    on_date: date | None = None,
) -> ActivityMatch:
    normalized = normalize_activity_name(value)
    if not normalized:
        return ActivityMatch(status=UNMATCHED, method="UNMATCHED", confidence=Decimal("0"))

    on_date = on_date or date.today()
    raw_code = normalize_activity_code(value)
    activity_query = _scope_filter(
        _active_on(EducationActivity.query, EducationActivity, on_date),
        EducationActivity,
        organization_id,
    )

    if raw_code:
        match = _unique_match(
            _prefer_organization(
                activity_query.filter(func.upper(EducationActivity.code) == raw_code).all(),
                organization_id,
            ),
            "CODE",
            "1",
        )
        if match:
            return match

    canonical_candidates = [
        item
        for item in activity_query.all()
        if normalize_activity_name(item.name) == normalized
        or normalize_activity_name(item.short_name) == normalized
    ]
    match = _unique_match(
        _prefer_organization(canonical_candidates, organization_id),
        "CANONICAL_NAME",
        "1",
    )
    if match:
        return match

    module = (source_module or "GENERAL").strip().upper()
    system = (source_system or "").strip()
    alias_query = (
        EducationActivityAlias.query
        .join(EducationActivity)
        .filter(
            EducationActivityAlias.normalized_alias == normalized,
            EducationActivityAlias.source_module.in_((module, "GENERAL")),
            EducationActivityAlias.source_system.in_((system, "")),
        )
    )
    alias_query = _scope_filter(alias_query, EducationActivityAlias, organization_id)
    alias_query = _active_on(alias_query, EducationActivityAlias, on_date)
    alias_query = _active_on(alias_query, EducationActivity, on_date)
    aliases = alias_query.order_by(
        EducationActivityAlias.match_priority.asc(),
        EducationActivityAlias.id.asc(),
    ).all()
    preferred_aliases = _prefer_organization(aliases, organization_id)
    match = _unique_match(
        [alias.education_activity for alias in preferred_aliases],
        "ALIAS",
        "0.9900",
    )
    if match:
        return match

    return ActivityMatch(status=UNMATCHED, method="UNMATCHED", confidence=Decimal("0"))


def record_activity_mapping(
    *,
    source_value: str,
    source_module: str,
    match: ActivityMatch,
    organization_id: int | None = None,
    academic_year_id: int | None = None,
    source_system: str | None = None,
    education_plan_item_id: int | None = None,
    import_batch_type: str | None = None,
    import_batch_id: int | None = None,
    confirmed_by_user_id: int | None = None,
) -> ExternalActivityMappingLog:
    method = match.method or (
        "AMBIGUOUS" if match.status == AMBIGUOUS else "UNMATCHED"
    )
    item = ExternalActivityMappingLog(
        organization_id=organization_id,
        academic_year_id=academic_year_id,
        source_module=(source_module or "GENERAL").strip().upper(),
        source_system=(source_system or "").strip() or None,
        source_value=str(source_value or ""),
        normalized_value=normalize_activity_name(source_value),
        education_activity_id=match.activity.id if match.activity else None,
        education_plan_item_id=education_plan_item_id,
        mapping_method=method,
        confidence=match.confidence,
        import_batch_type=import_batch_type,
        import_batch_id=import_batch_id,
        confirmed_by_user_id=confirmed_by_user_id,
        confirmed_at=datetime.utcnow() if confirmed_by_user_id else None,
    )
    db.session.add(item)
    return item


def ensure_activity_for_subject(
    subject: Subject,
    *,
    created_by_user_id: int | None = None,
) -> EducationActivity:
    if subject.education_activity_id:
        return subject.education_activity

    if subject.id is None:
        db.session.add(subject)
        db.session.flush()

    activity = EducationActivity(
        code=f"LEGACY_SUBJECT_{subject.id}",
        name=subject.name,
        short_name=subject.short_name,
        activity_kind="SUBJECT",
        is_global=True,
        is_tariffable=True,
        is_active=True,
        created_by_user_id=created_by_user_id,
        updated_by_user_id=created_by_user_id,
    )
    db.session.add(activity)
    db.session.flush()
    subject.education_activity_id = activity.id
    return activity


def sync_activity_from_subject(
    subject: Subject,
    *,
    updated_by_user_id: int | None = None,
) -> EducationActivity:
    activity = ensure_activity_for_subject(
        subject,
        created_by_user_id=updated_by_user_id,
    )
    if activity.code == f"LEGACY_SUBJECT_{subject.id}":
        activity.name = subject.name
        activity.short_name = subject.short_name
        activity.updated_by_user_id = updated_by_user_id
    return activity


def sync_subject_from_activity(
    activity: EducationActivity,
) -> Subject | None:
    if activity.activity_kind != "SUBJECT":
        if activity.legacy_subject is not None:
            raise ValueError(
                "Учебный предмет нельзя преобразовать в другой вид, "
                "пока он используется старыми разделами системы."
            )
        return None

    subject = activity.legacy_subject
    if subject is None:
        subject = (
            Subject.query
            .filter(func.lower(Subject.name) == activity.name.lower())
            .first()
        )
        if (
            subject is not None
            and subject.education_activity_id not in (None, activity.id)
        ):
            raise ValueError(
                "Предмет с таким названием уже связан с другой записью."
            )
        if subject is None:
            subject = Subject(name=activity.name)
            db.session.add(subject)
        subject.education_activity_id = activity.id

    subject.name = activity.name
    subject.short_name = activity.short_name
    return subject


def get_or_create_subject_with_activity(
    name: str,
    *,
    short_name: str | None = None,
    created_by_user_id: int | None = None,
) -> tuple[Subject, bool]:
    clean_name = " ".join(str(name or "").split())
    if not clean_name:
        raise ValueError("Subject name is required")

    subject = Subject.query.filter(func.lower(Subject.name) == clean_name.lower()).first()
    created = subject is None
    if subject is None:
        subject = Subject(name=clean_name, short_name=(short_name or "").strip() or None)
        db.session.add(subject)
        db.session.flush()
    elif short_name and not subject.short_name:
        subject.short_name = short_name.strip() or None

    ensure_activity_for_subject(subject, created_by_user_id=created_by_user_id)
    return subject, created


__all__ = [
    "MATCHED",
    "AMBIGUOUS",
    "UNMATCHED",
    "ActivityMatch",
    "normalize_activity_name",
    "normalize_activity_code",
    "resolve_education_activity",
    "record_activity_mapping",
    "ensure_activity_for_subject",
    "sync_activity_from_subject",
    "sync_subject_from_activity",
    "get_or_create_subject_with_activity",
]
