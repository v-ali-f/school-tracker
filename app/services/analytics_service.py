from sqlalchemy import func

from app.models import AcademicYear, Child, Incident, IncidentChild, SchoolClass, ControlWorkResult
from app import db


class AnalyticsService:
    """Сервис управленческой аналитики для dashboard директора."""

    @staticmethod
    def current_year():
        return AcademicYear.query.filter_by(is_current=True).first()

    @staticmethod
    def contingent_summary(academic_year_id=None):
        query = db.session.query(Child)
        if academic_year_id:
            query = query.join(ChildEnrollment, ChildEnrollment.child_id == Child.id).filter(ChildEnrollment.academic_year_id == academic_year_id)
        children = query.all()
        total = len(children)
        boys = sum(1 for c in children if (c.gender or '').upper().startswith('М'))
        girls = sum(1 for c in children if (c.gender or '').upper().startswith('Ж'))
        return {
            'total': total,
            'boys': boys,
            'girls': girls,
            'ovz': sum(1 for c in children if c.is_ovz),
            'vshu': sum(1 for c in children if c.is_vshu),
            'low_results': sum(1 for c in children if c.is_low),
        }

    @staticmethod
    def incidents_summary():
        total = Incident.query.count()
        open_count = Incident.query.filter(Incident.occurred_at.isnot(None)).count()
        return {
            'total': total,
            'registered': open_count,
        }

    @staticmethod
    def control_work_summary():
        avg_mark = db.session.query(func.avg(ControlWorkResult.mark)).scalar() or 0
        avg_percent = db.session.query(func.avg(ControlWorkResult.percent)).scalar() or 0
        return {
            'avg_mark': round(float(avg_mark), 2),
            'avg_percent': round(float(avg_percent), 2),
        }


# late import to avoid circular import in type evaluation order
from app.models import ChildEnrollment  # noqa: E402
