INCIDENT_CATEGORIES = [
    "Драка/конфликт",
    "Нарушение дисциплины",
    "Трудности в обучении",
    "Буллинг",
    "Травма/вызов скорой",
    "Жалоба родителей",
    "Психологическая проблема",
    "Другое",
]
OVZ_LEVEL_LABELS = {
    "NOO": "Начальное общее образование",
    "OOO": "Основное общее образование",
    "SOO": "Среднее общее образование",
}

OVZ_NOZOLOGY_LABELS = {
    "VISION": "Нарушения зрения",
    "TNR": "Тяжёлые нарушения речи",
    "NODA": "Нарушения опорно-двигательного аппарата",
    "ZPR": "Задержка психического развития",
    "INT": "Интеллектуальные нарушения",
}
AOOP_FULL_NAMES = {
    "4.1": "АООП НОО для обучающихся с нарушениями зрения (вариант 4.1)",
    "4.2": "АООП НОО для обучающихся с нарушениями зрения (вариант 4.2)",
    "4.3": "АООП НОО для обучающихся с нарушениями зрения (вариант 4.3)",

    "5.1": "АООП НОО для обучающихся с тяжёлыми нарушениями речи (вариант 5.1)",
    "5.2": "АООП НОО для обучающихся с тяжёлыми нарушениями речи (вариант 5.2)",

    "6.1": "АООП НОО для обучающихся с нарушениями опорно-двигательного аппарата (вариант 6.1)",
    "6.2": "АООП НОО для обучающихся с нарушениями опорно-двигательного аппарата (вариант 6.2)",
    "6.3": "АООП НОО для обучающихся с нарушениями опорно-двигательного аппарата (вариант 6.3)",
    "6.4": "АООП НОО для обучающихся с нарушениями опорно-двигательного аппарата (вариант 6.4)",

    "7.1": "АООП НОО для обучающихся с задержкой психического развития (вариант 7.1)",
    "7.2": "АООП НОО для обучающихся с задержкой психического развития (вариант 7.2)",

    "8.1": "АООП НОО для обучающихся с интеллектуальными нарушениями (вариант 8.1)",
    "8.2": "АООП НОО для обучающихся с интеллектуальными нарушениями (вариант 8.2)",
    "8.3": "АООП НОО для обучающихся с интеллектуальными нарушениями (вариант 8.3)",
    "8.4": "АООП НОО для обучающихся с интеллектуальными нарушениями (вариант 8.4)",
}

AOOP_TO_OVZ = {
    "4": {"nosology": "VISION", "label": "Нарушения зрения"},
    "5": {"nosology": "TNR", "label": "Тяжёлые нарушения речи"},
    "6": {"nosology": "NODA", "label": "Нарушения опорно-двигательного аппарата"},
    "7": {"nosology": "ZPR", "label": "Задержка психического развития"},
    "8": {"nosology": "INT", "label": "Интеллектуальные нарушения"},
}
from datetime import datetime, date, timedelta
import os
import shutil
import re
import mimetypes
from html import escape

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    current_app,
    flash,
    abort,
    jsonify,
    send_file,
)
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from openpyxl import load_workbook, Workbook
from io import BytesIO

from app.core.extensions import db
from .models import (
    AcademicYear,
    Building,
    User,
    Role,
    UserRole,
    SchoolClass,
    Child,
    ChildEnrollment,
    Parent,
    ChildParent,
    ChildSocial,
    Subject,
    Debt,
    Document,
    ChildComment,
    ChildEvent,
    ChildTransferHistory,
    Incident,
    IncidentChild,
    ControlWorkResult,
    OlympiadResult,
)
from .ovz_rules import OVZ_LEVELS, OVZ_NOZOLOGIES, allowed_variants, is_allowed
from .roles import require_roles
from .permissions import (
    can_view_child_basic,
    build_child_card_flags,
    should_limit_children_to_own_class,
    has_permission,
    has_role,
    can_view_documents,
    can_upload_documents,
    is_admin,
)

children_bp = Blueprint("children", __name__)


# =========================================================
# HELPERS
# =========================================================
def as_checkbox(form, name: str) -> bool:
    vals = form.getlist(name)
    return ("1" in vals) or ("on" in vals) or ("true" in vals) or ("True" in vals)


def parse_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None




def _document_abs_path(stored_path: str) -> str:
    if not stored_path:
        return ""
    if os.path.isabs(stored_path):
        return stored_path
    upload_root = current_app.config.get("UPLOAD_FOLDER") or os.path.abspath(os.path.join("data", "uploads"))
    return os.path.join(os.path.abspath(upload_root), stored_path)


def _user_can_manage_document(child) -> bool:
    return is_admin() or can_upload_documents(child)


def _render_docx_preview(path: str) -> str:
    from docx import Document as DocxDocument

    doc = DocxDocument(path)
    parts = ['<div class="container-fluid py-3">']
    for p in doc.paragraphs:
        text = (p.text or '').strip()
        if text:
            parts.append(f'<p style="margin-bottom:.5rem; white-space:pre-wrap;">{escape(text)}</p>')
    for table in doc.tables:
        parts.append('<div class="table-responsive"><table class="table table-sm table-bordered">')
        for row in table.rows:
            parts.append('<tr>')
            for cell in row.cells:
                parts.append(f'<td>{escape((cell.text or "").strip())}</td>')
            parts.append('</tr>')
        parts.append('</table></div>')
    if len(parts) == 1:
        parts.append('<div class="text-muted">В документе нет читаемого текста.</div>')
    parts.append('</div>')
    return ''.join(parts)


def _render_xlsx_preview(path: str) -> str:
    wb = load_workbook(path, data_only=True)
    parts = ['<div class="container-fluid py-3">']
    for ws in wb.worksheets:
        parts.append(f'<h6 class="mt-2">{escape(ws.title)}</h6>')
        parts.append('<div class="table-responsive mb-3"><table class="table table-sm table-bordered">')
        max_row = min(ws.max_row or 0, 50)
        max_col = min(ws.max_column or 0, 12)
        if max_row == 0 or max_col == 0:
            parts.append('<tr><td class="text-muted">Пустой лист</td></tr>')
        else:
            for row in ws.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=max_col, values_only=True):
                parts.append('<tr>')
                for val in row:
                    txt = '' if val is None else str(val)
                    parts.append(f'<td>{escape(txt)}</td>')
                parts.append('</tr>')
        parts.append('</table></div>')
        if (ws.max_row or 0) > 50 or (ws.max_column or 0) > 12:
            parts.append('<div class="small text-muted mb-3">Показана только часть таблицы для предпросмотра.</div>')
    parts.append('</div>')
    return ''.join(parts)


def _render_text_preview(path: str) -> str:
    for enc in ('utf-8', 'cp1251', 'latin-1'):
        try:
            with open(path, 'r', encoding=enc) as f:
                text = f.read()
            break
        except Exception:
            text = None
    if text is None:
        text = 'Не удалось прочитать текст документа.'
    return f'<div class="container-fluid py-3"><pre style="white-space:pre-wrap;">{escape(text[:200000])}</pre></div>'

def _registry_filter_state(year=None, allow_only_own_class: bool = False):
    q_text = (request.args.get("q") or "").strip()
    selected_grade_raw = (request.args.get("grade") or "").strip()
    selected_class_id = request.args.get("class_id", type=int)

    selected_grade = None
    if selected_grade_raw:
        try:
            selected_grade = int(selected_grade_raw)
        except ValueError:
            selected_grade = None

    classes_query = SchoolClass.query
    if year:
        classes_query = classes_query.filter(SchoolClass.academic_year_id == year.id)
    if allow_only_own_class:
        classes_query = classes_query.filter(SchoolClass.teacher_user_id == current_user.id)

    all_classes = (
        classes_query
        .order_by(
            SchoolClass.grade.asc().nullslast(),
            SchoolClass.letter.asc().nullslast(),
            SchoolClass.name.asc(),
        )
        .all()
    )

    grades = []
    for c in all_classes:
        if c.grade is not None and c.grade not in grades:
            grades.append(c.grade)

    classes = [c for c in all_classes if selected_grade is None or c.grade == selected_grade]

    selected_class = None
    if selected_class_id:
        for c in all_classes:
            if c.id == selected_class_id:
                selected_class = c
                break

    if selected_class and selected_grade is None and selected_class.grade is not None:
        selected_grade = selected_class.grade
        classes = [c for c in all_classes if c.grade == selected_grade]

    selected_class_name = selected_class.name if selected_class else ""

    return {
        "q_text": q_text,
        "selected_grade": selected_grade,
        "selected_grade_raw": str(selected_grade) if selected_grade is not None else "",
        "selected_class_id": selected_class_id,
        "selected_class_name": selected_class_name,
        "classes": classes,
        "grades": grades,
    }


def _match_fio_query(child: Child, q_text: str) -> bool:
    if not q_text:
        return True
    hay = " ".join([
        child.last_name or "",
        child.first_name or "",
        child.middle_name or "",
        child.current_class_name or "",
    ]).lower()
    return q_text.lower() in hay


