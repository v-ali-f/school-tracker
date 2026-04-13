from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.core.extensions import db
from .models import AcademicYear, SchoolClass, User

classes_bp = Blueprint("classes", __name__)

def _admin_only():
    if getattr(current_user, "role", "VIEWER") != "ADMIN":
        abort(403)

@classes_bp.route("/classes")
@login_required
def classes_list():
    _admin_only()

    year = AcademicYear.query.filter_by(is_current=True).first()
    if not year:
        flash("Не задан текущий учебный год (AcademicYear.is_current=True)", "danger")
        return render_template("classes_list.html", year=None, classes=[], teachers=[])

    classes = (SchoolClass.query
               .filter(SchoolClass.academic_year_id == year.id)
               .order_by(SchoolClass.name.asc())
               .all())

    teachers = (User.query
                .order_by(User.last_name.asc(), User.first_name.asc())
                .all())

    return render_template("classes_list.html", year=year, classes=classes, teachers=teachers)

@classes_bp.route("/classes/new", methods=["POST"])
@login_required
def classes_new():
    _admin_only()

    year = AcademicYear.query.filter_by(is_current=True).first()
    if not year:
        flash("Нет текущего учебного года", "danger")
        return redirect(url_for("classes.classes_list"))

    name = (request.form.get("name") or "").strip()
    max_students = request.form.get("max_students", type=int) or 25
    teacher_user_id = request.form.get("teacher_user_id", type=int)

    if not name:
        flash("Не указан класс (например 7А)", "danger")
        return redirect(url_for("classes.classes_list"))

    sc = SchoolClass.query.filter_by(academic_year_id=year.id, name=name).first()
    if sc:
        flash("Такой класс уже есть", "warning")
        return redirect(url_for("classes.classes_list"))

    sc = SchoolClass(
        academic_year_id=year.id,
        name=name,
        max_students=max_students,
        teacher_user_id=teacher_user_id
    )
    db.session.add(sc)
    db.session.commit()

    flash("Класс добавлен", "success")
    return redirect(url_for("classes.classes_list"))

@classes_bp.route("/classes/<int:class_id>/update", methods=["POST"])
@login_required
def classes_update(class_id: int):
    _admin_only()

    sc = SchoolClass.query.get_or_404(class_id)

    sc.max_students = request.form.get("max_students", type=int) or sc.max_students
    sc.teacher_user_id = request.form.get("teacher_user_id", type=int)
    db.session.commit()

    flash("Сохранено", "success")
    return redirect(url_for("classes.classes_list"))

@classes_bp.route("/classes/<int:class_id>/delete", methods=["POST"])
@login_required
def classes_delete(class_id: int):
    _admin_only()

    sc = SchoolClass.query.get_or_404(class_id)
    db.session.delete(sc)
    db.session.commit()

    flash("Класс удалён", "success")
    return redirect(url_for("classes.classes_list"))