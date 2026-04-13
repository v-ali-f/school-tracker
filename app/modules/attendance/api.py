from flask import jsonify, request
from flask_login import login_required

from app.attendance import attendance_bp
from app.models import Building, SchoolClass
from app.attendance import AttendanceImportSession


@attendance_bp.route("/api/classes")
@login_required
def api_classes():
    grade = request.args.get("grade", type=int)
    building_id = request.args.get("building_id", type=int)
    q = SchoolClass.query
    if grade is not None:
        q = q.filter(SchoolClass.grade == grade)
    if building_id:
        q = q.filter(SchoolClass.building_id == building_id)
    rows = q.order_by(SchoolClass.name.asc()).all()
    return jsonify({"items": [{"id": c.id, "name": c.name, "grade": c.grade, "building_id": c.building_id} for c in rows]})


@attendance_bp.route("/api/buildings")
@login_required
def api_buildings():
    rows = Building.query.order_by(Building.name.asc()).all()
    return jsonify({"items": [{"id": b.id, "name": b.name} for b in rows]})


@attendance_bp.route("/api/attendance/sessions")
@login_required
def api_attendance_sessions():
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    building_id = request.args.get("building_id", type=int)
    q = AttendanceImportSession.query
    if year:
        q = q.filter(AttendanceImportSession.period_year == year)
    if month:
        q = q.filter(AttendanceImportSession.period_num == month)
    if building_id:
        q = q.filter(AttendanceImportSession.building_id == building_id)
    rows = q.order_by(AttendanceImportSession.imported_at.desc(), AttendanceImportSession.id.desc()).limit(100).all()
    return jsonify({"items": [{
        "id": s.id,
        "filename": s.filename,
        "period_month": s.period_month,
        "building_id": s.building_id,
        "building_name": s.building.name if getattr(s, "building", None) else None,
        "imported_at": s.imported_at.isoformat() if s.imported_at else None,
        "rows_processed": s.rows_processed,
    } for s in rows]})
