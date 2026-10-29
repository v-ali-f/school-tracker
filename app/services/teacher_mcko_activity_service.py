"""The MCKO catalog includes subjects and one primary-school meta diagnostic."""

from app.models import EducationActivity
from app.services.education_activity_service import assign_subject_activity, list_subject_activities


PRIMARY_META_CODE = "MCKO_PRIMARY_META"
PRIMARY_META_NAME = "Комплексная метапредметная диагностика начальных классов"


def mcko_activity_options():
    subjects = list_subject_activities()
    meta = EducationActivity.query.filter_by(
        code=PRIMARY_META_CODE,
        organization_id=None,
        activity_kind="MODULE",
        is_active=True,
    ).first()
    return subjects + ([meta] if meta is not None else [])


def get_mcko_activity(activity_id):
    try:
        activity_id = int(activity_id)
    except (TypeError, ValueError):
        return None
    return next((item for item in mcko_activity_options() if item.id == activity_id), None)


def assign_mcko_activity(record, activity):
    if activity.activity_kind == "SUBJECT":
        assign_subject_activity(record, activity)
    elif activity.code == PRIMARY_META_CODE and activity.activity_kind == "MODULE":
        record.education_activity_id = activity.id
        record.education_activity = activity
        record.subject_id = None
    else:
        raise ValueError("Выберите вид диагностики из списка.")
    return activity