def parse_int(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except Exception:
        return None


def split_class_name(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return (None, None)

    m = re.match(r"^(\d{1,2})\s*(.*)$", raw)
    if not m:
        return (None, raw or None)

    grade = parse_int(m.group(1))
    letter = (m.group(2) or "").strip() or None
    return (grade, letter)

def normalize_class_name(raw: str):
    s = (raw or "").strip().upper()
    s = s.replace(" ", "")
    s = s.replace("-", "")
    return s or None

def _ensure_can_edit():
    if getattr(current_user, "role", "VIEWER") == "VIEWER":
        abort(403)


def _get_current_year():
    return AcademicYear.query.filter_by(is_current=True).first()


def _calc_retention_until(academic_year):
    if academic_year and academic_year.end_date:
        try:
            return academic_year.end_date.replace(year=academic_year.end_date.year + 7)
        except Exception:
            return None
    return None

def _sync_class_teacher_role(user_id):
    if not user_id:
        return

    user = User.query.get(user_id)
    if not user:
        return

    role = Role.query.filter_by(code="CLASS_TEACHER").first()
    if not role:
        return

    has_any_class = (
        SchoolClass.query
        .filter(SchoolClass.teacher_user_id == user.id)
        .first()
        is not None
    )

    existing_link = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()

    if has_any_class and not existing_link:
        db.session.add(UserRole(user_id=user.id, role_id=role.id))

    if not has_any_class and existing_link:
        db.session.delete(existing_link)

def _get_class_teacher_id(child: Child):
    if child.current_class:
        return child.current_class.teacher_user_id
    return None


def _can_edit_profile_admin_only(child: Child) -> bool:
    return getattr(current_user, "role", None) == "ADMIN"


def _can_edit_social_passport(child: Child) -> bool:
    if getattr(current_user, "role", None) == "ADMIN":
        return True

    class_teacher_id = _get_class_teacher_id(child)
    return class_teacher_id is not None and current_user.id == class_teacher_id


def _sync_child_az_flag(child: Child):
    has_open = (
        Debt.query
        .filter_by(child_id=child.id, status="OPEN")
        .first()
        is not None
    )
    child.is_az = bool(has_open)


def _get_or_create_social(child: Child) -> ChildSocial:
    if child.social:
        return child.social

    social = ChildSocial(child_id=child.id)
    db.session.add(social)
    db.session.flush()
    return social


def _get_parent_by_relation(child: Child, relation_type: str):
    for link in (child.parent_links or []):
        if link.relation_type == relation_type:
            return link.parent
    return None


def _set_parent_relation(child: Child, relation_type: str, fio: str, phone: str):
    fio = (fio or "").strip()
    phone = (phone or "").strip()

    existing_link = None
    for link in (child.parent_links or []):
        if link.relation_type == relation_type:
            existing_link = link
            break

    if not fio and not phone:
        if existing_link:
            db.session.delete(existing_link)
        return

    if existing_link and existing_link.parent:
        existing_link.parent.fio = fio or existing_link.parent.fio
        existing_link.parent.phone = phone or None
        return

    parent = Parent(
        fio=fio or relation_type,
        phone=phone or None,
    )
    db.session.add(parent)
    db.session.flush()

    link = ChildParent(
        child_id=child.id,
        parent_id=parent.id,
        relation_type=relation_type,
        is_legal_representative=True,
    )
    db.session.add(link)


def _export_children_xlsx(title: str, children):
    wb = Workbook()
    ws = wb.active
    ws.title = "Реестр"

    ws.append(["№", "ФИО", "Класс", "Дата рождения", "Мама", "Телефон мамы", "Папа", "Телефон папы"])

    for idx, ch in enumerate(children, start=1):
        mother = _get_parent_by_relation(ch, "mother")
        father = _get_parent_by_relation(ch, "father")

        ws.append([
            idx,
            ch.fio,
            ch.current_class_name or "—",
            ch.birth_date.strftime("%d.%m.%Y") if ch.birth_date else "",
            mother.fio if mother else "",
            mother.phone if mother else "",
            father.fio if father else "",
            father.phone if father else "",
        ])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    safe_name = re.sub(r"[^0-9A-Za-zА-Яа-я_\- ]+", "", title).strip().replace(" ", "_")
    return send_file(
        bio,
        as_attachment=True,
        download_name=f"{safe_name}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def _children_base_query_for_current_year():
    year = _get_current_year()

    q = db.session.query(Child)

    if year:
        q = (
            q.outerjoin(
                ChildEnrollment,
                (ChildEnrollment.child_id == Child.id)
                & (ChildEnrollment.academic_year_id == year.id)
                & (ChildEnrollment.ended_at.is_(None))
            )
            .outerjoin(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        )
    else:
        q = (
            q.outerjoin(
                ChildEnrollment,
                (ChildEnrollment.child_id == Child.id)
                & (ChildEnrollment.ended_at.is_(None))
            )
            .outerjoin(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        )

    return q, year

def parse_aoop_variant(raw_value: str):
    text = (raw_value or "").strip().upper()
    if not text:
        return None

    # Ищем вариант вроде 7.1, 8.2, 6.4
    m = re.search(r'(\d\.\d)', text)
    if m:
        return m.group(1)

    # Ищем одиночные коды вроде "12"
    m2 = re.search(r'\b(\d{1,2})\b', text)
    if m2:
        return m2.group(1)

    return text

def apply_aoop_to_child(child, social, aoop_raw: str):
    variant_code = parse_aoop_variant(aoop_raw)
    if not variant_code:
        return

    social.aoop_variant_text = AOOP_FULL_NAMES.get(variant_code, str(aoop_raw).strip())

    if variant_code not in AOOP_FULL_NAMES:
        return

    group_code = variant_code.split(".")[0]
    if group_code not in AOOP_TO_OVZ:
        return

    child.is_ovz = True
    child.ovz_level = "NOO"
    child.ovz_nosology = AOOP_TO_OVZ[group_code]["nosology"]

    try:
        child.ovz_variant = int(variant_code.split(".")[1])
    except Exception:
        child.ovz_variant = None

# =========================================================
# HOME
# =========================================================
@children_bp.route("/")
@login_required
def home():
    return redirect(url_for("main.dashboard"))


# =========================================================
# CHILDREN LIST
# =========================================================
@children_bp.route("/children")
@login_required
def list_children():
    query, year = _children_base_query_for_current_year()
    limit_to_own = should_limit_children_to_own_class()
    filters = _registry_filter_state(year, allow_only_own_class=limit_to_own)

    if limit_to_own:
        query = query.filter(SchoolClass.teacher_user_id == current_user.id)
    if filters["selected_grade"] is not None:
        query = query.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        query = query.filter(SchoolClass.id == filters["selected_class_id"])

    children = (
        query
        .order_by(SchoolClass.name.asc(), Child.last_name.asc(), Child.first_name.asc())
        .all()
    )

    if filters["q_text"]:
        children = [ch for ch in children if _match_fio_query(ch, filters["q_text"])]

    return render_template(
        "children_list.html",
        children=children,
        q=filters["q_text"],
        selected_grade=filters["selected_grade"],
        selected_class_id=filters["selected_class_id"],
        classes=filters["classes"],
        grades=filters["grades"],
    )


# =========================================================
# NEW CHILD
# =========================================================
@children_bp.route("/children/new", methods=["GET", "POST"])
@login_required
def new_child():
    if not has_permission("child_create"):
        abort(403)
    year = _get_current_year()
    school_classes = []
    if year:
        school_classes = (
            SchoolClass.query
            .filter(SchoolClass.academic_year_id == year.id)
            .order_by(SchoolClass.name.asc())
            .all()
        )

    if request.method == "POST":
        _ensure_can_edit()

        last_name = (request.form.get("last_name") or "").strip()
        first_name = (request.form.get("first_name") or "").strip()
        middle_name = (request.form.get("middle_name") or "").strip() or None
        birth_date = parse_date(request.form.get("birth_date"))
        reg_address = (request.form.get("reg_address") or "").strip() or None
        notes = (request.form.get("notes") or "").strip() or None

        if not last_name or not first_name:
            flash("Укажите фамилию и имя", "danger")
            return render_template("child_new.html", school_classes=school_classes)

        child = Child(
            last_name=last_name,
            first_name=first_name,
            middle_name=middle_name,
            birth_date=birth_date,
            reg_address=reg_address,
            notes=notes,
        )
        db.session.add(child)
        db.session.flush()

        _set_parent_relation(
            child,
            "mother",
            request.form.get("mother_fio"),
            request.form.get("mother_phone"),
        )
        _set_parent_relation(
            child,
            "father",
            request.form.get("father_fio"),
            request.form.get("father_phone"),
        )

        _get_or_create_social(child)

        school_class_id = request.form.get("school_class_id", type=int)
        if year and school_class_id:
            sc = (
                SchoolClass.query
                .filter(
                    SchoolClass.id == school_class_id,
                    SchoolClass.academic_year_id == year.id
                )
                .first()
            )
            if sc:
                en = ChildEnrollment(
                    child_id=child.id,
                    academic_year_id=year.id,
                    school_class_id=sc.id,
                    status="ACTIVE",
                )
                db.session.add(en)

        db.session.commit()
        flash("Ребёнок добавлен", "success")
        return redirect(url_for("children.child_card", child_id=child.id))

    return render_template("child_new.html", school_classes=school_classes)


# =========================================================
# CHILD CARD
# =========================================================
@children_bp.route("/children/<int:child_id>")
@login_required
def child_card(child_id: int):
    child = Child.query.get_or_404(child_id)

    if not can_view_child_basic(child):
        abort(403)

    subjects = Subject.query.order_by(Subject.name.asc()).all()

    social = child.social or _get_or_create_social(child)
    db.session.flush()

    mother = _get_parent_by_relation(child, "mother")
    father = _get_parent_by_relation(child, "father")

    selected_year_id = request.args.get("academic_year_id", type=int)
    year = _get_current_year()
    if not selected_year_id and year:
        selected_year_id = year.id

    docs = [d for d in (child.documents or []) if not getattr(d, "is_deleted_soft", False) and not getattr(d, "is_hidden_by_retention", False)]
    if selected_year_id:
        docs = [d for d in docs if (d.academic_year_id == selected_year_id or d.academic_year_id is None)]

    def dt(x):
        return (x.doc_type or "").strip().upper()

    documents_ovz = [d for d in docs if dt(d) == "OVZ"]
    documents_vshu = [d for d in docs if dt(d) == "VSHU"]
    documents_low = [d for d in docs if dt(d) == "LOW"]
    documents_az = [d for d in docs if dt(d) == "AZ"]
    documents_mse = [d for d in docs if dt(d) == "MSE"]
    documents_ipra = [d for d in docs if dt(d) == "IPRA"]
    documents_general = [d for d in docs if dt(d) == "GENERAL"]
    documents_disabled = [d for d in docs if dt(d) == "DISABLED"]

    ovz_allowed = allowed_variants(child.ovz_level, child.ovz_nosology)

    open_debts = (
        Debt.query
        .join(Subject, Debt.subject_id == Subject.id)
        .filter(Debt.child_id == child.id, Debt.status == "OPEN")
        .order_by(Debt.due_date.is_(None), Debt.due_date.asc(), Debt.created_at.desc())
        .all()
    )

    closed_debts = (
        Debt.query
        .join(Subject, Debt.subject_id == Subject.id)
        .filter(Debt.child_id == child.id, Debt.status == "CLOSED")
        .order_by(Debt.closed_at.is_(None), Debt.closed_at.desc(), Debt.created_at.desc())
        .all()
    )

    _sync_child_az_flag(child)
    db.session.commit()

    comments = (
        ChildComment.query
        .filter_by(child_id=child.id)
        .order_by(ChildComment.created_at.desc())
        .all()
    )

    events = (
        ChildEvent.query
        .filter_by(child_id=child.id)
        .order_by(ChildEvent.created_at.desc())
        .all()
    )

    incidents = (
        db.session.query(Incident)
        .join(IncidentChild, IncidentChild.incident_id == Incident.id)
        .filter(IncidentChild.child_id == child.id)
        .order_by(Incident.occurred_at.desc())
        .all()
    )

    school_classes = []
    current_year_id = selected_year_id
    if year:
        school_classes = (
            SchoolClass.query
            .filter(SchoolClass.academic_year_id == year.id)
            .order_by(SchoolClass.name.asc())
            .all()
        )

    show_ovz = child.is_ovz or bool(documents_ovz)
    show_disabled = (
        child.is_disabled
        or bool(child.disability_mse)
        or bool(child.disability_from)
        or bool(child.disability_to)
        or bool(child.disability_ipra)
        or bool(documents_mse)
        or bool(documents_ipra)
        or bool(documents_disabled)
    )
    show_vshu = child.is_vshu or bool(social.vshu_since and not social.vshu_removed_at) or bool(documents_vshu)
    show_low = child.is_low or bool(child.low_subjects) or bool(child.low_notes) or bool(documents_low)
    show_az = bool(open_debts) or bool(closed_debts) or bool(documents_az)
    show_general = bool(documents_general)

    ovz_level_label = OVZ_LEVEL_LABELS.get(child.ovz_level, child.ovz_level)
    ovz_nosology_label = OVZ_NOZOLOGY_LABELS.get(child.ovz_nosology, child.ovz_nosology)

    transfer_history = (
        ChildTransferHistory.query
        .filter_by(child_id=child.id)
        .order_by(ChildTransferHistory.transfer_date.desc().nullslast(), ChildTransferHistory.created_at.desc())
        .all()
    )
    enrollment_history = (
        ChildEnrollment.query
        .filter_by(child_id=child.id)
        .order_by(ChildEnrollment.enrolled_at.desc())
        .all()
    )
    control_results_q = ControlWorkResult.query.filter_by(child_id=child.id)
    if selected_year_id:
        control_results_q = control_results_q.filter_by(academic_year_id=selected_year_id)
    control_results = (
        control_results_q
        .order_by(ControlWorkResult.created_at.desc())
        .limit(50)
        .all()
    )
    olympiad_q = OlympiadResult.query.filter_by(child_id=child.id, is_archived=False)
    if selected_year_id:
        olympiad_q = olympiad_q.filter_by(academic_year_id=selected_year_id)
    olympiad_results = olympiad_q.order_by(OlympiadResult.created_at.desc()).limit(100).all()
    academic_years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()

    flags = build_child_card_flags(child)

    return render_template(
        "child_card.html",
        child=child,
        social=social,
        mother=mother,
        father=father,
        debts=child.debts,
        open_debts=open_debts,
        closed_debts=closed_debts,
        documents=docs,
        documents_ovz=documents_ovz,
        documents_vshu=documents_vshu,
        documents_low=documents_low,
        documents_az=documents_az,
        documents_mse=documents_mse,
        documents_ipra=documents_ipra,
        documents_general=documents_general,
        documents_disabled=documents_disabled,
        subjects=subjects,
        ovz_levels=OVZ_LEVELS,
        ovz_nozologies=OVZ_NOZOLOGIES,
        ovz_allowed=ovz_allowed,
        school_classes=school_classes,
        current_year_id=current_year_id,
        current_year_name=year.name if year else None,
        academic_years=academic_years,
        selected_year_id=selected_year_id,
        incidents=incidents,
        comments=comments,
        events=events,
        transfer_history=transfer_history,
        enrollment_history=enrollment_history,
        control_results=control_results,
        olympiad_results=olympiad_results,
        today=date.today(),
        datetime=datetime,
        show_ovz=show_ovz,
        show_disabled=show_disabled,
        show_vshu=show_vshu,
        show_low=show_low,
        show_az=show_az,
        show_general=show_general,
        ovz_level_label=ovz_level_label,
        ovz_nosology_label=ovz_nosology_label,
        **flags
    )
# =========================================================
# DOCUMENTS
# =========================================================
@children_bp.route("/children/<int:child_id>/documents/upload", methods=["POST"])
@login_required
def upload_child_document(child_id: int):
    _ensure_can_edit()

    child = Child.query.get_or_404(child_id)

    file = request.files.get("file")
    doc_type = (request.form.get("doc_type") or "").strip().upper()
    debt_id = request.form.get("debt_id", type=int)

    if not file or not file.filename:
        flash("Выберите файл", "danger")
        return redirect(url_for("children.child_card", child_id=child.id))

    if not doc_type:
        doc_type = "GENERAL"

    allowed_types = {"OVZ", "MSE", "IPRA", "VSHU", "LOW", "AZ", "GENERAL", "DISABLED"}
    if doc_type not in allowed_types:
        doc_type = "GENERAL"

    upload_root = current_app.config.get("UPLOAD_FOLDER")
    if not upload_root:
        flash("Не настроена папка для загрузки файлов", "danger")
        return redirect(url_for("children.child_card", child_id=child.id))

    child_folder = os.path.join(upload_root, str(child.id))
    os.makedirs(child_folder, exist_ok=True)

    original_name = file.filename
    safe_name = re.sub(r"[^0-9A-Za-zА-Яа-я._ -]+", "_", original_name).strip()
    if not safe_name:
        safe_name = f"document_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    stored_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}_{safe_name}"
    stored_path = os.path.join(child_folder, stored_name)

    file.save(stored_path)

    current_year = _get_current_year()
    retention_until = None
    if current_year and current_year.end_date:
        try:
            retention_until = current_year.end_date.replace(year=current_year.end_date.year + 7)
        except Exception:
            retention_until = None

    doc = Document(
        child_id=child.id,
        debt_id=debt_id if debt_id else None,
        academic_year_id=current_year.id if current_year else None,
        doc_type=doc_type,
        original_name=original_name,
        stored_path=stored_path,
        filename=stored_name,
        title=original_name,
        uploaded_by_user_id=getattr(current_user, "id", None),
        uploaded_at=datetime.utcnow(),
        retention_until=retention_until,
    )

    db.session.add(doc)
    db.session.commit()

    flash("Документ загружен", "success")
    return redirect(url_for("children.child_card", child_id=child.id))


@children_bp.route("/documents/<int:doc_id>/download")
@login_required
def download_document(doc_id: int):
    doc = Document.query.get_or_404(doc_id)
    child = Child.query.get_or_404(doc.child_id)

    if not (can_view_documents(child) or can_upload_documents(child) or is_admin()):
        abort(403)

    abs_path = _document_abs_path(doc.stored_path)
    if not abs_path or not os.path.isfile(abs_path):
        flash("Файл не найден", "danger")
        return redirect(url_for("children.child_card", child_id=doc.child_id))

    return send_file(
        abs_path,
        as_attachment=True,
        download_name=doc.original_name or os.path.basename(abs_path)
    )


@children_bp.route("/documents/<int:doc_id>/view")
@login_required
def view_document(doc_id: int):
    doc = Document.query.get_or_404(doc_id)
    child = Child.query.get_or_404(doc.child_id)

    if not (can_view_documents(child) or can_upload_documents(child) or is_admin()):
        abort(403)

    abs_path = _document_abs_path(doc.stored_path)
    if not abs_path or not os.path.isfile(abs_path):
        abort(404)

    mime, _ = mimetypes.guess_type(abs_path)
    mime = mime or "application/octet-stream"
    resp = send_file(abs_path, mimetype=mime, as_attachment=False)
    resp.headers["Content-Disposition"] = "inline"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@children_bp.route("/documents/<int:doc_id>/preview")
@login_required
def preview_document(doc_id: int):
    doc = Document.query.get_or_404(doc_id)
    child = Child.query.get_or_404(doc.child_id)

    if not (can_view_documents(child) or can_upload_documents(child) or is_admin()):
        abort(403)

    abs_path = _document_abs_path(doc.stored_path)
    if not abs_path or not os.path.isfile(abs_path):
        abort(404)

    ext = os.path.splitext(doc.original_name or abs_path)[1].lower()
    html = None
    inline_url = None
    mode = "html"
    preview_error = None

    try:
        if ext in {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.txt', '.csv'}:
            if ext in {'.txt', '.csv'}:
                html = _render_text_preview(abs_path)
            else:
                mode = "iframe"
                inline_url = url_for('children.view_document', doc_id=doc.id)
        elif ext == '.docx':
            html = _render_docx_preview(abs_path)
        elif ext == '.xlsx':
            html = _render_xlsx_preview(abs_path)
        else:
            preview_error = 'Для этого формата доступно скачивание. Полноценный просмотр в окне не поддерживается.'
    except Exception:
        preview_error = 'Не удалось построить предпросмотр документа.'

    return render_template(
        'document_preview.html',
        doc=doc,
        mode=mode,
        inline_url=inline_url,
        preview_html=html,
        preview_error=preview_error,
    )


@children_bp.route("/documents/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete_document(doc_id: int):
    doc = Document.query.get_or_404(doc_id)
    child_id = doc.child_id
    child = Child.query.get_or_404(child_id)

    if not _user_can_manage_document(child):
        abort(403)

    doc.is_deleted_soft = True
    doc.deleted_at = datetime.utcnow()
    doc.deleted_by = getattr(current_user, "id", None)
    db.session.commit()

    flash("Документ скрыт из карточки. Файл сохранён в архиве.", "success")
    return redirect(url_for("children.child_card", child_id=child_id))

# =========================================================
# DELETE CHILD
# =========================================================
@children_bp.route("/children/<int:child_id>/delete", methods=["POST"])
@require_roles("ADMIN")
def delete_child(child_id: int):
    child = Child.query.get_or_404(child_id)
    child.status = "ARCHIVED"
    child.archived_at = datetime.utcnow()

    active = (
        ChildEnrollment.query
        .filter(ChildEnrollment.child_id == child.id, ChildEnrollment.ended_at.is_(None))
        .all()
    )
    for en in active:
        en.status = "ARCHIVED"
        en.ended_at = datetime.utcnow()
        db.session.add(ChildTransferHistory(
            child_id=child.id,
            from_academic_year_id=en.academic_year_id,
            to_academic_year_id=None,
            from_class_id=en.school_class_id,
            to_class_id=None,
            transfer_type="ARCHIVED",
            transfer_date=date.today(),
            comment="Архивирование карточки вместо физического удаления",
            created_by=getattr(current_user, "id", None),
        ))

    db.session.add(ChildEvent(
        child_id=child.id,
        author_id=getattr(current_user, "id", None),
        event_type="EXPEL",
        from_class=child.current_class_name,
        to_class=None,
        promotion_kind="ARCHIVED",
        reason="Архивирование карточки",
        created_at=datetime.utcnow(),
    ))

    db.session.commit()
    flash("Карточка ученика переведена в архив. Документы и история сохранены.", "success")
    return redirect(url_for("children.list_children"))


# =========================================================
# FLAGS
# =========================================================
@children_bp.route("/children/<int:child_id>/flags", methods=["POST"])
@login_required
def update_child_flags(child_id: int):
    _ensure_can_edit()

    child = Child.query.get_or_404(child_id)

    child.is_ovz = as_checkbox(request.form, "is_ovz")
    child.is_disabled = as_checkbox(request.form, "is_disabled")
    child.is_vshu = as_checkbox(request.form, "is_vshu")
    child.is_low = as_checkbox(request.form, "is_low")

    child.disability_mse = (request.form.get("disability_mse") or "").strip() or None
    child.disability_from = parse_date(request.form.get("disability_from"))
    child.disability_to = parse_date(request.form.get("disability_to"))

    if not child.is_disabled:
        child.disability_mse = None
        child.disability_from = None
        child.disability_to = None

    child.low_subjects = (request.form.get("low_subjects") or "").strip() or None
    child.low_notes = (request.form.get("low_notes") or "").strip() or None

    if child.is_ovz:
        child.ovz_level = (request.form.get("ovz_level") or "").strip().upper() or None
        child.ovz_nosology = (request.form.get("ovz_nosology") or "").strip().upper() or None

        v_raw = (request.form.get("ovz_variant") or "").strip()
        child.ovz_variant = int(v_raw) if v_raw.isdigit() else None

        if child.ovz_variant and not is_allowed(child.ovz_level, child.ovz_nosology, child.ovz_variant):
            child.ovz_variant = None
    else:
        child.ovz_level = None
        child.ovz_nosology = None
        child.ovz_variant = None

    _sync_child_az_flag(child)

    db.session.commit()
    flash("Сохранено", "success")
    return redirect(url_for("children.child_card", child_id=child_id))


# =========================================================
# PROFILE UPDATE
# =========================================================
@children_bp.route("/children/<int:child_id>/profile", methods=["POST"])
@login_required
def update_child_profile(child_id: int):
    child = Child.query.get_or_404(child_id)

    if not _can_edit_profile_admin_only(child):
        abort(403)

    child.last_name = (request.form.get("last_name") or "").strip()
    child.first_name = (request.form.get("first_name") or "").strip()
    child.middle_name = (request.form.get("middle_name") or "").strip() or None
    child.birth_date = parse_date(request.form.get("birth_date"))
    child.reg_address = (request.form.get("reg_address") or "").strip() or None
    child.notes = (request.form.get("notes") or "").strip() or None
    child.education_form = request.form.get("education_form") or None
    child.reg_address = request.form.get("reg_address") or None
    child.temporary_address = request.form.get("temporary_address") or None
    child.actual_address = request.form.get("actual_address") or None

    db.session.commit()
    flash("Основные данные обновлены", "success")
    return redirect(url_for("children.child_card", child_id=child.id))


# =========================================================
# SOCIAL PASSPORT
# =========================================================
@children_bp.route("/children/<int:child_id>/social-passport", methods=["POST"])
@login_required
def update_child_social_passport(child_id: int):
    child = Child.query.get_or_404(child_id)

    if not _can_edit_social_passport(child):
        abort(403)

    social = _get_or_create_social(child)

    _set_parent_relation(
        child,
        "mother",
        request.form.get("mother_fio"),
        request.form.get("mother_phone"),
    )
    _set_parent_relation(
        child,
        "father",
        request.form.get("father_fio"),
        request.form.get("father_phone"),
    )

    child.reg_address = (request.form.get("reg_address") or "").strip() or None

    social.family_status = (request.form.get("family_status") or "").strip() or None
    social.living_conditions = (request.form.get("living_conditions") or "").strip() or None
    social.social_risk = (request.form.get("social_risk") or "").strip() or None
    social.aoop_variant_text = (request.form.get("aoop_variant_text") or "").strip() or None

    child.is_ovz = as_checkbox(request.form, "is_ovz")
    child.ovz_level = (request.form.get("ovz_level") or "").strip().upper() or None
    child.ovz_nosology = (request.form.get("ovz_nosology") or "").strip().upper() or None
    v_raw = (request.form.get("ovz_variant") or "").strip()
    child.ovz_variant = int(v_raw) if v_raw.isdigit() else None
    child.ovz_doc_number = (request.form.get("ovz_doc_number") or "").strip() or None
    child.ovz_doc_date = parse_date(request.form.get("ovz_doc_date"))
    if child.is_ovz and child.ovz_variant and not is_allowed(child.ovz_level, child.ovz_nosology, child.ovz_variant):
        child.ovz_variant = None
    if not child.is_ovz:
        child.ovz_level = None
        child.ovz_nosology = None
        child.ovz_variant = None
        child.ovz_doc_number = None
        child.ovz_doc_date = None

    child.is_disabled = as_checkbox(request.form, "is_disabled")
    child.disability_mse = (request.form.get("disability_mse") or "").strip() or None
    child.disability_from = parse_date(request.form.get("disability_from"))
    child.disability_to = parse_date(request.form.get("disability_to"))
    child.disability_ipra = (request.form.get("disability_ipra") or "").strip() or None
    if not child.is_disabled:
        child.disability_mse = None
        child.disability_from = None
        child.disability_to = None
        child.disability_ipra = None

    social.vshu_since = parse_date(request.form.get("vshu_since"))
    social.vshu_reason = (request.form.get("vshu_reason") or "").strip() or None

    social.kdn_since = parse_date(request.form.get("kdn_since"))
    social.kdn_reason = (request.form.get("kdn_reason") or "").strip() or None

    social.pdn_since = parse_date(request.form.get("pdn_since"))
    social.pdn_reason = (request.form.get("pdn_reason") or "").strip() or None

    social.vshu_removed_at = parse_date(request.form.get("vshu_removed_at"))
    social.vshu_remove_reason = (request.form.get("vshu_remove_reason") or "").strip() or None

    child.is_vshu = bool(social.vshu_since and not social.vshu_removed_at)

    social.has_disability_parents = as_checkbox(request.form, "has_disability_parents")
    social.has_large_family = as_checkbox(request.form, "has_large_family")
    social.has_low_income_family = as_checkbox(request.form, "has_low_income_family")
    social.has_guardianship = as_checkbox(request.form, "has_guardianship")
    social.has_orphan_status = as_checkbox(request.form, "has_orphan_status")
    social.has_refugee_status = as_checkbox(request.form, "has_refugee_status")

    social.is_socially_dangerous = as_checkbox(request.form, "is_socially_dangerous")
    social.is_hard_life = as_checkbox(request.form, "is_hard_life")

    social.notes = (request.form.get("social_notes") or "").strip() or None
    social.updated_at = datetime.utcnow()

    db.session.commit()
    flash("Данные социального паспорта обновлены", "success")
    return redirect(url_for("children.child_card", child_id=child.id))


# =========================================================
# DEBTS
# =========================================================
@children_bp.route("/children/<int:child_id>/debts/add", methods=["POST"])
@login_required
def add_debt(child_id: int):
    _ensure_can_edit()

    child = Child.query.get_or_404(child_id)

    subject_id = (request.form.get("subject_id") or "").strip()
    detected_date = parse_date(request.form.get("detected_date")) or date.today()
    due_date = parse_date(request.form.get("due_date"))

    if not subject_id.isdigit():
        flash("Не выбран предмет", "danger")
        return redirect(url_for("children.child_card", child_id=child.id))

    debt = Debt(
        child_id=child.id,
        subject_id=int(subject_id),
        detected_date=detected_date,
        due_date=due_date,
        status="OPEN",
        created_at=datetime.utcnow(),
    )

    db.session.add(debt)
    db.session.flush()

    _sync_child_az_flag(child)

    db.session.commit()
    flash("Задолженность добавлена", "success")
    return redirect(url_for("children.child_card", child_id=child.id))


@children_bp.route("/debts/<int:debt_id>/close", methods=["POST"])
@login_required
def close_debt(debt_id: int):
    _ensure_can_edit()

    debt = Debt.query.get_or_404(debt_id)
    child = Child.query.get_or_404(debt.child_id)

    if debt.status != "CLOSED":
        debt.status = "CLOSED"
        debt.closed_at = datetime.utcnow()
        debt.closed_by_user_id = current_user.id

    _sync_child_az_flag(child)

    db.session.commit()
    flash("Задолженность закрыта", "success")
    return redirect(url_for("children.child_card", child_id=child.id))


@children_bp.route("/debts/<int:debt_id>/reopen", methods=["POST"])
@login_required
def reopen_debt(debt_id: int):
    _ensure_can_edit()

    debt = Debt.query.get_or_404(debt_id)
    child = Child.query.get_or_404(debt.child_id)

    if debt.status != "OPEN":
        debt.status = "OPEN"
        debt.closed_at = None
        debt.closed_by_user_id = None

    _sync_child_az_flag(child)

    db.session.commit()
    flash("Задолженность возвращена в открытые", "success")
    return redirect(url_for("children.child_card", child_id=child.id))


# =========================================================
# COMMENTS
# =========================================================
@children_bp.route("/children/<int:child_id>/comments", methods=["POST"])
@login_required
def add_child_comment(child_id: int):
    child = Child.query.get_or_404(child_id)

    text = (request.form.get("comment_text") or "").strip()
    if not text:
        return redirect(url_for("children.child_card", child_id=child_id))

    c = ChildComment(
        child_id=child.id,
        author_id=current_user.id,
        text=text
    )

    db.session.add(c)
    db.session.commit()

    return redirect(url_for("children.child_card", child_id=child_id))


@children_bp.route("/comments/<int:comment_id>/delete", methods=["POST"])
@login_required
def delete_child_comment(comment_id: int):
    c = ChildComment.query.get_or_404(comment_id)

    if not (current_user.role == "ADMIN" or c.author_id == current_user.id):
        abort(403)

    child_id = c.child_id
    db.session.delete(c)
    db.session.commit()

    return redirect(url_for("children.child_card", child_id=child_id))


# =========================================================
# TRANSFER / EXPEL
# =========================================================
@children_bp.route("/children/<int:child_id>/transfer", methods=["POST"])
@require_roles("ADMIN")
def transfer_child(child_id: int):
    child = Child.query.get_or_404(child_id)

    is_repeat = (request.form.get("is_repeat") == "1")
    note = (request.form.get("note") or "").strip() or None

    year = _get_current_year()
    if not year:
        flash("Не найден текущий учебный год", "danger")
        return redirect(url_for("children.child_card", child_id=child_id))

    en = (
        ChildEnrollment.query
        .filter(
            ChildEnrollment.child_id == child.id,
            ChildEnrollment.academic_year_id == year.id,
            ChildEnrollment.ended_at.is_(None)
        )
        .first()
    )

    old_class = child.current_class_name or "—"

    if is_repeat:
        db.session.add(ChildEvent(
            child_id=child.id,
            author_id=current_user.id,
            event_type="REPEAT",
            from_class=old_class,
            to_class=old_class,
            reason=note,
            created_at=datetime.utcnow(),
        ))
        db.session.commit()
        flash("Сохранено", "success")
        return redirect(url_for("children.child_card", child_id=child_id))

    school_class_id = request.form.get("school_class_id")
    if not (school_class_id and str(school_class_id).isdigit()):
        flash("Выберите класс из реестра", "danger")
        return redirect(url_for("children.child_card", child_id=child_id))

    sc = (
        SchoolClass.query
        .filter(
            SchoolClass.id == int(school_class_id),
            SchoolClass.academic_year_id == year.id
        )
        .first()
    )
    if not sc:
        flash("Выбранный класс не найден в текущем учебном году", "danger")
        return redirect(url_for("children.child_card", child_id=child_id))

    if en:
        en.ended_at = datetime.utcnow()
        en.status = "TRANSFERRED"

    new_en = ChildEnrollment(
        child_id=child.id,
        academic_year_id=year.id,
        school_class_id=sc.id,
        status="ACTIVE"
    )
    db.session.add(new_en)

    db.session.add(ChildEvent(
        child_id=child.id,
        author_id=current_user.id,
        event_type="TRANSFER",
        from_class=old_class,
        to_class=sc.name,
        reason=note,
        created_at=datetime.utcnow(),
    ))

    db.session.commit()
    flash("Сохранено", "success")
    return redirect(url_for("children.child_card", child_id=child_id))


@children_bp.route("/children/<int:child_id>/expel", methods=["POST"])
@require_roles("ADMIN")
def expel_child(child_id: int):
    child = Child.query.get_or_404(child_id)

    note = (request.form.get("note") or "").strip() or None
    to_where = (request.form.get("to_where") or "").strip() or None
    old_class = child.current_class_name or "—"

    year = _get_current_year()
    if year:
        en = (
            ChildEnrollment.query
            .filter(
                ChildEnrollment.child_id == child.id,
                ChildEnrollment.academic_year_id == year.id,
                ChildEnrollment.ended_at.is_(None)
            )
            .first()
        )
        if en:
            en.ended_at = datetime.utcnow()
            en.status = "EXPELLED"
            en.note = note

    db.session.add(
        ChildEvent(
            child_id=child.id,
            author_id=current_user.id,
            event_type="EXPEL",
            from_class=old_class,
            to_class=to_where,
            reason=note,
            created_at=datetime.utcnow(),
        )
    )

    db.session.commit()
    flash("Ребёнок отчислен", "success")
    return redirect(url_for("children.child_card", child_id=child_id))


# =========================================================
# CONTINGENT
# =========================================================
@children_bp.route("/contingent")
@login_required
def contingent():
    year_id = request.args.get("year_id", type=int)
    building_id = request.args.get("building_id", type=int)

    years = AcademicYear.query.order_by(AcademicYear.created_at.desc()).all()
    buildings = Building.query.order_by(Building.name.asc()).all()

    if not year_id:
        y = _get_current_year()
        year_id = y.id if y else None

    q = SchoolClass.query
    if year_id:
        q = q.filter(SchoolClass.academic_year_id == year_id)
    if building_id:
        q = q.filter(SchoolClass.building_id == building_id)

    classes = q.order_by(
        SchoolClass.grade.asc().nullslast(),
        SchoolClass.letter.asc().nullslast(),
        SchoolClass.name.asc()
    ).all()

    teachers = User.query.order_by(User.last_name.asc(), User.first_name.asc()).all()
    teachers_map = {u.id: u for u in teachers}

    class_counts = dict(
        db.session.query(
            ChildEnrollment.school_class_id,
            db.func.count(ChildEnrollment.id)
        )
        .filter(
            ChildEnrollment.academic_year_id == year_id,
            ChildEnrollment.ended_at.is_(None)
        )
        .group_by(ChildEnrollment.school_class_id)
        .all()
    ) if year_id else {}

    transfer_counts = {
        "PROMOTED": 0,
        "CONDITIONAL": 0,
        "REPEAT": 0,
        "EXPELLED": 0,
        "TRANSFERRED_OUT": 0,
        "ARCHIVED": 0,
    }
    if year_id:
        for t_type, cnt in (
            db.session.query(ChildTransferHistory.transfer_type, db.func.count(ChildTransferHistory.id))
            .filter(ChildTransferHistory.from_academic_year_id == year_id)
            .group_by(ChildTransferHistory.transfer_type)
            .all()
        ):
            transfer_counts[t_type] = int(cnt or 0)

    totals = {
        "school": 0,
        "grades_1_4": 0,
        "grades_5_9": 0,
        "grades_10_11": 0,
        "boys": 0,
        "girls": 0,

        "ovz": 0,
        "vshu": 0,
        "kdn": 0,

        "by_grade": {},
        "by_building": {},
        "education_forms": {},

        "classes_total": 0,
        "classes_1_4": 0,
        "classes_5_9": 0,
        "classes_10_11": 0,

        "parallel_stats": {},
        "pending_transfer": 0,
        "transferred_out": 0,
        "repeat_total": 0,
        "conditional_total": 0,
    }

    rows = []

    for c in classes:
        total = int(class_counts.get(c.id, 0))

        children_in_class = (
            Child.query
            .join(ChildEnrollment, ChildEnrollment.child_id == Child.id)
            .filter(
                ChildEnrollment.academic_year_id == year_id,
                ChildEnrollment.school_class_id == c.id,
                ChildEnrollment.ended_at.is_(None)
            )
            .all()
        )

        boys_count = sum(1 for ch in children_in_class if (ch.gender or "").upper() == "М")
        girls_count = sum(1 for ch in children_in_class if (ch.gender or "").upper() == "Ж")

        ovz_count = sum(1 for ch in children_in_class if ch.is_ovz)
        vshu_count = sum(1 for ch in children_in_class if ch.is_vshu or (ch.social and ch.social.vshu_since and not ch.social.vshu_removed_at))
        kdn_count = sum(
            1 for ch in children_in_class
            if ch.social and ch.social.kdn_since
        )

        free = int((c.max_students or 0) - total)

        teacher = teachers_map.get(c.teacher_user_id)
        teacher_fio = teacher.fio if teacher else None
        teacher_phone = teacher.phone if teacher else None

        class_transfer_types = {}
        if year_id and children_in_class:
            child_ids = [ch.id for ch in children_in_class]
            for t_type, cnt in (
                db.session.query(ChildTransferHistory.transfer_type, db.func.count(ChildTransferHistory.id))
                .filter(ChildTransferHistory.child_id.in_(child_ids), ChildTransferHistory.from_academic_year_id == year_id)
                .group_by(ChildTransferHistory.transfer_type)
                .all()
            ):
                class_transfer_types[t_type] = int(cnt or 0)
        transferred_total = sum(class_transfer_types.get(k, 0) for k in ["PROMOTED", "CONDITIONAL", "REPEAT"])
        pending_transfer = max(total - transferred_total, 0)

        rows.append({
            "class": c,
            "total": total,
            "free": free,
            "boys": boys_count,
            "girls": girls_count,
            "teacher_fio": teacher_fio,
            "teacher_phone": teacher_phone,
            "pending_transfer": pending_transfer,
            "promoted": class_transfer_types.get("PROMOTED", 0),
            "conditional": class_transfer_types.get("CONDITIONAL", 0),
            "repeat": class_transfer_types.get("REPEAT", 0),
        })

        totals["school"] += total
        totals["boys"] += boys_count
        totals["girls"] += girls_count

        totals["ovz"] += ovz_count
        totals["vshu"] += vshu_count
        totals["kdn"] += kdn_count

        totals["classes_total"] += 1
        totals["pending_transfer"] += pending_transfer
        totals["transferred_out"] += transferred_total
        totals["repeat_total"] += class_transfer_types.get("REPEAT", 0)
        totals["conditional_total"] += class_transfer_types.get("CONDITIONAL", 0)

        for ch in children_in_class:
            form_name = (ch.education_form or "Не указана").strip()
            totals["education_forms"][form_name] = totals["education_forms"].get(form_name, 0) + 1

        bname = c.building.name if getattr(c, "building", None) else "Без здания"
        totals["by_building"][bname] = totals["by_building"].get(bname, 0) + total

        grade = c.grade
        if grade is not None:
            totals["by_grade"][grade] = totals["by_grade"].get(grade, 0) + total

            if grade not in totals["parallel_stats"]:
                totals["parallel_stats"][grade] = {
                    "classes": 0,
                    "children": 0,
                    "boys": 0,
                    "girls": 0,
                }

            totals["parallel_stats"][grade]["classes"] += 1
            totals["parallel_stats"][grade]["children"] += total
            totals["parallel_stats"][grade]["boys"] += boys_count
            totals["parallel_stats"][grade]["girls"] += girls_count

            if 1 <= grade <= 4:
                totals["grades_1_4"] += total
                totals["classes_1_4"] += 1
            elif 5 <= grade <= 9:
                totals["grades_5_9"] += total
                totals["classes_5_9"] += 1
            elif 10 <= grade <= 11:
                totals["grades_10_11"] += total
                totals["classes_10_11"] += 1

    return render_template(
        "contingent.html",
        rows=rows,
        years=years,
        buildings=buildings,
        year_id=year_id,
        building_id=building_id,
        totals=totals,
        transfer_counts=transfer_counts
    )
# =========================================================
# IMPORT CHILDREN
# =========================================================
@children_bp.route("/children/import", methods=["GET", "POST"])
@require_roles("ADMIN")
def children_import():
    print("=== NEW CHILDREN IMPORT ROUTE ===")
    year = _get_current_year()

    if request.method == "POST":
        f = request.files.get("file")

        if not f or not f.filename:
            flash("Выберите Excel файл", "danger")
            return redirect(url_for("children.children_import"))

        if not year:
            flash("Не найден текущий учебный год", "danger")
            return redirect(url_for("children.children_import"))

        wb = load_workbook(f, data_only=True)
        ws = wb.active

        headers = [(str(c.value).strip() if c.value else "") for c in ws[1]]
        idx = {h: i for i, h in enumerate(headers)}

        required = [
            "ФИО",
            "Пол",
            "Родился",
            "Номер и буква класса"
        ]

        missing = [c for c in required if c not in idx]

        if missing:
             flash(f"НОВЫЙ ИМПОРТ: не хватает колонок: {', '.join(missing)}", "danger")
             return redirect(url_for("children.children_import"))

        created = 0
        skipped = 0

        def parse_birth(x):
            if not x:
                return None
            if isinstance(x, datetime):
                return x.date()
            if isinstance(x, date):
                return x

            s = str(x).strip()

            m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", s)
            if m:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None

        def split_fio(fio):
            parts = str(fio).strip().split()
            last = parts[0] if len(parts) > 0 else ""
            first = parts[1] if len(parts) > 1 else ""
            middle = parts[2] if len(parts) > 2 else None
            return last, first, middle

        for r in range(2, ws.max_row + 1):

            row = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]

            fio = str(row[idx["ФИО"]] or "").strip()

            if not fio:
                skipped += 1
                continue

            last_name, first_name, middle_name = split_fio(fio)

            birth_date = parse_birth(row[idx["Родился"]])

            gender_raw = str(row[idx["Пол"]] or "").strip().lower()

            if gender_raw in ["м", "муж", "мужской"]:
                gender = "М"
            elif gender_raw in ["ж", "жен", "женский"]:
                gender = "Ж"
            else:
                gender = None

            class_name = normalize_class_name(row[idx["Номер и буква класса"]])

            education_form = None
            if "Сведения о форме обучения" in idx:
                education_form = str(row[idx["Сведения о форме обучения"]] or "").strip() or None

            reg_address = None
            if "Регистрация по месту жительства" in idx:
                reg_address = str(row[idx["Регистрация по месту жительства"]] or "").strip() or None

            temporary_address = None
            if "Регистрация по месту пребывания" in idx:
                temporary_address = str(row[idx["Регистрация по месту пребывания"]] or "").strip() or None

            actual_address = None
            if "Адрес фактического проживания" in idx:
                actual_address = str(row[idx["Адрес фактического проживания"]] or "").strip() or None

            child = Child(
                last_name=last_name,
                first_name=first_name,
                middle_name=middle_name,
                birth_date=birth_date,
                gender=gender,
                education_form=education_form,
                reg_address=reg_address,
                temporary_address=temporary_address,
                actual_address=actual_address,
            )

            db.session.add(child)
            db.session.flush()

            social = _get_or_create_social(child)

            if "Вариант АООП" in idx:
                social.aoop_variant_text = str(row[idx["Вариант АООП"]] or "").strip() or None
                apply_aoop_to_child(child, social, social.aoop_variant_text)

            if "На ВШУ с" in idx:
                social.vshu_since = parse_birth(row[idx["На ВШУ с"]])

            if "Основание(я) постановки на ВШУ" in idx:
                social.vshu_reason = str(row[idx["Основание(я) постановки на ВШУ"]] or "").strip() or None

            if "На учете КДН с" in idx:
                social.kdn_since = parse_birth(row[idx["На учете КДН с"]])

            if "Основание(я) постановки на учет КДН" in idx:
                social.kdn_reason = str(row[idx["Основание(я) постановки на учет КДН"]] or "").strip() or None

            if "На учете ПДН с" in idx:
                social.pdn_since = parse_birth(row[idx["На учете ПДН с"]])

            if "Основание(я) постановки на учет ПДН" in idx:
                social.pdn_reason = str(row[idx["Основание(я) постановки на учет ПДН"]] or "").strip() or None

            if "Снят с ВШУ" in idx:
                social.vshu_removed_at = parse_birth(row[idx["Снят с ВШУ"]])

            if "Основание снятия с ВШУ" in idx:
                social.vshu_remove_reason = str(row[idx["Основание снятия с ВШУ"]] or "").strip() or None

            if class_name:

                sc = (
                    SchoolClass.query
                    .filter(
                        SchoolClass.academic_year_id == year.id,
                        SchoolClass.name == class_name
                    )
                    .first()
                )

                if not sc:

                    g, l = split_class_name(class_name)

                    sc = SchoolClass(
                        academic_year_id=year.id,
                        name=class_name,
                        grade=g,
                        letter=l,
                        max_students=25,
                    )

                    db.session.add(sc)
                    db.session.flush()

                en = ChildEnrollment(
                    child_id=child.id,
                    academic_year_id=year.id,
                    school_class_id=sc.id,
                    status="ACTIVE"
                )

                db.session.add(en)

            created += 1

        db.session.commit()

        flash(f"Импорт завершён. Добавлено детей: {created}, пропущено строк: {skipped}", "success")

        return redirect(url_for("children.list_children"))

    return render_template("children_import.html")

@children_bp.route("/classes/<int:class_id>/update", methods=["POST"])
@require_roles("ADMIN")
def update_class(class_id: int):
    c = SchoolClass.query.get_or_404(class_id)

    old_teacher_user_id = c.teacher_user_id

    building_id = request.form.get("building_id")
    c.building_id = int(building_id) if (building_id and str(building_id).isdigit()) else None

    ms = request.form.get("max_students")
    if ms and ms.isdigit():
        c.max_students = int(ms)

    teacher_user_id = request.form.get("teacher_user_id")
    c.teacher_user_id = int(teacher_user_id) if (teacher_user_id and teacher_user_id.isdigit()) else None

    name = (request.form.get("name") or "").strip()
    if name:
        c.name = name
        g, l = split_class_name(name)
        c.grade = g
        c.letter = l

    db.session.flush()

    _sync_class_teacher_role(old_teacher_user_id)
    _sync_class_teacher_role(c.teacher_user_id)

    db.session.commit()
    flash("Сохранено", "success")
    return redirect(url_for("children.classes_registry"))

@children_bp.route("/classes")
@require_roles("ADMIN")
def classes_registry():
    year_id = request.args.get("academic_year_id", type=int)
    year = AcademicYear.query.get(year_id) if year_id else _get_current_year()
    if not year:
        flash("Не найден текущий учебный год", "danger")
        return redirect(url_for("children.contingent"))

    all_years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    raw_classes = (
        SchoolClass.query
        .filter(SchoolClass.academic_year_id == year.id)
        .order_by(
            SchoolClass.grade.asc().nullslast(),
            SchoolClass.letter.asc().nullslast(),
            SchoolClass.name.asc()
        )
        .all()
    )

    buildings = Building.query.order_by(Building.name.asc()).all()
    teachers = User.query.order_by(User.last_name.asc(), User.first_name.asc()).all()

    teachers_map = {u.id: u for u in teachers}

    classes = []
    for c in raw_classes:
        teacher = teachers_map.get(c.teacher_user_id)
        teacher_fio = teacher.fio if teacher else None
        teacher_phone = teacher.phone if teacher else None
        active_count = ChildEnrollment.query.filter(
            ChildEnrollment.school_class_id == c.id,
            ChildEnrollment.ended_at.is_(None)
        ).count()
        classes.append((c, teacher_fio, teacher_phone, active_count))

    return render_template(
        "classes_list.html",
        classes=classes,
        teachers=teachers,
        buildings=buildings,
        year=year,
        all_years=all_years,
    )

@children_bp.route("/classes/new", methods=["POST"])
@require_roles("ADMIN")
def classes_new():
    requested_year_id = request.form.get("academic_year_id", type=int)
    year = AcademicYear.query.get(requested_year_id) if requested_year_id else _get_current_year()
    if not year:
        flash("Не найден текущий учебный год", "danger")
        return redirect(url_for("children.classes_registry", academic_year_id=year.id if year else None))

    name = (request.form.get("name") or "").strip()
    max_students = request.form.get("max_students", type=int) or 25
    teacher_user_id = request.form.get("teacher_user_id", type=int)
    building_id = request.form.get("building_id", type=int)

    if not name:
        flash("Укажите класс", "danger")
        return redirect(url_for("children.classes_registry", academic_year_id=year.id if year else None))

    g, l = split_class_name(name)

    c = SchoolClass(
        academic_year_id=year.id,
        building_id=building_id,
        name=name,
        grade=g,
        letter=l,
        max_students=max_students,
        teacher_user_id=teacher_user_id
    )

    db.session.add(c)
    db.session.flush()

    _sync_class_teacher_role(teacher_user_id)

    db.session.commit()
    flash("Класс добавлен", "success")
    return redirect(url_for("children.classes_registry", academic_year_id=year.id))

# =========================================================
# REGISTRIES
# =========================================================
@children_bp.route("/registry/vshu")
@login_required
def registry_vshu():
    q, year = _children_base_query_for_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())
    q = q.outerjoin(ChildSocial, ChildSocial.child_id == Child.id).filter(
        db.or_(
            Child.is_vshu.is_(True),
            ChildSocial.vshu_since.isnot(None)
        )
    ).filter(
        db.or_(
            ChildSocial.vshu_removed_at.is_(None),
            Child.is_vshu.is_(True)
        )
    )

    if filters["selected_grade"] is not None:
        q = q.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        q = q.filter(SchoolClass.id == filters["selected_class_id"])

    children = (
        q.options(joinedload(Child.parent_links).joinedload(ChildParent.parent))
        .order_by(SchoolClass.name.asc(), Child.last_name.asc(), Child.first_name.asc())
        .all()
    )

    if filters["q_text"]:
        children = [ch for ch in children if _match_fio_query(ch, filters["q_text"])]

    return render_template(
        "registry_children.html",
        title="Реестр ВШУ",
        children=children,
        q_text=filters["q_text"],
        classes=filters["classes"],
        grades=filters["grades"],
        selected_grade=filters["selected_grade"],
        selected_class_id=filters["selected_class_id"],
        export_url=url_for("children.registry_vshu_export", grade=filters["selected_grade_raw"], class_id=filters["selected_class_id"], q=filters["q_text"])
    )


@children_bp.route("/registry/vshu/export")
@login_required
def registry_vshu_export():
    q, year = _children_base_query_for_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())
    q = q.outerjoin(ChildSocial, ChildSocial.child_id == Child.id).filter(
        db.or_(
            Child.is_vshu.is_(True),
            ChildSocial.vshu_since.isnot(None)
        )
    ).filter(
        db.or_(
            ChildSocial.vshu_removed_at.is_(None),
            Child.is_vshu.is_(True)
        )
    )
    if filters["selected_grade"] is not None:
        q = q.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        q = q.filter(SchoolClass.id == filters["selected_class_id"])

    children = (
        q.options(joinedload(Child.parent_links).joinedload(ChildParent.parent))
        .order_by(Child.last_name.asc(), Child.first_name.asc())
        .all()
    )
    if filters["q_text"]:
        children = [ch for ch in children if _match_fio_query(ch, filters["q_text"])]

    return _export_children_xlsx("Реестр_ВШУ", children)


@children_bp.route("/registry/ovz")
@login_required
def registry_ovz():
    q, year = _children_base_query_for_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())
    q = q.filter(Child.is_ovz.is_(True))
    if filters["selected_grade"] is not None:
        q = q.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        q = q.filter(SchoolClass.id == filters["selected_class_id"])

    children = q.order_by(SchoolClass.name.asc(), Child.last_name.asc(), Child.first_name.asc()).all()
    if filters["q_text"]:
        children = [ch for ch in children if _match_fio_query(ch, filters["q_text"])]

    return render_template(
        "registry_ovz.html",
        title="Реестр ОВЗ",
        children=children,
        q_text=filters["q_text"],
        classes=filters["classes"],
        grades=filters["grades"],
        selected_grade=filters["selected_grade"],
        selected_class_id=filters["selected_class_id"],
        export_url=url_for("children.registry_ovz_export", grade=filters["selected_grade_raw"], class_id=filters["selected_class_id"], q=filters["q_text"])
    )


@children_bp.route("/registry/ovz/export")
@login_required
def registry_ovz_export():
    q, year = _children_base_query_for_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())
    q = q.filter(Child.is_ovz.is_(True))
    if filters["selected_grade"] is not None:
        q = q.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        q = q.filter(SchoolClass.id == filters["selected_class_id"])

    children = q.order_by(Child.last_name.asc(), Child.first_name.asc()).all()
    if filters["q_text"]:
        children = [ch for ch in children if _match_fio_query(ch, filters["q_text"])]

    return _export_children_xlsx("Реестр_ОВЗ", children)


@children_bp.route("/registry/az")
@login_required
def registry_az():
    year = _get_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())

    debts = (
        Debt.query
        .join(Child, Debt.child_id == Child.id)
        .join(Subject, Debt.subject_id == Subject.id)
        .outerjoin(
            ChildEnrollment,
            (ChildEnrollment.child_id == Child.id)
            & (ChildEnrollment.academic_year_id == year.id if year else True)
            & (ChildEnrollment.ended_at.is_(None))
        )
        .outerjoin(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        .filter(Debt.status == "OPEN")
    )

    if filters["selected_grade"] is not None:
        debts = debts.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        debts = debts.filter(SchoolClass.id == filters["selected_class_id"])

    debts = debts.order_by(SchoolClass.name.asc(), Child.last_name.asc(), Child.first_name.asc(), Subject.name.asc()).all()

    m = {}
    for d in debts:
        ch = d.child
        if not _match_fio_query(ch, filters["q_text"]):
            continue

        if ch.id not in m:
            m[ch.id] = {"child": ch, "subjects": []}
        subj = d.subject.name if d.subject else None
        if subj and subj not in m[ch.id]["subjects"]:
            m[ch.id]["subjects"].append(subj)

    rows = list(m.values())

    return render_template(
        "registry_az.html",
        title="Реестр АЗ (открытые задолженности)",
        rows=rows,
        q_text=filters["q_text"],
        classes=filters["classes"],
        grades=filters["grades"],
        selected_grade=filters["selected_grade"],
        selected_class_id=filters["selected_class_id"],
        export_url=url_for("children.registry_az_export", grade=filters["selected_grade_raw"], class_id=filters["selected_class_id"], q=filters["q_text"])
    )


@children_bp.route("/registry/az/export")
@login_required
def registry_az_export():
    year = _get_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())

    debts = (
        Debt.query
        .join(Child, Debt.child_id == Child.id)
        .join(Subject, Debt.subject_id == Subject.id)
        .outerjoin(
            ChildEnrollment,
            (ChildEnrollment.child_id == Child.id)
            & (ChildEnrollment.academic_year_id == year.id if year else True)
            & (ChildEnrollment.ended_at.is_(None))
        )
        .outerjoin(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        .filter(Debt.status == "OPEN")
    )

    if filters["selected_grade"] is not None:
        debts = debts.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        debts = debts.filter(SchoolClass.id == filters["selected_class_id"])

    debts = debts.order_by(Child.last_name.asc(), Child.first_name.asc(), Subject.name.asc()).all()

    m = {}
    for d in debts:
        ch = d.child
        if not _match_fio_query(ch, filters["q_text"]):
            continue
        if ch.id not in m:
            m[ch.id] = {"child": ch, "subjects": []}
        subj = d.subject.name if d.subject else None
        if subj and subj not in m[ch.id]["subjects"]:
            m[ch.id]["subjects"].append(subj)

    wb = Workbook()
    ws = wb.active
    ws.title = "АЗ"
    ws.append(["№", "ФИО", "Класс", "Предметы (открытые)"])

    for idx, item in enumerate(m.values(), start=1):
        ch = item["child"]
        ws.append([
            idx,
            ch.fio,
            ch.current_class_name or "—",
            ", ".join(item["subjects"])
        ])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    return send_file(
        bio,
        as_attachment=True,
        download_name="Реестр_АЗ.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@children_bp.route("/registry/enrolled")
@login_required
def registry_enrolled():
    year = _get_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())
    if not year:
        flash("Не найден текущий учебный год", "danger")
        return redirect(url_for("children.home"))

    ens = (
        ChildEnrollment.query
        .join(Child, ChildEnrollment.child_id == Child.id)
        .join(SchoolClass, ChildEnrollment.school_class_id == SchoolClass.id)
        .filter(
            ChildEnrollment.academic_year_id == year.id,
            ChildEnrollment.ended_at.is_(None),
            ChildEnrollment.status == "ACTIVE"
        )
    )

    if filters["selected_grade"] is not None:
        ens = ens.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        ens = ens.filter(SchoolClass.id == filters["selected_class_id"])

    ens = ens.order_by(SchoolClass.name.asc(), Child.last_name.asc(), Child.first_name.asc()).all()

    rows = []
    for en in ens:
        ch = en.child
        if not _match_fio_query(ch, filters["q_text"]):
            continue
        rows.append({
            "child": ch,
            "class_name": en.school_class.name if en.school_class else None,
            "en": en
        })

    return render_template(
        "registry_enrolled.html",
        title=f"Реестр зачисленных ({year.name})",
        rows=rows,
        q_text=filters["q_text"],
        classes=filters["classes"],
        grades=filters["grades"],
        selected_grade=filters["selected_grade"],
        selected_class_id=filters["selected_class_id"],
        export_url=url_for("children.registry_enrolled_export", grade=filters["selected_grade_raw"], class_id=filters["selected_class_id"], q=filters["q_text"])
    )


@children_bp.route("/registry/enrolled/export")
@login_required
def registry_enrolled_export():
    year = _get_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())
    if not year:
        flash("Не найден текущий учебный год", "danger")
        return redirect(url_for("children.home"))

    ens = (
        ChildEnrollment.query
        .join(Child, ChildEnrollment.child_id == Child.id)
        .join(SchoolClass, ChildEnrollment.school_class_id == SchoolClass.id)
        .filter(
            ChildEnrollment.academic_year_id == year.id,
            ChildEnrollment.ended_at.is_(None),
            ChildEnrollment.status == "ACTIVE"
        )
    )

    if filters["selected_grade"] is not None:
        ens = ens.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        ens = ens.filter(SchoolClass.id == filters["selected_class_id"])

    ens = ens.order_by(Child.last_name.asc(), Child.first_name.asc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Зачисленные"
    ws.append(["№", "ФИО", "Класс", "Дата зачисления"])

    row_num = 1
    for en in ens:
        ch = en.child
        if not _match_fio_query(ch, filters["q_text"]):
            continue
        ws.append([
            row_num,
            ch.fio,
            en.school_class.name if en.school_class else "",
            en.enrolled_at.strftime("%d.%m.%Y %H:%M") if en.enrolled_at else ""
        ])
        row_num += 1

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    return send_file(
        bio,
        as_attachment=True,
        download_name="Реестр_зачисленных.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@children_bp.route("/registry/expelled")
@login_required
def registry_expelled():
    year = _get_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())

    events = (
        ChildEvent.query
        .join(Child, ChildEvent.child_id == Child.id)
        .filter(ChildEvent.event_type == "EXPEL")
    )

    if filters["selected_grade"] is not None:
        grade_classes = [c.name for c in filters["classes"]]
        if grade_classes:
            events = events.filter(ChildEvent.from_class.in_(grade_classes))
        else:
            events = events.filter(db.text("1=0"))
    if filters["selected_class_name"]:
        events = events.filter(ChildEvent.from_class == filters["selected_class_name"])

    events = events.order_by(ChildEvent.created_at.desc()).all()

    rows = []
    row_num = 1
    for ev in events:
        ch = Child.query.get(ev.child_id)
        if not ch:
            continue
        if not _match_fio_query(ch, filters["q_text"]):
            continue
        rows.append({"child": ch, "ev": ev})

    return render_template(
        "registry_expelled.html",
        title="Реестр отчисленных",
        rows=rows,
        q_text=filters["q_text"],
        classes=filters["classes"],
        grades=filters["grades"],
        selected_grade=filters["selected_grade"],
        selected_class_id=filters["selected_class_id"],
        export_url=url_for("children.registry_expelled_export", grade=filters["selected_grade_raw"], class_id=filters["selected_class_id"], q=filters["q_text"])
    )


@children_bp.route("/registry/expelled/export")
@login_required
def registry_expelled_export():
    year = _get_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())

    events = (
        ChildEvent.query
        .join(Child, ChildEvent.child_id == Child.id)
        .filter(ChildEvent.event_type == "EXPEL")
    )

    if filters["selected_grade"] is not None:
        grade_classes = [c.name for c in filters["classes"]]
        if grade_classes:
            events = events.filter(ChildEvent.from_class.in_(grade_classes))
        else:
            events = events.filter(db.text("1=0"))
    if filters["selected_class_name"]:
        events = events.filter(ChildEvent.from_class == filters["selected_class_name"])

    events = events.order_by(ChildEvent.created_at.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Отчисленные"
    ws.append(["№", "ФИО", "Класс (откуда)", "Дата", "Причина/основание", "Куда"])

    row_num = 1
    for ev in events:
        ch = Child.query.get(ev.child_id)
        if not ch:
            continue
        if not _match_fio_query(ch, filters["q_text"]):
            continue

        ws.append([
            row_num,
            ch.fio,
            ev.from_class or "",
            ev.created_at.strftime("%d.%m.%Y %H:%M") if ev.created_at else "",
            ev.reason or "",
            ev.to_class or "",
        ])
        row_num += 1

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    return send_file(
        bio,
        as_attachment=True,
        download_name="Реестр_отчисленных.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# =========================================================
# INCIDENTS
# =========================================================
@children_bp.route("/incidents/new", methods=["GET", "POST"])
@login_required
def incident_new():
    if request.method == "POST":
        occurred_date = (request.form.get("occurred_date") or "").strip()
        occurred_hour = (request.form.get("occurred_hour") or "").strip()
        occurred_minute = (request.form.get("occurred_minute") or "").strip()
        occurred_time = f"{occurred_hour}:{occurred_minute}"
        category = (request.form.get("category") or "").strip()
        description = (request.form.get("description") or "").strip() or None

        raw_ids = request.form.getlist("child_ids")
        child_ids = []
        for x in raw_ids:
            if str(x).isdigit():
                child_ids.append(int(x))
        child_ids = list(dict.fromkeys(child_ids))

        if not occurred_date or not occurred_time:
            flash("Укажите дату и время", "danger")
            return redirect(url_for("children.incident_new"))

        if category not in INCIDENT_CATEGORIES:
            flash("Выберите категорию инцидента", "danger")
            return redirect(url_for("children.incident_new"))

        if not child_ids:
            flash("Добавьте хотя бы одного ребёнка", "danger")
            return redirect(url_for("children.incident_new"))

        try:
            occurred_at = datetime.strptime(f"{occurred_date} {occurred_time}", "%Y-%m-%d %H:%M")
        except Exception:
            flash("Неверный формат даты/времени", "danger")
            return redirect(url_for("children.incident_new"))

        inc = Incident(
            occurred_at=occurred_at,
            category=category,
            description=description,
            author_id=getattr(current_user, "id", None),
            created_at=datetime.utcnow(),
        )
        db.session.add(inc)
        db.session.flush()

        for cid in child_ids:
            ch = Child.query.get(cid)
            if ch:
                db.session.add(IncidentChild(incident_id=inc.id, child_id=ch.id))

        db.session.commit()
        flash("Инцидент сохранён", "success")
        return redirect(url_for("children.child_card", child_id=child_ids[0]))

    return render_template(
        "incident_new.html",
        categories=INCIDENT_CATEGORIES
    )


@children_bp.route("/api/classes/by-grade")
@login_required
def api_classes_by_grade():
    grade = request.args.get("grade", type=int)
    if not grade:
        return jsonify([])

    year = _get_current_year()
    if not year:
        return jsonify([])

    q = SchoolClass.query.filter(
        SchoolClass.academic_year_id == year.id,
        SchoolClass.grade == grade
    )

    classes = q.order_by(SchoolClass.name.asc()).all()
    return jsonify([{"id": c.id, "name": c.name} for c in classes])


@children_bp.route("/api/children/by-class")
@login_required
def api_children_by_class():
    class_id = request.args.get("class_id", type=int)
    if not class_id:
        return jsonify([])

    year = _get_current_year()
    if not year:
        return jsonify([])

    ens = (
        ChildEnrollment.query
        .join(Child, ChildEnrollment.child_id == Child.id)
        .filter(
            ChildEnrollment.academic_year_id == year.id,
            ChildEnrollment.school_class_id == class_id,
            ChildEnrollment.ended_at.is_(None)
        )
        .order_by(Child.last_name.asc(), Child.first_name.asc(), Child.middle_name.asc())
        .all()
    )

    return jsonify([{"id": en.child.id, "fio": en.child.fio} for en in ens])


def _can_manage_incident(incident):
    role = getattr(current_user, "role", None)
    if role in {"ADMIN", "METHODIST"}:
        return True
    return bool(getattr(current_user, "id", None)) and incident.author_id == current_user.id and has_permission("incident_add")


@children_bp.route("/incidents/<int:incident_id>/edit", methods=["GET", "POST"])
@login_required
def incident_edit(incident_id):
    inc = Incident.query.get_or_404(incident_id)
    if not _can_manage_incident(inc):
        abort(403)

    if request.method == "POST":
        occurred_date = (request.form.get("occurred_date") or "").strip()
        occurred_hour = (request.form.get("occurred_hour") or "").strip()
        occurred_minute = (request.form.get("occurred_minute") or "").strip()
        occurred_time = f"{occurred_hour}:{occurred_minute}"
        category = (request.form.get("category") or "").strip()
        description = (request.form.get("description") or "").strip() or None

        raw_ids = request.form.getlist("child_ids")
        child_ids = []
        for x in raw_ids:
            if str(x).isdigit():
                child_ids.append(int(x))
        child_ids = list(dict.fromkeys(child_ids))

        if not occurred_date or not occurred_time:
            flash("Укажите дату и время", "danger")
            return redirect(url_for("children.incident_edit", incident_id=inc.id))

        if category not in INCIDENT_CATEGORIES:
            flash("Выберите категорию инцидента", "danger")
            return redirect(url_for("children.incident_edit", incident_id=inc.id))

        if not child_ids:
            flash("Добавьте хотя бы одного ребёнка", "danger")
            return redirect(url_for("children.incident_edit", incident_id=inc.id))

        try:
            occurred_at = datetime.strptime(f"{occurred_date} {occurred_time}", "%Y-%m-%d %H:%M")
        except Exception:
            flash("Неверный формат даты/времени", "danger")
            return redirect(url_for("children.incident_edit", incident_id=inc.id))

        inc.occurred_at = occurred_at
        inc.category = category
        inc.description = description

        IncidentChild.query.filter_by(incident_id=inc.id).delete()
        for cid in child_ids:
            ch = Child.query.get(cid)
            if ch:
                db.session.add(IncidentChild(incident_id=inc.id, child_id=ch.id))

        db.session.commit()
        flash("Инцидент обновлён", "success")
        next_url = (request.form.get("next") or "").strip()
        if next_url.startswith("/"):
            return redirect(next_url)
        if child_ids:
            return redirect(url_for("children.child_card", child_id=child_ids[0]))
        return redirect(url_for("children.incidents_registry"))

    selected_children = [link.child for link in IncidentChild.query.filter_by(incident_id=inc.id).all() if link.child]
    grouped = {}
    for ch in selected_children:
        cl = ch.current_class
        key = getattr(cl, "id", None) or f"child-{ch.id}"
        if key not in grouped:
            grouped[key] = {
                "grade": getattr(cl, "grade", None) or "",
                "class_id": getattr(cl, "id", None) or "",
                "child_ids": [],
            }
        grouped[key]["child_ids"].append(ch.id)

    selected_blocks = list(grouped.values()) or [{"grade": "", "class_id": "", "child_ids": []}]

    return render_template(
        "incident_edit.html",
        incident=inc,
        categories=INCIDENT_CATEGORIES,
        selected_blocks=selected_blocks,
    )


@children_bp.route("/incidents/<int:incident_id>/delete", methods=["POST"])
@login_required
def incident_delete(incident_id):
    inc = Incident.query.get_or_404(incident_id)
    if not _can_manage_incident(inc):
        abort(403)

    child_id = None
    first_link = IncidentChild.query.filter_by(incident_id=inc.id).first()
    if first_link:
        child_id = first_link.child_id

    IncidentChild.query.filter_by(incident_id=inc.id).delete()
    db.session.delete(inc)
    db.session.commit()
    flash("Инцидент удалён", "success")

    next_url = (request.form.get("next") or request.referrer or "").strip()
    if next_url.startswith("/") or next_url.startswith("http://") or next_url.startswith("https://"):
        return redirect(next_url)
    if child_id:
        return redirect(url_for("children.child_card", child_id=child_id))
    return redirect(url_for("children.incidents_registry"))


@children_bp.route("/incidents/registry")
@require_roles("ADMIN", "METHODIST")
def incidents_registry():
    q_text = (request.args.get("q") or "").strip()
    grade = request.args.get("grade", type=int)
    class_id = request.args.get("class_id", type=int)
    category = (request.args.get("category") or "").strip()

    year = _get_current_year()
    year_id = year.id if year else None

    iq = (
        db.session.query(Incident)
        .join(IncidentChild, IncidentChild.incident_id == Incident.id)
        .join(Child, Child.id == IncidentChild.child_id)
    )

    if category:
        iq = iq.filter(Incident.category == category)

    if q_text:
        ql = q_text.lower()
        iq = iq.filter(
            func.lower(func.coalesce(Child.last_name, "")).like(f"%{ql}%") |
            func.lower(func.coalesce(Child.first_name, "")).like(f"%{ql}%") |
            func.lower(func.coalesce(Child.middle_name, "")).like(f"%{ql}%")
        )

    if year_id and (grade or class_id):
        iq = iq.join(ChildEnrollment, ChildEnrollment.child_id == Child.id)
        iq = iq.filter(
            ChildEnrollment.academic_year_id == year_id,
            ChildEnrollment.ended_at.is_(None)
        )
        if class_id:
            iq = iq.filter(ChildEnrollment.school_class_id == class_id)
        elif grade:
            iq = iq.join(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
            iq = iq.filter(SchoolClass.grade == grade)

    incidents = iq.order_by(Incident.occurred_at.desc(), Incident.id.desc()).all()

    rows = []
    for idx, inc in enumerate(incidents, start=1):
        links = IncidentChild.query.filter_by(incident_id=inc.id).all()
        kids = []
        for lk in links:
            ch = Child.query.get(lk.child_id)
            if not ch:
                continue
            kids.append({
                "id": ch.id,
                "fio": ch.fio,
                "class": ch.current_class_name or "—"
            })
        rows.append({"inc": inc, "children": kids})

    classes = (
        SchoolClass.query
        .filter(SchoolClass.academic_year_id == year.id)
        .order_by(
            SchoolClass.grade.asc().nullslast(),
            SchoolClass.letter.asc().nullslast(),
            SchoolClass.name.asc()
        )
        .all()
    )

    return render_template(
        "incidents_registry.html",
        title="Реестр инцидентов",
        rows=rows,
        q=q_text,
        grade=grade,
        class_id=class_id,
        category=category,
        categories=INCIDENT_CATEGORIES,
        classes=classes,
        export_url=url_for("children.incidents_registry_export", grade=grade, class_id=class_id, category=category, q=q_text)
    )


@children_bp.route("/incidents/registry/export")
@require_roles("ADMIN", "METHODIST")
def incidents_registry_export():
    q_text = (request.args.get("q") or "").strip()
    grade = request.args.get("grade", type=int)
    class_id = request.args.get("class_id", type=int)
    category = (request.args.get("category") or "").strip()

    year = _get_current_year()
    year_id = year.id if year else None

    iq = (
        db.session.query(Incident)
        .join(IncidentChild, IncidentChild.incident_id == Incident.id)
        .join(Child, Child.id == IncidentChild.child_id)
    )

    if category:
        iq = iq.filter(Incident.category == category)

    if q_text:
        ql = q_text.lower()
        iq = iq.filter(
            func.lower(func.coalesce(Child.last_name, "")).like(f"%{ql}%") |
            func.lower(func.coalesce(Child.first_name, "")).like(f"%{ql}%") |
            func.lower(func.coalesce(Child.middle_name, "")).like(f"%{ql}%")
        )

    if year_id and (grade or class_id):
        iq = iq.join(ChildEnrollment, ChildEnrollment.child_id == Child.id)
        iq = iq.filter(
            ChildEnrollment.academic_year_id == year_id,
            ChildEnrollment.ended_at.is_(None)
        )
        if class_id:
            iq = iq.filter(ChildEnrollment.school_class_id == class_id)
        elif grade:
            iq = iq.join(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
            iq = iq.filter(SchoolClass.grade == grade)

    incidents = iq.order_by(Incident.occurred_at.desc(), Incident.id.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Инциденты"
    ws.append(["№", "Дата/время", "Категория", "Обучающиеся", "Классы", "Описание", "Автор"])

    for idx, inc in enumerate(incidents, start=1):
        links = IncidentChild.query.filter_by(incident_id=inc.id).all()
        children = []
        classes = []
        for lk in links:
            ch = Child.query.get(lk.child_id)
            if not ch:
                continue
            children.append(ch.fio)
            cls_name = ch.current_class_name or "—"
            if cls_name not in classes:
                classes.append(cls_name)
        ws.append([
            idx,
            inc.occurred_at.strftime("%d.%m.%Y %H:%M") if inc.occurred_at else "",
            inc.category or "",
            "; ".join(children),
            "; ".join(classes),
            inc.description or "",
            inc.author.fio if getattr(inc, "author", None) else "",
        ])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    return send_file(
        bio,
        as_attachment=True,
        download_name="Реестр_инцидентов.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@children_bp.route("/incidents/dashboard")
@require_roles("ADMIN", "METHODIST")
def incidents_dashboard():
    return redirect(url_for("children.incidents_dashboard_legacy", **request.args))


@children_bp.route("/incidents/dashboard-legacy")
@require_roles("ADMIN", "METHODIST")
def incidents_dashboard_legacy():
    grade = request.args.get("grade", type=int)
    class_id = request.args.get("class_id", type=int)
    category = (request.args.get("category") or "").strip()

    year = _get_current_year()
    year_id = year.id if year else None

    base = (
        db.session.query(Incident)
        .join(IncidentChild, IncidentChild.incident_id == Incident.id)
        .join(Child, Child.id == IncidentChild.child_id)
    )

    if category:
        base = base.filter(Incident.category == category)

    if year_id and (grade or class_id):
        base = base.join(ChildEnrollment, ChildEnrollment.child_id == Child.id)
        base = base.filter(
            ChildEnrollment.academic_year_id == year_id,
            ChildEnrollment.ended_at.is_(None)
        )
        if class_id:
            base = base.filter(ChildEnrollment.school_class_id == class_id)
        elif grade:
            base = base.join(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
            base = base.filter(SchoolClass.grade == grade)

    base = base.distinct()

    now = datetime.utcnow()
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)

    total_all = base.count()
    total_7 = base.filter(Incident.occurred_at >= d7).count()
    total_30 = base.filter(Incident.occurred_at >= d30).count()

    top_categories = (
        db.session.query(Incident.category, func.count(func.distinct(Incident.id)))
        .select_from(Incident)
        .join(IncidentChild, IncidentChild.incident_id == Incident.id)
        .join(Child, Child.id == IncidentChild.child_id)
        .filter(Incident.occurred_at >= d30)
    )

    if category:
        top_categories = top_categories.filter(Incident.category == category)

    if year_id and (grade or class_id):
        top_categories = top_categories.join(ChildEnrollment, ChildEnrollment.child_id == Child.id)
        top_categories = top_categories.filter(
            ChildEnrollment.academic_year_id == year_id,
            ChildEnrollment.ended_at.is_(None)
        )
        if class_id:
            top_categories = top_categories.filter(ChildEnrollment.school_class_id == class_id)
        elif grade:
            top_categories = top_categories.join(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
            top_categories = top_categories.filter(SchoolClass.grade == grade)

    top_categories = (
        top_categories
        .group_by(Incident.category)
        .order_by(func.count(func.distinct(Incident.id)).desc())
        .limit(10)
        .all()
    )

    top_classes = []
    if year_id:
        tc = (
            db.session.query(SchoolClass.name, func.count(func.distinct(Incident.id)))
            .select_from(Incident)
            .join(IncidentChild, IncidentChild.incident_id == Incident.id)
            .join(Child, Child.id == IncidentChild.child_id)
            .join(ChildEnrollment, ChildEnrollment.child_id == Child.id)
            .join(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
            .filter(
                Incident.occurred_at >= d30,
                ChildEnrollment.academic_year_id == year_id,
                ChildEnrollment.ended_at.is_(None)
            )
        )

        if category:
            tc = tc.filter(Incident.category == category)
        if class_id:
            tc = tc.filter(SchoolClass.id == class_id)
        elif grade:
            tc = tc.filter(SchoolClass.grade == grade)

        top_classes = (
            tc.group_by(SchoolClass.name)
            .order_by(func.count(func.distinct(Incident.id)).desc())
            .limit(10)
            .all()
        )

    top_buildings = []
    if year_id:
        tb = (
            db.session.query(Building.name, func.count(func.distinct(Incident.id)))
            .select_from(Incident)
            .join(IncidentChild, IncidentChild.incident_id == Incident.id)
            .join(Child, Child.id == IncidentChild.child_id)
            .join(ChildEnrollment, ChildEnrollment.child_id == Child.id)
            .join(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
            .outerjoin(Building, Building.id == SchoolClass.building_id)
            .filter(
                Incident.occurred_at >= d30,
                ChildEnrollment.academic_year_id == year_id,
                ChildEnrollment.ended_at.is_(None)
            )
        )

        if category:
            tb = tb.filter(Incident.category == category)
        if class_id:
            tb = tb.filter(SchoolClass.id == class_id)
        elif grade:
            tb = tb.filter(SchoolClass.grade == grade)

        top_buildings = (
            tb.group_by(Building.name)
            .order_by(func.count(func.distinct(Incident.id)).desc())
            .limit(10)
            .all()
        )

    recent_daily = []
    daily_labels = []
    max_daily = 0
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        cnt = base.filter(Incident.occurred_at >= day_start, Incident.occurred_at < day_end).count()
        recent_daily.append({
            "label": day_start.strftime("%d.%m"),
            "count": cnt,
        })
        daily_labels.append(day_start.strftime("%d.%m"))
        max_daily = max(max_daily, cnt)

    max_category = max([cnt for _, cnt in top_categories], default=0)
    max_class = max([cnt for _, cnt in top_classes], default=0)
    max_building = max([cnt for _, cnt in top_buildings], default=0)

    recent = base.order_by(Incident.occurred_at.desc(), Incident.id.desc()).limit(20).all()
    rows = []
    for inc in recent:
        links = IncidentChild.query.filter_by(incident_id=inc.id).all()
        kids = []
        for lk in links:
            ch = Child.query.get(lk.child_id)
            if not ch:
                continue
            kids.append({
                "id": ch.id,
                "fio": ch.fio,
                "class": ch.current_class_name or "—"
            })
        rows.append({"inc": inc, "children": kids})

    classes = (
        SchoolClass.query
        .filter(SchoolClass.academic_year_id == year.id)
        .order_by(
            SchoolClass.grade.asc().nullslast(),
            SchoolClass.letter.asc().nullslast(),
            SchoolClass.name.asc()
        )
        .all()
    )

    return render_template(
        "incidents_dashboard.html",
        title="Инциденты — дашборд",
        total_all=total_all,
        total_7=total_7,
        total_30=total_30,
        top_categories=top_categories,
        top_classes=top_classes,
        top_buildings=top_buildings,
        rows=rows,
        recent_daily=recent_daily,
        max_daily=max_daily,
        max_category=max_category,
        max_class=max_class,
        max_building=max_building,
        grade=grade,
        class_id=class_id,
        category=category,
        categories=INCIDENT_CATEGORIES,
        classes=classes,
    )


# =========================================================
# BUILDINGS
# =========================================================
@children_bp.route("/buildings")
@require_roles("ADMIN")
def buildings_registry():
    buildings = Building.query.order_by(Building.name.asc()).all()
    return render_template("buildings_list.html", buildings=buildings)


@children_bp.route("/buildings/new", methods=["POST"])
@require_roles("ADMIN")
def buildings_new():
    name = (request.form.get("name") or "").strip()
    address = (request.form.get("address") or "").strip() or None
    short_name = (request.form.get("short_name") or "").strip() or None

    if not name:
        flash("Укажите название здания", "danger")
        return redirect(url_for("children.buildings_registry"))

    db.session.add(Building(name=name, address=address, short_name=short_name))
    db.session.commit()
    flash("Здание добавлено", "success")
    return redirect(url_for("children.buildings_registry"))


@children_bp.route("/buildings/<int:building_id>/update", methods=["POST"])
@require_roles("ADMIN")
def buildings_update(building_id: int):
    b = Building.query.get_or_404(building_id)

    b.name = (request.form.get("name") or "").strip()
    b.short_name = (request.form.get("short_name") or "").strip() or None
    b.address = (request.form.get("address") or "").strip() or None

    if not b.name:
        flash("Название здания не может быть пустым", "danger")
        return redirect(url_for("children.buildings_registry"))

    db.session.commit()
    flash("Сохранено", "success")
    return redirect(url_for("children.buildings_registry"))


@children_bp.route("/buildings/<int:building_id>/delete", methods=["POST"])
@require_roles("ADMIN")
def buildings_delete(building_id: int):
    b = Building.query.get_or_404(building_id)

    SchoolClass.query.filter_by(building_id=b.id).update({"building_id": None})
    db.session.delete(b)
    db.session.commit()

    flash("Здание удалено", "success")
    return redirect(url_for("children.buildings_registry"))


# =========================================================
# SOCIAL PASSPORT REGISTRY / DASHBOARD
# =========================================================
@children_bp.route("/social-passport")
@login_required
def social_passport_registry():
    if not has_permission("social_passport_registry_view"):
        abort(403)

    year = _get_current_year()
    if not year:
        flash("Не найден текущий учебный год", "danger")
        return redirect(url_for("children.home"))

    grade = parse_int(request.args.get("grade"))
    class_id = parse_int(request.args.get("class_id"))
    q_text = (request.args.get("q") or "").strip()

    q = (
        Child.query
        .outerjoin(
            ChildEnrollment,
            (ChildEnrollment.child_id == Child.id)
            & (ChildEnrollment.academic_year_id == year.id)
            & (ChildEnrollment.ended_at.is_(None))
        )
        .outerjoin(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        .outerjoin(ChildSocial, ChildSocial.child_id == Child.id)
    )

    is_admin_user = has_role("ADMIN")
    is_methodist_user = has_role("METHODIST")
    is_class_teacher_user = has_role("CLASS_TEACHER")

    if is_class_teacher_user and not (is_admin_user or is_methodist_user):
        q = q.filter(SchoolClass.teacher_user_id == current_user.id)

    if grade is not None:
        q = q.filter(SchoolClass.grade == grade)
    if class_id:
        q = q.filter(SchoolClass.id == class_id)
    if q_text:
        like = f"%{q_text}%"
        q = q.filter(db.or_(
            Child.last_name.ilike(like),
            Child.first_name.ilike(like),
            Child.middle_name.ilike(like),
        ))

    classes_query = SchoolClass.query.filter_by(academic_year_id=year.id)
    if is_class_teacher_user and not (is_admin_user or is_methodist_user):
        classes_query = classes_query.filter(SchoolClass.teacher_user_id == current_user.id)
    if grade is not None:
        classes_query = classes_query.filter(SchoolClass.grade == grade)
    classes = classes_query.order_by(SchoolClass.grade.asc().nullslast(), SchoolClass.name.asc()).all()
    grades = sorted({c.grade for c in classes if c.grade is not None})

    children = q.order_by(SchoolClass.grade.asc().nullslast(), SchoolClass.name.asc(), Child.last_name.asc(), Child.first_name.asc()).all()

    return render_template(
        "social_passport_registry.html",
        children=children,
        year=year,
        classes=classes,
        grades=grades,
        selected_grade=grade,
        selected_class_id=class_id,
        q_text=q_text,
        is_admin=is_admin_user,
        is_methodist=is_methodist_user,
        is_class_teacher=is_class_teacher_user,
    )


@children_bp.route("/comments/registry")
@login_required
def comments_registry():
    if not has_permission("children_registry_view"):
        abort(403)

    year = _get_current_year()
    q_text = (request.args.get("q") or "").strip()
    grade = parse_int(request.args.get("grade"))
    class_id = parse_int(request.args.get("class_id"))

    q = (
        ChildComment.query
        .join(Child, Child.id == ChildComment.child_id)
        .outerjoin(
            ChildEnrollment,
            (ChildEnrollment.child_id == Child.id)
            & (ChildEnrollment.academic_year_id == (year.id if year else 0))
            & (ChildEnrollment.ended_at.is_(None))
        )
        .outerjoin(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        .outerjoin(User, User.id == ChildComment.author_id)
    )

    if has_role("CLASS_TEACHER") and not (has_role("ADMIN") or has_role("METHODIST")):
        q = q.filter(SchoolClass.teacher_user_id == current_user.id)

    if grade is not None:
        q = q.filter(SchoolClass.grade == grade)
    if class_id:
        q = q.filter(SchoolClass.id == class_id)
    if q_text:
        like = f"%{q_text}%"
        q = q.filter(db.or_(
            Child.last_name.ilike(like), Child.first_name.ilike(like), Child.middle_name.ilike(like),
            ChildComment.text.ilike(like), User.last_name.ilike(like), User.first_name.ilike(like)
        ))

    classes_q = SchoolClass.query
    if year:
        classes_q = classes_q.filter_by(academic_year_id=year.id)
    if has_role("CLASS_TEACHER") and not (has_role("ADMIN") or has_role("METHODIST")):
        classes_q = classes_q.filter(SchoolClass.teacher_user_id == current_user.id)
    if grade is not None:
        classes_q = classes_q.filter(SchoolClass.grade == grade)
    classes = classes_q.order_by(SchoolClass.grade.asc().nullslast(), SchoolClass.name.asc()).all()
    grades = sorted({c.grade for c in classes if c.grade is not None})
    comments = q.order_by(ChildComment.created_at.desc()).all()

    return render_template(
        "comments_registry.html",
        comments=comments,
        classes=classes,
        grades=grades,
        selected_grade=grade,
        selected_class_id=class_id,
        q_text=q_text,
    )


@children_bp.route("/social-passport/dashboard")
@require_roles("ADMIN")
def social_passport_dashboard():
    year = _get_current_year()
    if not year:
        flash("Не найден текущий учебный год", "danger")
        return redirect(url_for("children.home"))

    base = (
        Child.query
        .outerjoin(
            ChildEnrollment,
            (ChildEnrollment.child_id == Child.id)
            & (ChildEnrollment.academic_year_id == year.id)
            & (ChildEnrollment.ended_at.is_(None))
        )
        .outerjoin(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        .outerjoin(Building, Building.id == SchoolClass.building_id)
        .outerjoin(ChildSocial, ChildSocial.child_id == Child.id)
    )

    children = base.distinct().all()

    def s(ch):
        return ch.social

    totals = {
        "school_total": len(children),
        "large_family": sum(1 for ch in children if s(ch) and s(ch).has_large_family),
        "low_income": sum(1 for ch in children if s(ch) and s(ch).has_low_income_family),
        "guardianship": sum(1 for ch in children if s(ch) and s(ch).has_guardianship),
        "orphan": sum(1 for ch in children if s(ch) and s(ch).has_orphan_status),
        "parents_disability": sum(1 for ch in children if s(ch) and s(ch).has_disability_parents),
        "socially_dangerous": sum(1 for ch in children if s(ch) and s(ch).is_socially_dangerous),
        "hard_life": sum(1 for ch in children if s(ch) and s(ch).is_hard_life),
    }

    by_building = {}
    for ch in children:
        bname = "Без здания"
        if ch.current_building:
            bname = ch.current_building.name

        if bname not in by_building:
            by_building[bname] = {
                "total": 0,
                "large_family": 0,
                "low_income": 0,
                "guardianship": 0,
                "orphan": 0,
                "parents_disability": 0,
                "socially_dangerous": 0,
                "hard_life": 0,
            }

        row = by_building[bname]
        social = ch.social

        row["total"] += 1
        row["large_family"] += 1 if social and social.has_large_family else 0
        row["low_income"] += 1 if social and social.has_low_income_family else 0
        row["guardianship"] += 1 if social and social.has_guardianship else 0
        row["orphan"] += 1 if social and social.has_orphan_status else 0
        row["parents_disability"] += 1 if social and social.has_disability_parents else 0
        row["socially_dangerous"] += 1 if social and social.is_socially_dangerous else 0
        row["hard_life"] += 1 if social and social.is_hard_life else 0

    return render_template(
        "social_passport_dashboard.html",
        totals=totals,
        by_building=by_building
    )


# =========================================================
# SUBJECTS
# =========================================================
@children_bp.route("/subjects")
@require_roles("ADMIN")
def subjects_registry():
    q = (request.args.get("q") or "").strip().lower()

    subjects = Subject.query.order_by(Subject.name.asc()).all()
    if q:
        subjects = [s for s in subjects if q in (s.name or "").lower()]

    return render_template(
        "subjects_list.html",
        subjects=subjects,
        q=q
    )


@children_bp.route("/subjects/new", methods=["POST"])
@require_roles("ADMIN")
def subjects_new():
    name = (request.form.get("name") or "").strip()
    short_name = (request.form.get("short_name") or "").strip() or None

    if not name:
        flash("Укажите название предмета", "danger")
        return redirect(url_for("children.subjects_registry"))

    exists = Subject.query.filter(db.func.lower(Subject.name) == name.lower()).first()
    if exists:
        flash("Такой предмет уже существует", "warning")
        return redirect(url_for("children.subjects_registry"))

    db.session.add(Subject(name=name, short_name=short_name))
    db.session.commit()
    flash("Предмет добавлен", "success")
    return redirect(url_for("children.subjects_registry"))


@children_bp.route("/subjects/<int:subject_id>/update", methods=["POST"])
@require_roles("ADMIN")
def subjects_update(subject_id: int):
    subject = Subject.query.get_or_404(subject_id)

    name = (request.form.get("name") or "").strip()
    short_name = (request.form.get("short_name") or "").strip() or None

    if not name:
        flash("Название предмета не может быть пустым", "danger")
        return redirect(url_for("children.subjects_registry"))

    exists = (
        Subject.query
        .filter(db.func.lower(Subject.name) == name.lower(), Subject.id != subject.id)
        .first()
    )
    if exists:
        flash("Предмет с таким названием уже существует", "warning")
        return redirect(url_for("children.subjects_registry"))

    subject.name = name
    subject.short_name = short_name
    db.session.commit()
    flash("Предмет сохранён", "success")
    return redirect(url_for("children.subjects_registry"))


@children_bp.route("/subjects/<int:subject_id>/delete", methods=["POST"])
@require_roles("ADMIN")
def subjects_delete(subject_id: int):
    subject = Subject.query.get_or_404(subject_id)

    has_debts = Debt.query.filter_by(subject_id=subject.id).first() is not None
    if has_debts:
        flash("Нельзя удалить предмет: он уже используется в задолженностях", "danger")
        return redirect(url_for("children.subjects_registry"))

    db.session.delete(subject)
    db.session.commit()
    flash("Предмет удалён", "success")
    return redirect(url_for("children.subjects_registry"))

# =========================================================
# ACADEMIC YEARS
# =========================================================
@children_bp.route("/academic-years")
@require_roles("ADMIN")
def academic_years_registry():
    years = AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).all()
    return render_template("academic_years_list.html", years=years)


@children_bp.route("/academic-years/new", methods=["POST"])
@require_roles("ADMIN")
def academic_years_new():
    name = (request.form.get("name") or "").strip()
    start_date = parse_date(request.form.get("start_date"))
    end_date = parse_date(request.form.get("end_date"))
    make_current = as_checkbox(request.form, "is_current")

    if not name:
        flash("Укажите название учебного года", "danger")
        return redirect(url_for("children.academic_years_registry"))

    exists = AcademicYear.query.filter_by(name=name).first()
    if exists:
        flash("Такой учебный год уже существует", "warning")
        return redirect(url_for("children.academic_years_registry"))

    if make_current:
        AcademicYear.query.update({"is_current": False})

    y = AcademicYear(
        name=name,
        start_date=start_date,
        end_date=end_date,
        is_current=make_current,
    )
    db.session.add(y)
    db.session.commit()

    flash("Учебный год добавлен", "success")
    return redirect(url_for("children.academic_years_registry"))


@children_bp.route("/academic-years/create-next", methods=["POST"])
@require_roles("ADMIN")
def academic_year_create_next():
    current = _get_current_year()
    base = current or AcademicYear.query.order_by(AcademicYear.start_date.desc().nullslast(), AcademicYear.name.desc()).first()
    if not base:
        flash("Сначала создайте хотя бы один учебный год вручную", "warning")
        return redirect(url_for("children.academic_years_registry"))

    if base.start_date and base.end_date:
        start_date = base.start_date.replace(year=base.start_date.year + 1)
        end_date = base.end_date.replace(year=base.end_date.year + 1)
        name = f"{start_date.year}/{end_date.year}"
    else:
        parts = (base.name or "").replace('-', '/').split('/')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            name = f"{int(parts[0])+1}/{int(parts[1])+1}"
            start_date = date(int(parts[0])+1, 9, 1)
            end_date = date(int(parts[1])+1, 8, 31)
        else:
            flash("Не удалось автоматически определить следующий учебный год", "danger")
            return redirect(url_for("children.academic_years_registry"))

    if AcademicYear.query.filter_by(name=name).first():
        flash(f"Учебный год {name} уже существует", "warning")
        return redirect(url_for("children.academic_years_registry"))

    new_year = AcademicYear(name=name, start_date=start_date, end_date=end_date, is_current=False)
    db.session.add(new_year)
    db.session.commit()
    flash(f"Создан следующий учебный год: {name}", "success")
    return redirect(url_for("children.academic_years_registry"))


@children_bp.route("/academic-years/<int:year_id>/toggle-closed", methods=["POST"])
@require_roles("ADMIN")
def academic_year_toggle_closed(year_id: int):
    year = AcademicYear.query.get_or_404(year_id)
    year.is_closed = not bool(getattr(year, 'is_closed', False))
    db.session.commit()
    flash("Статус учебного года обновлён", "success")
    return redirect(url_for("children.academic_years_registry"))


@children_bp.route("/academic-years/<int:year_id>/toggle-archive", methods=["POST"])
@require_roles("ADMIN")
def academic_year_toggle_archive(year_id: int):
    year = AcademicYear.query.get_or_404(year_id)
    year.is_archived = not bool(getattr(year, 'is_archived', False))
    db.session.commit()
    flash("Архивный статус учебного года обновлён", "success")
    return redirect(url_for("children.academic_years_registry"))


@children_bp.route("/academic-years/<int:year_id>/make-current", methods=["POST"])
@require_roles("ADMIN")
def academic_year_make_current(year_id: int):
    year = AcademicYear.query.get_or_404(year_id)

    AcademicYear.query.update({"is_current": False})
    year.is_current = True
    db.session.commit()

    flash(f"Текущий учебный год: {year.name}", "success")
    return redirect(url_for("children.academic_years_registry"))


@children_bp.route("/academic-years/<int:year_id>/update", methods=["POST"])
@require_roles("ADMIN")
def academic_year_update(year_id: int):
    year = AcademicYear.query.get_or_404(year_id)

    name = (request.form.get("name") or "").strip()
    start_date = parse_date(request.form.get("start_date"))
    end_date = parse_date(request.form.get("end_date"))

    if not name:
        flash("Название учебного года не может быть пустым", "danger")
        return redirect(url_for("children.academic_years_registry"))

    exists = (
        AcademicYear.query
        .filter(AcademicYear.name == name, AcademicYear.id != year.id)
        .first()
    )
    if exists:
        flash("Учебный год с таким названием уже существует", "warning")
        return redirect(url_for("children.academic_years_registry"))

    year.name = name
    year.start_date = start_date
    year.end_date = end_date

    db.session.commit()
    flash("Учебный год сохранён", "success")
    return redirect(url_for("children.academic_years_registry"))

@children_bp.route("/subjects/import", methods=["GET", "POST"])
@require_roles("ADMIN")
def subjects_import():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Выберите Excel файл", "danger")
            return redirect(url_for("children.subjects_registry"))

        wb = load_workbook(f, data_only=True)
        ws = wb.active

        headers = [(str(cell.value).strip() if cell.value is not None else "") for cell in ws[1]]
        idx = {h: i for i, h in enumerate(headers)}

        if "name" not in idx:
            flash("В файле должна быть колонка: name", "danger")
            return redirect(url_for("children.subjects_registry"))

        created = 0
        skipped = 0

        for r in range(2, ws.max_row + 1):
            row = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]

            name = str(row[idx["name"]] or "").strip()
            short_name = None
            if "short_name" in idx:
                short_name = str(row[idx["short_name"]] or "").strip() or None

            if not name:
                skipped += 1
                continue

            exists = Subject.query.filter(db.func.lower(Subject.name) == name.lower()).first()
            if exists:
                skipped += 1
                continue

            db.session.add(Subject(name=name, short_name=short_name))
            created += 1

        db.session.commit()
        flash(f"Импорт завершён. Добавлено: {created}, пропущено: {skipped}", "success")
        return redirect(url_for("children.subjects_registry"))

    return render_template("subjects_import.html")

@children_bp.route("/children/import-parents", methods=["GET", "POST"])
@require_roles("ADMIN")
def parents_import():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Выберите Excel файл", "danger")
            return redirect(url_for("children.parents_import"))

        wb = load_workbook(f, data_only=True)
        ws = wb.active

        headers = [(str(cell.value).strip() if cell.value is not None else "") for cell in ws[1]]
        idx = {h: i for i, h in enumerate(headers)}

        required = [
            "ФИО",
            "Дата рождения",
            "Тип представителя",
            "ФИО представителя",
            "Телефон представителя",
            "E-mail представителя",
        ]
        missing = [c for c in required if c not in idx]
        if missing:
            flash(f"Не хватает колонок: {', '.join(missing)}", "danger")
            return redirect(url_for("children.parents_import"))

        created_links = 0
        created_parents = 0
        skipped = 0
        not_found = 0

        def parse_birth(x):
            if not x:
                return None
            if isinstance(x, datetime):
                return x.date()
            if isinstance(x, date):
                return x
            s = str(x).strip()
            m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", s)
            if m:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None

        def split_fio(full_fio: str):
            parts = [p.strip() for p in str(full_fio or "").split() if p.strip()]
            last_name = parts[0] if len(parts) > 0 else None
            first_name = parts[1] if len(parts) > 1 else None
            middle_name = parts[2] if len(parts) > 2 else None
            return last_name, first_name, middle_name

        def normalize_relation(value: str):
            s = (value or "").strip().lower()
            if s == "мать":
                return "mother"
            if s == "отец":
                return "father"
            if s == "опекун":
                return "guardian"
            return "other"

        def split_multi_values(raw: str):
            if not raw:
                return []
            parts = re.split(r"[,\n;]+", str(raw))
            return [p.strip() for p in parts if p and p.strip()]

        for r in range(2, ws.max_row + 1):
            row = [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]

            child_fio = str(row[idx["ФИО"]] or "").strip()
            child_birth_date = parse_birth(row[idx["Дата рождения"]])

            relation_raw = str(row[idx["Тип представителя"]] or "").strip()
            parent_fio = str(row[idx["ФИО представителя"]] or "").strip()

            raw_phone = str(row[idx["Телефон представителя"]] or "").strip()
            raw_email = str(row[idx["E-mail представителя"]] or "").strip()

            parent_phone = None
            parent_email = None
            notes_parts = []

            phone_list = split_multi_values(raw_phone)
            if phone_list:
                parent_phone = phone_list[0][:50]
                if len(phone_list) > 1:
                    notes_parts.append("Доп. телефоны: " + ", ".join(phone_list[1:]))

            email_list = split_multi_values(raw_email)
            if email_list:
                parent_email = email_list[0][:120]
                if len(email_list) > 1:
                    notes_parts.append("Доп. e-mail: " + ", ".join(email_list[1:]))

            parent_notes = "\n".join(notes_parts) if notes_parts else None

            if not child_fio or not parent_fio:
                skipped += 1
                continue

            child_last_name, child_first_name, child_middle_name = split_fio(child_fio)

            q = Child.query.filter(
                db.func.lower(Child.last_name) == (child_last_name or "").lower(),
                db.func.lower(Child.first_name) == (child_first_name or "").lower(),
            )

            if child_middle_name:
                q = q.filter(db.func.lower(Child.middle_name) == child_middle_name.lower())

            if child_birth_date:
                q = q.filter(Child.birth_date == child_birth_date)

            child = q.first()

            if not child:
                not_found += 1
                continue

            relation_type = normalize_relation(relation_raw)

            existing_parent = Parent.query.filter(
                db.func.lower(Parent.fio) == parent_fio.lower()
            ).first()

            if existing_parent:
                parent = existing_parent

                if parent_phone and not parent.phone:
                    parent.phone = parent_phone

                if parent_email and not parent.email:
                    parent.email = parent_email

                if parent_notes:
                    old_notes = (parent.notes or "").strip()
                    if old_notes:
                        if parent_notes not in old_notes:
                            parent.notes = old_notes + "\n" + parent_notes
                    else:
                        parent.notes = parent_notes
            else:
                parent = Parent(
                    fio=parent_fio,
                    phone=parent_phone,
                    email=parent_email,
                    notes=parent_notes,
                )
                db.session.add(parent)
                db.session.flush()
                created_parents += 1

            exists_link = ChildParent.query.filter_by(
                child_id=child.id,
                parent_id=parent.id,
                relation_type=relation_type
            ).first()

            if not exists_link:
                link = ChildParent(
                    child_id=child.id,
                    parent_id=parent.id,
                    relation_type=relation_type,
                    is_legal_representative=True,
                )
                db.session.add(link)
                created_links += 1
            else:
                skipped += 1

        db.session.commit()

        flash(
            f"Импорт родителей завершён. "
            f"Создано представителей: {created_parents}, "
            f"создано связей: {created_links}, "
            f"не найдено детей: {not_found}, "
            f"пропущено: {skipped}",
            "success"
        )
        return redirect(url_for("children.list_children"))

    return render_template("parents_import.html")

@children_bp.route("/classes/copy-from-year", methods=["POST"])
@require_roles("ADMIN")
def classes_copy_from_year():
    target_year_id = request.form.get("target_year_id", type=int)
    source_year_id = request.form.get("source_year_id", type=int)
    target_year = AcademicYear.query.get_or_404(target_year_id)
    source_year = AcademicYear.query.get_or_404(source_year_id)

    created = 0
    source_classes = SchoolClass.query.filter_by(academic_year_id=source_year.id).order_by(SchoolClass.name.asc()).all()
    for sc in source_classes:
        exists = SchoolClass.query.filter_by(academic_year_id=target_year.id, building_id=sc.building_id, name=sc.name).first()
        if exists:
            continue
        clone = SchoolClass(
            academic_year_id=target_year.id,
            building_id=sc.building_id,
            name=sc.name,
            grade=sc.grade,
            letter=sc.letter,
            max_students=sc.max_students,
            teacher_user_id=sc.teacher_user_id,
            is_active=True,
        )
        db.session.add(clone)
        created += 1
    db.session.commit()
    flash(f"Скопировано классов: {created}", "success")
    return redirect(url_for("children.classes_registry", academic_year_id=target_year.id))


@children_bp.route("/classes/<int:class_id>/delete", methods=["POST"])
@require_roles("ADMIN")
def classes_delete(class_id: int):
    c = SchoolClass.query.get_or_404(class_id)

    teacher_user_id = c.teacher_user_id

    has_children = (
        ChildEnrollment.query
        .filter(
            ChildEnrollment.school_class_id == c.id,
            ChildEnrollment.ended_at.is_(None)
        )
        .first()
        is not None
    )

    if has_children:
        flash("Нельзя удалить класс: в нём есть активные дети", "danger")
        return redirect(url_for("children.classes_registry"))

    db.session.delete(c)
    db.session.flush()

    _sync_class_teacher_role(teacher_user_id)

    db.session.commit()
    flash("Класс удалён", "success")
    return redirect(url_for("children.classes_registry"))

@children_bp.route("/registry/kdn")
@login_required
def registry_kdn():
    year = _get_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())
    if not year:
        flash("Не найден текущий учебный год", "danger")
        return redirect(url_for("children.home"))

    q = (
        Child.query
        .outerjoin(
            ChildEnrollment,
            (ChildEnrollment.child_id == Child.id)
            & (ChildEnrollment.academic_year_id == year.id)
            & (ChildEnrollment.ended_at.is_(None))
        )
        .outerjoin(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        .outerjoin(ChildSocial, ChildSocial.child_id == Child.id)
        .filter(ChildSocial.kdn_since.isnot(None))
    )

    if filters["selected_grade"] is not None:
        q = q.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        q = q.filter(SchoolClass.id == filters["selected_class_id"])

    children = q.order_by(SchoolClass.name.asc(), Child.last_name.asc(), Child.first_name.asc()).all()

    if filters["q_text"]:
        children = [ch for ch in children if _match_fio_query(ch, filters["q_text"])]

    return render_template(
        "registry_children.html",
        title="Реестр КДН",
        children=children,
        q_text=filters["q_text"],
        classes=filters["classes"],
        grades=filters["grades"],
        selected_grade=filters["selected_grade"],
        selected_class_id=filters["selected_class_id"],
        export_url=url_for("children.registry_kdn_export", grade=filters["selected_grade_raw"], class_id=filters["selected_class_id"], q=filters["q_text"])
    )
    
@children_bp.route("/registry/kdn/export")
@login_required
def registry_kdn_export():
    year = _get_current_year()
    filters = _registry_filter_state(year, allow_only_own_class=should_limit_children_to_own_class())
    if not year:
        flash("Не найден текущий учебный год", "danger")
        return redirect(url_for("children.home"))

    q = (
        Child.query
        .outerjoin(
            ChildEnrollment,
            (ChildEnrollment.child_id == Child.id)
            & (ChildEnrollment.academic_year_id == year.id)
            & (ChildEnrollment.ended_at.is_(None))
        )
        .outerjoin(SchoolClass, SchoolClass.id == ChildEnrollment.school_class_id)
        .outerjoin(ChildSocial, ChildSocial.child_id == Child.id)
        .filter(ChildSocial.kdn_since.isnot(None))
    )

    if filters["selected_grade"] is not None:
        q = q.filter(SchoolClass.grade == filters["selected_grade"])
    if filters["selected_class_id"]:
        q = q.filter(SchoolClass.id == filters["selected_class_id"])

    children = q.order_by(Child.last_name.asc(), Child.first_name.asc()).all()

    if filters["q_text"]:
        children = [ch for ch in children if _match_fio_query(ch, filters["q_text"])]

    return _export_children_xlsx("Реестр_КДН", children)

@children_bp.route("/admin/roles", methods=["GET", "POST"])
@require_roles("ADMIN")
def roles_admin():
    if request.method == "POST":
        user_id = request.form.get("user_id", type=int)
        selected_role_codes = request.form.getlist("roles")

        user = User.query.get_or_404(user_id)

        editable_roles = Role.query.filter(Role.code != "CLASS_TEACHER").all()
        editable_role_ids = [r.id for r in editable_roles]

        UserRole.query.filter(
            UserRole.user_id == user.id,
            UserRole.role_id.in_(editable_role_ids)
        ).delete(synchronize_session=False)

        for code in selected_role_codes:
            if code == "CLASS_TEACHER":
                continue

            role = Role.query.filter_by(code=code).first()
            if role:
                db.session.add(UserRole(user_id=user.id, role_id=role.id))

        db.session.commit()
        flash("Роли пользователя сохранены", "success")
        return redirect(url_for("children.roles_admin", q=request.args.get("q", "")))

    q = (request.args.get("q") or "").strip().lower()

    users = User.query.order_by(
        User.last_name.asc(),
        User.first_name.asc(),
        User.middle_name.asc()
    ).all()

    if q:
        def match_user(u):
            text = " ".join([
                u.fio or "",
                u.username or "",
                u.phone or "",
                u.email or "",
            ]).lower()
            return q in text

        users = [u for u in users if match_user(u)]

    roles = Role.query.order_by(Role.name.asc()).all()

    rows = []
    for u in users:
        rows.append({
            "user": u,
            "role_codes": set(u.role_codes),
        })

    return render_template(
        "roles_admin.html",
        rows=rows,
        roles=roles,
        q=q,
    )

