import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_

from app.core.extensions import db
from app.models import (
    Department,
    DepartmentSubject,
    EducationActivity,
    EducationActivityAlias,
    EducationActivityDepartment,
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
        # Keep the legacy adapter for historical results. New subject
        # selectors use EducationActivity.activity_kind and will no longer
        # offer this entry after it is converted to another kind.
        subject = activity.legacy_subject
        if subject is not None:
            subject.name = activity.name
            subject.short_name = activity.short_name
        return subject

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


def subject_activity_query(*, include_inactive: bool = False):
    query = EducationActivity.query.filter(
        EducationActivity.activity_kind == "SUBJECT",
    )
    if not include_inactive:
        query = query.filter(EducationActivity.is_active.is_(True))
    return query


def list_subject_activities(*, include_inactive: bool = False):
    items = subject_activity_query(
        include_inactive=include_inactive,
    ).all()
    return sorted(
        items,
        key=lambda item: (
            normalize_activity_name(item.name),
            item.id,
        ),
    )


def get_subject_activity(activity_id: int | None) -> EducationActivity | None:
    if not activity_id:
        return None
    return subject_activity_query(include_inactive=True).filter_by(
        id=activity_id,
    ).first()


def assign_subject_activity(target, activity: EducationActivity | int):
    if isinstance(activity, int):
        activity = get_subject_activity(activity)
    if activity is None or activity.activity_kind != "SUBJECT":
        raise ValueError("Выбранная запись не является учебным предметом.")

    subject = sync_subject_from_activity(activity)
    db.session.flush()
    target.education_activity_id = activity.id
    if hasattr(type(target), "education_activity"):
        target.education_activity = activity
    if hasattr(target, "subject_id"):
        target.subject_id = subject.id
    if "subject_name" in target.__table__.columns:
        target.subject_name = activity.name
    if target.__class__.__name__ == "DiagnosticSession":
        target.subject = activity.name
    return activity


def sync_legacy_department_subject_links(
    activity: EducationActivity,
    department_ids=None,
):
    if activity.activity_kind != "SUBJECT":
        subject = activity.legacy_subject
        if subject is not None:
            DepartmentSubject.query.filter_by(
                subject_id=subject.id,
            ).delete(synchronize_session=False)
        return
    subject = sync_subject_from_activity(activity)
    db.session.flush()
    desired_department_ids = (
        {int(value) for value in department_ids}
        if department_ids is not None
        else {
            link.department_id
            for link in activity.department_links
            if link.is_active and link.valid_from is None
        }
    )
    existing = DepartmentSubject.query.filter_by(
        subject_id=subject.id,
    ).all()
    existing_by_department = {link.department_id: link for link in existing}
    for department_id, link in existing_by_department.items():
        if department_id not in desired_department_ids:
            db.session.delete(link)
        elif link.education_activity_id != activity.id:
            link.education_activity_id = activity.id
    for department_id in desired_department_ids - set(existing_by_department):
        db.session.add(DepartmentSubject(
            department_id=department_id,
            subject_id=subject.id,
            education_activity_id=activity.id,
        ))


def replace_activity_departments(
    activity: EducationActivity,
    department_ids,
):
    unique_ids = list(dict.fromkeys(int(value) for value in department_ids))
    departments = (
        Department.query
        .filter(Department.id.in_(unique_ids))
        .order_by(func.lower(Department.name).asc(), Department.id.asc())
        .all()
        if unique_ids else []
    )
    if len(departments) != len(unique_ids):
        raise ValueError("Одна из выбранных кафедр не найдена.")

    selected_ids = {department.id for department in departments}
    default_links = {
        link.department_id: link
        for link in activity.department_links
        if link.valid_from is None
    }
    existing_primary_id = next(
        (
            link.department_id
            for link in default_links.values()
            if link.is_primary and link.department_id in selected_ids
        ),
        None,
    )
    primary_id = (
        existing_primary_id
        if existing_primary_id is not None
        else (departments[0].id if departments else None)
    )
    for department_id, link in default_links.items():
        link.is_active = department_id in selected_ids
        link.is_primary = department_id == primary_id
    for department in departments:
        if department.id not in default_links:
            db.session.add(EducationActivityDepartment(
                education_activity_id=activity.id,
                department_id=department.id,
                is_primary=department.id == primary_id,
            ))
    db.session.flush()
    sync_legacy_department_subject_links(activity, selected_ids)
    return departments


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


def get_or_create_subject_activity(
    name: str,
    *,
    short_name: str | None = None,
    created_by_user_id: int | None = None,
) -> tuple[EducationActivity, bool]:
    """Return the canonical subject while keeping the legacy adapter in sync."""
    clean_name = " ".join(str(name or "").split())
    if not clean_name:
        raise ValueError("Subject name is required")

    activities = (
        subject_activity_query(include_inactive=True)
        .filter(func.lower(EducationActivity.name) == clean_name.lower())
        .order_by(EducationActivity.id.asc())
        .all()
    )
    if len(activities) > 1:
        raise ValueError(
            f"В едином каталоге найдено несколько предметов «{clean_name}»."
        )
    if activities:
        activity = activities[0]
        if short_name and not activity.short_name:
            activity.short_name = short_name.strip() or None
        sync_subject_from_activity(activity)
        db.session.flush()
        return activity, False

    subject, created = get_or_create_subject_with_activity(
        clean_name,
        short_name=short_name,
        created_by_user_id=created_by_user_id,
    )
    return ensure_activity_for_subject(
        subject,
        created_by_user_id=created_by_user_id,
    ), created


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
    "subject_activity_query",
    "list_subject_activities",
    "get_subject_activity",
    "assign_subject_activity",
    "sync_legacy_department_subject_links",
    "replace_activity_departments",
    "get_or_create_subject_with_activity",
    "get_or_create_subject_activity",
]
