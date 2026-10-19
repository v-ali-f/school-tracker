"""Quality of education: 9th/11th grade МЭШ journals and ГИА choices."""
import hashlib
from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from app.core.extensions import db
from app.models import AcademicYear
from app.permissions import has_permission
from app.quality_import import parse_gia_xlsx, parse_journals_zip


quality_bp = Blueprint("quality", __name__, url_prefix="/quality")


class QualitySnapshot(db.Model):
    __tablename__ = "quality_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=False, index=True)
    source_type = db.Column(db.String(20), nullable=False, index=True)
    source_name = db.Column(db.String(255), nullable=False)
    source_sha256 = db.Column(db.String(64), nullable=False)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    imported_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    payload = db.Column(db.JSON, nullable=False)


def _year():
    year = AcademicYear.query.filter_by(is_current=True).first()
    if year is None:
        abort(409, "Не выбран текущий учебный год")
    return year


def _latest(year_id, kind):
    return (QualitySnapshot.query.filter_by(academic_year_id=year_id, source_type=kind)
            .order_by(QualitySnapshot.id.desc()).first())


@quality_bp.get("/")
@login_required
def index():
    if not has_permission("quality_view"):
        abort(403)
    year = _year()
    return render_template("quality/index.html", year=year,
                           can_import=has_permission("quality_import"))


@quality_bp.get("/api/data")
@login_required
def data():
    if not has_permission("quality_view"):
        abort(403)
    year = _year()
    journals = _latest(year.id, "journals")
    gia = _latest(year.id, "gia")
    return jsonify({
        "year": year.name,
        "journals": journals.payload if journals else None,
        "gia": gia.payload if gia else None,
        "imports": {
            "journals": journals.imported_at.isoformat() if journals else None,
            "gia": gia.imported_at.isoformat() if gia else None,
        },
    })


@quality_bp.post("/api/import/<kind>")
@login_required
def import_file(kind):
    if not has_permission("quality_import"):
        abort(403)
    if kind not in {"journals", "gia"}:
        abort(404)
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Выберите файл"}), 400
    filename = upload.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:255]
    expected = ".zip" if kind == "journals" else ".xlsx"
    if not filename.lower().endswith(expected):
        return jsonify({"error": f"Ожидается файл {expected}"}), 400
    content = upload.stream.read((64 if kind == "journals" else 32) * 1024 * 1024 + 1)
    try:
        parsed = (parse_journals_zip(content, filename) if kind == "journals"
                  else parse_gia_xlsx(content, filename))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    year = _year()
    if kind == "journals":
        snapshot_date = datetime.fromisoformat(parsed["snapshot"]).date()
        if ((year.start_date and snapshot_date < year.start_date) or
                (year.end_date and snapshot_date > year.end_date)):
            return jsonify({"error": "Дата выгрузки не относится к текущему учебному году"}), 400
    previous = _latest(year.id, kind)
    checksum = hashlib.sha256(content).hexdigest()
    if previous and previous.source_sha256 == checksum:
        return jsonify({"ok": True, "snapshot_id": previous.id,
                        "records": len(parsed.get("records", parsed.get("students", []))),
                        "unchanged": True})
    if kind == "journals" and previous and parsed["snapshot"] < previous.payload.get("snapshot", ""):
        return jsonify({"error": "Эта выгрузка старше уже загруженной"}), 409
    entry = QualitySnapshot(
        academic_year_id=year.id, source_type=kind, source_name=filename,
        source_sha256=checksum,
        imported_by_user_id=current_user.id, payload=parsed,
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({"ok": True, "snapshot_id": entry.id,
                    "records": len(parsed.get("records", parsed.get("students", [])))})
