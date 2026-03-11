from datetime import datetime, date

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db


# =========================
# ACADEMIC YEAR
# =========================
class AcademicYear(db.Model):
    __tablename__ = "academic_year"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False, unique=True)   # "2025/2026"
    is_current = db.Column(db.Boolean, default=False, nullable=False)

    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_closed = db.Column(db.Boolean, default=False, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<AcademicYear {self.name}>"



# =========================
# BUILDING
# =========================
class Building(db.Model):
    __tablename__ = "buildings"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    short_name = db.Column(db.String(50), nullable=True)
    address = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Building {self.name}>"



# =========================
# USER
# =========================
class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(120), unique=True, nullable=False)

    last_name = db.Column(db.String(120), nullable=True)
    first_name = db.Column(db.String(120), nullable=True)
    middle_name = db.Column(db.String(120), nullable=True)

    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(32), nullable=True)
    email = db.Column(db.String(120), nullable=True)

    role = db.Column(db.String(30), nullable=False, default="VIEWER")

    is_active_user = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    employment_status = db.Column(db.String(30), nullable=False, default="ACTIVE")
    dismissal_date = db.Column(db.Date, nullable=True)
    archived_at = db.Column(db.DateTime, nullable=True)

    roles = db.relationship(
        "Role",
        secondary="user_role",
        lazy="joined"
    )

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(
            password,
            method="pbkdf2:sha256",
            salt_length=16
        )

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def fio(self):
        parts = [
            (self.last_name or "").strip(),
            (self.first_name or "").strip(),
            (self.middle_name or "").strip(),
        ]
        return " ".join([p for p in parts if p])

    @property
    def role_codes(self):
        if self.roles:
            return [r.code for r in self.roles]

        if getattr(self, "role", None):
            return [self.role]

        return []

    def has_role(self, code: str) -> bool:
        return code in self.role_codes

    @property
    def is_active(self):
        return self.is_active_user

    def __repr__(self):
        return f"<User {self.username}>"

# =========================
# SCHOOL CLASS
# =========================
class SchoolClass(db.Model):
    __tablename__ = "school_class"

    id = db.Column(db.Integer, primary_key=True)

    academic_year_id = db.Column(
        db.Integer,
        db.ForeignKey("academic_year.id"),
        nullable=False,
        index=True
    )

    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=True,
        index=True
    )

    # Оставляем name для совместимости с текущими шаблонами/роутами
    # Примеры: "5А", "10ИТ", "7КРО"
    name = db.Column(db.String(20), nullable=False)

    # Дополнительная нормализованная структура
    grade = db.Column(db.Integer, nullable=True)          # 1..11, если есть
    letter = db.Column(db.String(10), nullable=True)      # "А", "Б", "ИТ", "КРО" и т.п.

    max_students = db.Column(db.Integer, default=25, nullable=False)

    teacher_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
        index=True
    )
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    academic_year = db.relationship("AcademicYear", backref=db.backref("classes", lazy=True))
    building = db.relationship("Building", backref=db.backref("classes", lazy=True))
    teacher_user = db.relationship("User", foreign_keys=[teacher_user_id])

    __table_args__ = (
        db.UniqueConstraint(
            "academic_year_id",
            "building_id",
            "name",
            name="uq_school_class_year_building_name"
        ),
    )

    @property
    def teacher_name(self):
        return self.teacher_user.fio if self.teacher_user else None

    @property
    def teacher_phone(self):
        return self.teacher_user.phone if self.teacher_user else None

    def __repr__(self):
        return f"<SchoolClass {self.name}>"



