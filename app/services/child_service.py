from app.models import Child, ChildEnrollment


class ChildService:
    """Сервисный слой по карточке ученика и контингенту."""

    @staticmethod
    def get_by_id(child_id: int):
        return Child.query.get_or_404(child_id)

    @staticmethod
    def get_current_class(child: Child):
        enrollments = sorted(child.enrollments, key=lambda e: (e.academic_year_id or 0, e.id or 0), reverse=True)
        return enrollments[0].school_class if enrollments else None

    @staticmethod
    def search_by_fio(text: str, limit: int = 20):
        pattern = f"%{text.strip()}%"
        return (
            Child.query.filter(
                (Child.last_name.ilike(pattern)) |
                (Child.first_name.ilike(pattern)) |
                (Child.middle_name.ilike(pattern))
            )
            .order_by(Child.last_name.asc(), Child.first_name.asc())
            .limit(limit)
            .all()
        )
