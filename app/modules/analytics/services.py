from app.management import build_management_data
from app.services.teacher_rating import build_teacher_rating

def build_analytics_payload(year_id=None):
    payload = build_management_data(year_id)
    payload["teacher_rating"] = build_teacher_rating()
    return payload