# =========================
# CHILD
# =========================
class Child(db.Model):
    __tablename__ = "child"

    id = db.Column(db.Integer, primary_key=True)

    last_name = db.Column(db.String(120), nullable=False)
    first_name = db.Column(db.String(120), nullable=False)
    middle_name = db.Column(db.String(120), nullable=True)

    birth_date = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(10), nullable=True)
    education_form = db.Column(db.String(100), nullable=True)   # Очная и т.д.
    actual_address = db.Column(db.String(500), nullable=True)
    temporary_address = db.Column(db.String(500), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    education_form = db.Column(db.String(50), nullable=True)

    reg_address = db.Column(db.String(255), nullable=True)  # регистрация по месту жительства
    temporary_address = db.Column(db.String(255), nullable=True)  # регистрация по месту пребывания
    actual_address = db.Column(db.String(255), nullable=True)  # фактический адрес

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="ACTIVE")
    archived_at = db.Column(db.DateTime, nullable=True)

    # Флаги сопровождения (можно оставить в child, это нормально)
    is_ovz = db.Column(db.Boolean, default=False, nullable=False)
    is_vshu = db.Column(db.Boolean, default=False, nullable=False)
    is_low = db.Column(db.Boolean, default=False, nullable=False)
    is_az = db.Column(db.Boolean, default=False, nullable=False)
    is_disabled = db.Column(db.Boolean, default=False, nullable=False)

    # ОВЗ
    ovz_level = db.Column(db.String(10), nullable=True)
    ovz_nosology = db.Column(db.String(20), nullable=True)
    ovz_variant = db.Column(db.Integer, nullable=True)
    ovz_doc_number = db.Column(db.String(100), nullable=True)
    ovz_doc_date = db.Column(db.Date, nullable=True)

    # Низкие результаты
    low_subjects = db.Column(db.String(255), nullable=True)
    low_notes = db.Column(db.Text, nullable=True)

    # Инвалидность
    disability_mse = db.Column(db.String(255), nullable=True)
    disability_from = db.Column(db.Date, nullable=True)
    disability_to = db.Column(db.Date, nullable=True)
    disability_ipra = db.Column(db.String(255), nullable=True)

    # relationships
    debts = db.relationship("Debt", backref="child", lazy=True, cascade="all, delete-orphan")
    documents = db.relationship("Document", backref="child", lazy=True, cascade="all, delete-orphan")

    @property
    def fio(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join([p.strip() for p in parts if p and str(p).strip()])

    @property
    def current_enrollment(self):
        try:
            current_year = AcademicYear.query.filter_by(is_current=True).first()
        except Exception:
            current_year = None

        if current_year:
            for e in (self.enrollments or []):
                if e.ended_at is None and e.academic_year_id == current_year.id:
                    return e

        for e in (self.enrollments or []):
            if e.ended_at is None:
                return e

        return None

    @property
    def current_class(self):
        e = self.current_enrollment
        return e.school_class if e and e.school_class else None

    @property
    def current_class_name(self):
        sc = self.current_class
        return sc.name if sc else None

    @property
    def current_building(self):
        sc = self.current_class
        return sc.building if sc and sc.building else None

    def _parent_by_relation(self, relation_type: str):
        for link in (self.parent_links or []):
            if (link.relation_type or "").lower() == relation_type and link.parent:
                return link.parent
        return None

    @property
    def mother(self):
        return self._parent_by_relation("mother")

    @property
    def father(self):
        return self._parent_by_relation("father")

    @property
    def mother_fio(self):
        return self.mother.fio if self.mother else None

    @property
    def mother_phone(self):
        return self.mother.phone if self.mother else None

    @property
    def father_fio(self):
        return self.father.fio if self.father else None

    @property
    def father_phone(self):
        return self.father.phone if self.father else None

    def __repr__(self):
        return f"<Child {self.fio}>"



# =========================
# CHILD ENROLLMENT
# =========================
class ChildEnrollment(db.Model):
    __tablename__ = "child_enrollment"

    id = db.Column(db.Integer, primary_key=True)

    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=False, index=True)
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)

    # ACTIVE / TRANSFERRED / REPEAT / EXPELLED / GRADUATED
    status = db.Column(db.String(30), default="ACTIVE", nullable=False)

    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)

    note = db.Column(db.String(255), nullable=True)
    transfer_order_number = db.Column(db.String(100), nullable=True)
    transfer_order_date = db.Column(db.Date, nullable=True)

    child = db.relationship(
        "Child",
        backref=db.backref("enrollments", cascade="all, delete-orphan", lazy=True)
    )
    academic_year = db.relationship("AcademicYear")
    school_class = db.relationship("SchoolClass")

    def __repr__(self):
        return f"<ChildEnrollment child={self.child_id} class={self.school_class_id}>"



