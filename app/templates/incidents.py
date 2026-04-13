from flask import jsonify

@children_bp.route("/api/classes/by-grade")
@login_required
def api_classes_by_grade():
    """Вернёт список классов (из реестра SchoolClass) по параллели."""
    from .models import AcademicYear, SchoolClass

    grade = request.args.get("grade", type=int)
    if not grade:
        return jsonify([])

    year = AcademicYear.query.filter_by(is_current=True).first()
    if not year:
        return jsonify([])

    # классы вида "5А", "5Б", "10ИТ" — фильтруем по начальным цифрам
    classes = (
        SchoolClass.query
        .filter(SchoolClass.academic_year_id == year.id)
        .order_by(SchoolClass.name.asc())
        .all()
    )

    out = []
    for c in classes:
        m = re.match(r"^(\d{1,2})", (c.name or "").strip())
        if m and int(m.group(1)) == grade:
            out.append({"id": c.id, "name": c.name})
    return jsonify(out)


@children_bp.route("/api/children/by-class")
@login_required
def api_children_by_class():
    """Вернёт детей по school_class_id (текущий учебный год, ACTIVE)."""
    from .models import AcademicYear, ChildEnrollment

    class_id = request.args.get("class_id", type=int)
    if not class_id:
        return jsonify([])

    year = AcademicYear.query.filter_by(is_current=True).first()
    if not year:
        return jsonify([])

    ens = (
        ChildEnrollment.query
        .join(Child, ChildEnrollment.child_id == Child.id)
        .filter(
            ChildEnrollment.academic_year_id == year.id,
            ChildEnrollment.school_class_id == class_id,
            ChildEnrollment.ended_at.is_(None),
            ChildEnrollment.status == "ACTIVE",
        )
        .order_by(Child.last_name.asc(), Child.first_name.asc(), Child.middle_name.asc())
        .all()
    )

    return jsonify([{"id": en.child.id, "fio": en.child.fio} for en in ens])