# =========================
# PARENTS / REPRESENTATIVES
# =========================
class Parent(db.Model):
    __tablename__ = "parent"

    id = db.Column(db.Integer, primary_key=True)

    fio = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(500), nullable=True)

    notes = db.Column(db.Text, nullable=True)
    retention_until = db.Column(db.Date, nullable=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Parent {self.fio}>"


class ChildParent(db.Model):
    __tablename__ = "child_parent"

    id = db.Column(db.Integer, primary_key=True)

    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("parent.id"), nullable=False, index=True)

    # mother / father / guardian / other
    relation_type = db.Column(db.String(30), nullable=False, default="other")
    is_legal_representative = db.Column(db.Boolean, nullable=False, default=True)
    note = db.Column(db.String(255), nullable=True)
    transfer_order_number = db.Column(db.String(100), nullable=True)
    transfer_order_date = db.Column(db.Date, nullable=True)

    child = db.relationship(
        "Child",
        backref=db.backref("parent_links", cascade="all, delete-orphan", lazy=True)
    )
    parent = db.relationship(
        "Parent",
        backref=db.backref("child_links", cascade="all, delete-orphan", lazy=True)
    )

    __table_args__ = (
        db.UniqueConstraint("child_id", "parent_id", "relation_type", name="uq_child_parent_relation"),
    )

    def __repr__(self):
        return f"<ChildParent child={self.child_id} parent={self.parent_id} rel={self.relation_type}>"



# =========================
# SOCIAL PASSPORT
# =========================
class ChildSocial(db.Model):
    __tablename__ = "child_social"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, unique=True, index=True)

    family_status = db.Column(db.String(100), nullable=True)
    living_conditions = db.Column(db.String(255), nullable=True)
    social_risk = db.Column(db.String(255), nullable=True)

    has_disability_parents = db.Column(db.Boolean, default=False, nullable=False)
    has_large_family = db.Column(db.Boolean, default=False, nullable=False)
    has_low_income_family = db.Column(db.Boolean, default=False, nullable=False)
    has_guardianship = db.Column(db.Boolean, default=False, nullable=False)
    has_orphan_status = db.Column(db.Boolean, default=False, nullable=False)
    has_refugee_status = db.Column(db.Boolean, default=False, nullable=False)

    vshu_since = db.Column(db.Date, nullable=True)
    vshu_reason = db.Column(db.Text, nullable=True)

    kdn_since = db.Column(db.Date, nullable=True)
    kdn_reason = db.Column(db.Text, nullable=True)

    pdn_since = db.Column(db.Date, nullable=True)
    pdn_reason = db.Column(db.Text, nullable=True)

    vshu_removed_at = db.Column(db.Date, nullable=True)
    vshu_remove_reason = db.Column(db.Text, nullable=True)

    aoop_variant_text = db.Column(db.String(255), nullable=True)

    is_socially_dangerous = db.Column(db.Boolean, default=False, nullable=False)
    is_hard_life = db.Column(db.Boolean, default=False, nullable=False)

    notes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    child = db.relationship(
        "Child",
        backref=db.backref("social", uselist=False, cascade="all, delete-orphan")
    )

    def __repr__(self):
        return f"<ChildSocial child={self.child_id}>"
# =========================
# ROLE
# =========================
class Role(db.Model):
    __tablename__ = "role"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)


class UserRole(db.Model):
    __tablename__ = "user_role"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"), primary_key=True)

    # ------------------------------
    # Flask-Login
    # ------------------------------

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    # ------------------------------
    # ФИО пользователя
    # ------------------------------

    @property
    def fio(self):
        parts = [
            self.last_name or "",
            self.first_name or "",
            self.middle_name or "",
        ]
        return " ".join(x for x in parts if x).strip()

    # ------------------------------
    # список кодов ролей
    # ------------------------------

    @property
    def role_codes(self):
        if self.roles:
            return [r.code for r in self.roles]

        if getattr(self, "role", None):
            return [self.role]

        return []

    # ------------------------------
    # проверка роли
    # ------------------------------

    def has_role(self, code: str) -> bool:
        return code in self.role_codes

    # ------------------------------
    # строковое представление
    # ------------------------------

    def __repr__(self):
        return f"<User {self.id} {self.fio}>"

# =========================
# SUBJECT
# =========================
class Subject(db.Model):
    __tablename__ = "subject"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    short_name = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f"<Subject {self.name}>"





# =========================
# DEPARTMENTS / TEACHER LOAD / METHODICAL DATA
# =========================
class Department(db.Model):
    __tablename__ = "department"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    code = db.Column(db.String(80), nullable=True, unique=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class DepartmentLeader(db.Model):
    __tablename__ = "department_leader"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    department = db.relationship("Department", backref=db.backref("leaders", cascade="all, delete-orphan", lazy=True))
    user = db.relationship("User", foreign_keys=[user_id])
    building = db.relationship("Building", foreign_keys=[building_id])


class DepartmentSubject(db.Model):
    __tablename__ = "department_subject"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)

    department = db.relationship("Department", backref=db.backref("subject_links", cascade="all, delete-orphan", lazy=True))
    subject = db.relationship("Subject", foreign_keys=[subject_id])

    __table_args__ = (db.UniqueConstraint("department_id", "subject_id", name="uq_department_subject"),)


class TeacherLoad(db.Model):
    __tablename__ = "teacher_load"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=True, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    building_id = db.Column(db.Integer, db.ForeignKey("buildings.id"), nullable=True, index=True)
    class_name = db.Column(db.String(255), nullable=True)
    grade = db.Column(db.Integer, nullable=True)
    group_name = db.Column(db.String(255), nullable=True)
    hours = db.Column(db.Float, nullable=False, default=0)
    subject_name = db.Column(db.String(255), nullable=True)
    building_name = db.Column(db.String(255), nullable=True)
    source_sheet = db.Column(db.String(255), nullable=True)
    row_number = db.Column(db.Integer, nullable=True)
    is_whole_class = db.Column(db.Boolean, nullable=False, default=False)
    is_meta_group = db.Column(db.Boolean, nullable=False, default=False)
    teacher_total_hours = db.Column(db.Float, nullable=True)
    retention_until = db.Column(db.Date, nullable=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    subject = db.relationship("Subject", foreign_keys=[subject_id])
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    department = db.relationship("Department", foreign_keys=[department_id])
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    building = db.relationship("Building", foreign_keys=[building_id])


class TeacherMckoResult(db.Model):
    __tablename__ = "teacher_mcko_result"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=True, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    passed_at = db.Column(db.Date, nullable=True)
    expires_at = db.Column(db.Date, nullable=True)
    level = db.Column(db.String(120), nullable=True)
    result_text = db.Column(db.String(255), nullable=True)
    retention_until = db.Column(db.Date, nullable=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    subject = db.relationship("Subject", foreign_keys=[subject_id])
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at < date.today())


class TeacherCourse(db.Model):
    __tablename__ = "teacher_course"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    provider = db.Column(db.String(255), nullable=True)
    hours = db.Column(db.Float, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    retention_until = db.Column(db.Date, nullable=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])

# =========================
# DEBT
# =========================
class Debt(db.Model):
    __tablename__ = "debt"

    id = db.Column(db.Integer, primary_key=True)

    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False, index=True)

    detected_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=True)

    status = db.Column(db.String(20), default="OPEN", nullable=False)   # OPEN / CLOSED
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    closed_by = db.relationship("User", foreign_keys=[closed_by_user_id])
    subject = db.relationship("Subject")

    def __repr__(self):
        return f"<Debt child={self.child_id} subject={self.subject_id}>"



# =========================
# DOCUMENT
# =========================
class Document(db.Model):
    __tablename__ = "document"

    id = db.Column(db.Integer, primary_key=True)

    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    debt_id = db.Column(db.Integer, db.ForeignKey("debt.id"), nullable=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)

    doc_type = db.Column(db.String(30), nullable=False, default="GENERAL")
    doc_date = db.Column(db.Date, nullable=True)

    original_name = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)

    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    title = db.Column(db.String(255), nullable=True)
    filename = db.Column(db.String(255), nullable=True)
    retention_until = db.Column(db.Date, nullable=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    is_hidden_by_retention = db.Column(db.Boolean, default=False, nullable=False)
    is_deleted_soft = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_user_id])
    deleted_by_user = db.relationship("User", foreign_keys=[deleted_by])
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    debt = db.relationship("Debt", backref=db.backref("documents", lazy=True))

    def __repr__(self):
        return f"<Document {self.original_name}>"



# =========================
# COMMENTS
# =========================
class ChildComment(db.Model):
    __tablename__ = "child_comments"

    id = db.Column(db.Integer, primary_key=True)

    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    child = db.relationship(
        "Child",
        backref=db.backref("comments", cascade="all, delete-orphan", lazy=True)
    )
    author = db.relationship("User")

    def __repr__(self):
        return f"<ChildComment child={self.child_id}>"



# =========================
# EVENTS (history)
# =========================
class ChildEvent(db.Model):
    __tablename__ = "child_events"

    id = db.Column(db.Integer, primary_key=True)

    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    event_type = db.Column(db.String(30), nullable=False, default="PROMOTION")

    from_class = db.Column(db.String(20), nullable=True)
    to_class = db.Column(db.String(20), nullable=True)

    promotion_kind = db.Column(db.String(20), nullable=False, default="NORMAL")
    reason = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    child = db.relationship(
        "Child",
        backref=db.backref("events", cascade="all, delete-orphan", lazy=True)
    )
    author = db.relationship("User")

    def __repr__(self):
        return f"<ChildEvent child={self.child_id} type={self.event_type}>"





# =========================
# CHILD TRANSFER HISTORY
# =========================
class ChildTransferHistory(db.Model):
    __tablename__ = "child_transfer_history"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    from_academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    to_academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    from_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    to_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    transfer_type = db.Column(db.String(30), nullable=False, default="MANUAL")
    transfer_date = db.Column(db.Date, nullable=True)
    order_number = db.Column(db.String(100), nullable=True)
    order_date = db.Column(db.Date, nullable=True)
    comment = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    child = db.relationship("Child", backref=db.backref("transfer_history", lazy=True, cascade="all, delete-orphan"))
    from_academic_year = db.relationship("AcademicYear", foreign_keys=[from_academic_year_id])
    to_academic_year = db.relationship("AcademicYear", foreign_keys=[to_academic_year_id])
    from_class = db.relationship("SchoolClass", foreign_keys=[from_class_id])
    to_class = db.relationship("SchoolClass", foreign_keys=[to_class_id])
    creator = db.relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<ChildTransferHistory child={self.child_id} type={self.transfer_type}>"


# =========================
# INCIDENTS
# =========================
class Incident(db.Model):
    __tablename__ = "incident"

    id = db.Column(db.Integer, primary_key=True)

    occurred_at = db.Column(db.DateTime, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    author = db.relationship("User", backref="incidents_created")

    def __repr__(self):
        return f"<Incident {self.category}>"


class IncidentChild(db.Model):
    __tablename__ = "incident_child"

    id = db.Column(db.Integer, primary_key=True)

    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)

    incident = db.relationship("Incident", backref="links")
    child = db.relationship("Child", backref="incident_links")

    __table_args__ = (
        db.UniqueConstraint("incident_id", "child_id", name="uq_incident_child"),
    )

    def __repr__(self):
        return f"<IncidentChild incident={self.incident_id} child={self.child_id}>"

# =========================
# CONTROL WORKS
# =========================
class ControlWork(db.Model):
    __tablename__ = "control_work"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False, index=True)
    theme = db.Column(db.String(255), nullable=False)
    work_date = db.Column(db.Date, nullable=True)
    deadline_date = db.Column(db.Date, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    grade5_percent = db.Column(db.Integer, nullable=False, default=85)
    grade4_percent = db.Column(db.Integer, nullable=False, default=65)
    grade3_percent = db.Column(db.Integer, nullable=False, default=45)
    retention_until = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    creator = db.relationship("User", foreign_keys=[created_by])
    subject_ref = db.relationship("Subject", foreign_keys=[subject_id])
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    tasks = db.relationship("ControlWorkTask", backref="control_work", lazy=True, cascade="all, delete-orphan")
    assignments = db.relationship("ControlWorkAssignment", backref="control_work", lazy=True, cascade="all, delete-orphan")

    @property
    def subject_name(self):
        return self.subject_ref.name if self.subject_ref else "—"


class ControlWorkTask(db.Model):
    __tablename__ = "control_work_task"

    id = db.Column(db.Integer, primary_key=True)
    control_work_id = db.Column(db.Integer, db.ForeignKey("control_work.id"), nullable=False, index=True)
    task_number = db.Column(db.Integer, nullable=False)
    max_score = db.Column(db.Integer, nullable=False, default=0)
    description = db.Column(db.String(255), nullable=True)
    topic = db.Column(db.String(255), nullable=True)


class ControlWorkAssignment(db.Model):
    __tablename__ = "control_work_assignment"

    id = db.Column(db.Integer, primary_key=True)
    control_work_id = db.Column(db.Integer, db.ForeignKey("control_work.id"), nullable=False, index=True)
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=False, default="ASSIGNED")

    school_class = db.relationship("SchoolClass", foreign_keys=[school_class_id])
    teacher = db.relationship("User", foreign_keys=[teacher_id])


class ControlWorkResult(db.Model):
    __tablename__ = "control_work_result"

    id = db.Column(db.Integer, primary_key=True)
    control_work_id = db.Column(db.Integer, db.ForeignKey("control_work.id"), nullable=False, index=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("control_work_assignment.id"), nullable=False, index=True)
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    total_score = db.Column(db.Integer, nullable=True)
    percent = db.Column(db.Float, nullable=True)
    mark = db.Column(db.Integer, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    grade5_percent = db.Column(db.Integer, nullable=False, default=85)
    grade4_percent = db.Column(db.Integer, nullable=False, default=65)
    grade3_percent = db.Column(db.Integer, nullable=False, default=45)
    retention_until = db.Column(db.Date, nullable=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assignment = db.relationship("ControlWorkAssignment", foreign_keys=[assignment_id])
    child = db.relationship("Child", foreign_keys=[child_id])
    school_class = db.relationship("SchoolClass", foreign_keys=[school_class_id])
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    creator = db.relationship("User", foreign_keys=[created_by])


# =========================
# CHILD MOVEMENT / SUPPORT / SYSTEM LOG
# =========================
class ChildMovement(db.Model):
    __tablename__ = "child_movement"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    movement_type = db.Column(db.String(30), nullable=False, index=True)  # enroll / transfer / leave / repeat / conditional
    movement_date = db.Column(db.Date, nullable=False, default=date.today)
    from_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True)
    to_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True)
    reason = db.Column(db.Text, nullable=True)
    order_number = db.Column(db.String(100), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    child = db.relationship("Child", foreign_keys=[child_id], backref=db.backref("movements", lazy=True, cascade="all, delete-orphan"))
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    from_class = db.relationship("SchoolClass", foreign_keys=[from_class_id])
    to_class = db.relationship("SchoolClass", foreign_keys=[to_class_id])
    creator = db.relationship("User", foreign_keys=[created_by])


class SupportCase(db.Model):
    __tablename__ = "support_case"

    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    support_type = db.Column(db.String(50), nullable=False, index=True)  # psychologist / social / administration / tutor
    status = db.Column(db.String(30), nullable=False, default="OPEN", index=True)
    description = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    child = db.relationship("Child", foreign_keys=[child_id], backref=db.backref("support_cases", lazy=True, cascade="all, delete-orphan"))
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    creator = db.relationship("User", foreign_keys=[created_by])


class SystemLog(db.Model):
    __tablename__ = "system_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    object_type = db.Column(db.String(100), nullable=True, index=True)
    object_id = db.Column(db.String(100), nullable=True, index=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User", foreign_keys=[user_id])


class SchoolOrder(db.Model):
    __tablename__ = "school_order"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), nullable=False, index=True)
    order_date = db.Column(db.Date, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    section = db.Column(db.String(50), nullable=False, index=True)
    executor = db.Column(db.String(255), nullable=True)
    author = db.Column(db.String(255), nullable=True)
    responsible_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    valid_until = db.Column(db.Date, nullable=True)
    original_submitted = db.Column(db.Boolean, nullable=False, default=False)
    approved_by_deputy = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    responsible_user = db.relationship("User", foreign_keys=[responsible_user_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])


class OrderResponsible(db.Model):
    __tablename__ = "order_responsible"

    id = db.Column(db.Integer, primary_key=True)
    section = db.Column(db.String(50), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User")


class OrderResponsibleLink(db.Model):
    __tablename__ = "order_responsible_link"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("school_order.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    order = db.relationship("SchoolOrder", backref=db.backref("responsible_links", cascade="all, delete-orphan", lazy=True))
    user = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("order_id", "user_id", name="uq_order_responsible_link"),)



# =========================
# OLYMPIADS / ВСОШ
# =========================
class OlympiadImportSession(db.Model):
    __tablename__ = "olympiad_import_session"

    id = db.Column(db.Integer, primary_key=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=True, index=True)
    stage = db.Column(db.String(30), nullable=False, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=True, index=True)
    subject_name = db.Column(db.String(255), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True, index=True)
    source_file_name = db.Column(db.String(255), nullable=True)
    imported_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    total_rows = db.Column(db.Integer, nullable=False, default=0)
    school_rows = db.Column(db.Integer, nullable=False, default=0)
    matched_rows = db.Column(db.Integer, nullable=False, default=0)
    unmatched_rows = db.Column(db.Integer, nullable=False, default=0)
    created_rows = db.Column(db.Integer, nullable=False, default=0)
    updated_rows = db.Column(db.Integer, nullable=False, default=0)
    duplicate_rows = db.Column(db.Integer, nullable=False, default=0)
    error_rows = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default="DONE")
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    subject = db.relationship("Subject", foreign_keys=[subject_id])
    department = db.relationship("Department", foreign_keys=[department_id])
    importer = db.relationship("User", foreign_keys=[imported_by])


class OlympiadResult(db.Model):
    __tablename__ = "olympiad_result"

    id = db.Column(db.Integer, primary_key=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey("academic_year.id"), nullable=False, index=True)
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=False, index=True)
    school_class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=True, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=True, index=True)
    subject_name = db.Column(db.String(255), nullable=True)
    stage = db.Column(db.String(30), nullable=False, index=True)
    class_study_text = db.Column(db.String(50), nullable=True)
    class_participation_text = db.Column(db.String(50), nullable=True)
    score = db.Column(db.Float, nullable=True)
    max_score = db.Column(db.Float, nullable=True)
    percent = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(100), nullable=True, index=True)
    reason = db.Column(db.Text, nullable=True)
    olympiad_date = db.Column(db.Date, nullable=True)
    publication_date = db.Column(db.Date, nullable=True)
    school_login = db.Column(db.String(50), nullable=True, index=True)
    school_ekis = db.Column(db.String(50), nullable=True, index=True)
    school_name = db.Column(db.String(255), nullable=True)
    source_file_name = db.Column(db.String(255), nullable=True)
    source_sheet_name = db.Column(db.String(255), nullable=True)
    source_row_number = db.Column(db.Integer, nullable=True)
    source_row_hash = db.Column(db.String(64), nullable=True, index=True)
    import_session_id = db.Column(db.Integer, db.ForeignKey("olympiad_import_session.id"), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_archived = db.Column(db.Boolean, nullable=False, default=False)

    child = db.relationship("Child", foreign_keys=[child_id], backref=db.backref("olympiad_results", lazy=True, cascade="all, delete-orphan"))
    school_class = db.relationship("SchoolClass", foreign_keys=[school_class_id])
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    department = db.relationship("Department", foreign_keys=[department_id])
    subject = db.relationship("Subject", foreign_keys=[subject_id])
    academic_year = db.relationship("AcademicYear", foreign_keys=[academic_year_id])
    creator = db.relationship("User", foreign_keys=[created_by])
    import_session = db.relationship("OlympiadImportSession", foreign_keys=[import_session_id], backref=db.backref("results", lazy=True))


class OlympiadUnmatchedRow(db.Model):
    __tablename__ = "olympiad_unmatched_row"

    id = db.Column(db.Integer, primary_key=True)
    import_session_id = db.Column(db.Integer, db.ForeignKey("olympiad_import_session.id"), nullable=False, index=True)
    raw_fio = db.Column(db.String(255), nullable=True)
    raw_class_study = db.Column(db.String(50), nullable=True)
    raw_class_participation = db.Column(db.String(50), nullable=True)
    raw_score = db.Column(db.String(50), nullable=True)
    raw_status = db.Column(db.String(100), nullable=True)
    raw_reason = db.Column(db.Text, nullable=True)
    raw_subject = db.Column(db.String(255), nullable=True)
    raw_stage = db.Column(db.String(100), nullable=True)
    raw_school_login = db.Column(db.String(50), nullable=True)
    raw_school_ekis = db.Column(db.String(50), nullable=True)
    raw_payload_json = db.Column(db.Text, nullable=True)
    unmatched_reason = db.Column(db.String(255), nullable=True)
    maybe_left_school = db.Column(db.Boolean, nullable=False, default=False)
    comment = db.Column(db.Text, nullable=True)
    resolution_status = db.Column(db.String(30), nullable=False, default="OPEN")
    resolved_child_id = db.Column(db.Integer, db.ForeignKey("child.id"), nullable=True, index=True)
    resolved_teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    resolved_department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    import_session = db.relationship(
        "OlympiadImportSession",
        backref=db.backref("unmatched_items", lazy=True, cascade="all, delete-orphan")
    )
    resolved_child = db.relationship("Child", foreign_keys=[resolved_child_id])
    resolved_teacher = db.relationship("User", foreign_keys=[resolved_teacher_id])
    resolved_department = db.relationship("Department", foreign_keys=[resolved_department_id])


class OlympiadSubjectMapping(db.Model):
    __tablename__ = "olympiad_subject_mapping"

    id = db.Column(db.Integer, primary_key=True)
    olympiad_subject_name = db.Column(db.String(255), nullable=False, unique=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey("department.id"), nullable=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    subject = db.relationship("Subject", foreign_keys=[subject_id])
    department = db.relationship("Department", foreign_keys=[department_id])


class OlympiadStageMapping(db.Model):
    __tablename__ = "olympiad_stage_mapping"

    id = db.Column(db.Integer, primary_key=True)
    source_stage_name = db.Column(db.String(255), nullable=False, unique=True)
    system_stage_code = db.Column(db.String(30), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
