from datetime import datetime
from decimal import Decimal

from sqlalchemy.dialects.postgresql import JSONB

from app.core.extensions import db


CALCULATION_JSON_TYPE = db.JSON().with_variant(JSONB(), "postgresql")

ROUNDING_RULES = ("HALF_UP", "HALF_EVEN")
PARAMETER_SET_STATUSES = ("DRAFT", "LOCKED")
COEFFICIENT_CALCULATION_KINDS = (
    "MULTIPLIER",
    "PERCENT",
    "GROUP_SIZE_RATIO",
)
COEFFICIENT_SCOPES = ("GROUP", "ACTIVITY", "EMPLOYEE", "LINE")
COEFFICIENT_CONDITION_KINDS = ("ALWAYS", "ACTIVITY", "PLAN_KIND")
ALLOWANCE_AMOUNT_KINDS = ("FIXED", "PERCENT")
ALLOWANCE_SCOPES = ("EMPLOYEE", "ASSIGNMENT", "TARIFF_LINE")
ALLOWANCE_BASE_KINDS = ("BASE", "SUBTOTAL")
CALCULATION_RUN_STATUSES = (
    "QUEUED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
)
TARIFF_COMPONENT_KINDS = (
    "INPUT",
    "COEFFICIENT",
    "ALLOWANCE",
    "MANUAL",
    "TOTAL",
)


class CalculationParameterSet(db.Model):
    __tablename__ = "calculation_parameter_set"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization_settings.id"),
        nullable=True,
        index=True,
    )
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=False)
    student_hour_rate = db.Column(db.Numeric(14, 6), nullable=False)
    periods_per_year = db.Column(
        db.Numeric(8, 3),
        nullable=False,
        default=Decimal("12"),
        server_default="12",
    )
    rounding_rule = db.Column(
        db.String(40),
        nullable=False,
        default="HALF_UP",
        server_default="HALF_UP",
    )
    currency_code = db.Column(
        db.String(3),
        nullable=False,
        default="RUB",
        server_default="RUB",
    )
    status = db.Column(
        db.String(30),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        index=True,
    )
    revision = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    updated_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    organization = db.relationship("OrganizationSettings")
    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "calculation_parameter_sets",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        db.CheckConstraint(
            "valid_to >= valid_from",
            name="ck_calculation_parameter_set_period",
        ),
        db.CheckConstraint(
            "student_hour_rate >= 0 AND periods_per_year > 0",
            name="ck_calculation_parameter_set_values",
        ),
        db.CheckConstraint(
            "rounding_rule IN ('HALF_UP','HALF_EVEN')",
            name="ck_calculation_parameter_set_rounding",
        ),
        db.CheckConstraint(
            "status IN ('DRAFT','LOCKED')",
            name="ck_calculation_parameter_set_status",
        ),
        db.CheckConstraint(
            "revision > 0",
            name="ck_calculation_parameter_set_revision",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "code",
            name="uq_calculation_parameter_set_version_code",
        ),
        db.Index(
            "ix_calculation_parameter_set_version_status",
            "tariff_version_id",
            "status",
        ),
    )


class TariffRateNorm(db.Model):
    __tablename__ = "tariff_rate_norm"

    id = db.Column(db.Integer, primary_key=True)
    parameter_set_id = db.Column(
        db.Integer,
        db.ForeignKey("calculation_parameter_set.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position_code = db.Column(db.String(80), nullable=False)
    position_name = db.Column(db.String(180), nullable=False)
    activity_kind = db.Column(db.String(40), nullable=True)
    weekly_norm_hours = db.Column(db.Numeric(8, 3), nullable=False)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=False)
    source_text = db.Column(db.String(500), nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    parameter_set = db.relationship(
        "CalculationParameterSet",
        backref=db.backref(
            "rate_norms",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    created_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "valid_to >= valid_from",
            name="ck_tariff_rate_norm_period",
        ),
        db.CheckConstraint(
            "weekly_norm_hours > 0",
            name="ck_tariff_rate_norm_hours",
        ),
        db.UniqueConstraint(
            "parameter_set_id",
            "position_code",
            "activity_kind",
            "valid_from",
            "valid_to",
            name="uq_tariff_rate_norm_scope_period",
        ),
        db.Index(
            "ix_tariff_rate_norm_resolution",
            "parameter_set_id",
            "position_code",
            "activity_kind",
            "valid_from",
            "valid_to",
        ),
    )


class TariffCoefficientType(db.Model):
    __tablename__ = "tariff_coefficient_type"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization_settings.id"),
        nullable=True,
        index=True,
    )
    code = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    calculation_kind = db.Column(db.String(30), nullable=False)
    applicable_scope = db.Column(db.String(40), nullable=False)
    is_configurable = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
    )
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
        index=True,
    )
    valid_from = db.Column(db.Date, nullable=True)
    valid_to = db.Column(db.Date, nullable=True)

    organization = db.relationship("OrganizationSettings")

    __table_args__ = (
        db.CheckConstraint(
            "calculation_kind IN "
            "('MULTIPLIER','PERCENT','GROUP_SIZE_RATIO')",
            name="ck_tariff_coefficient_type_calculation",
        ),
        db.CheckConstraint(
            "applicable_scope IN ('GROUP','ACTIVITY','EMPLOYEE','LINE')",
            name="ck_tariff_coefficient_type_scope",
        ),
        db.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_tariff_coefficient_type_period",
        ),
        db.Index(
            "uq_tariff_coefficient_type_global_code",
            "code",
            unique=True,
            postgresql_where=db.text("organization_id IS NULL"),
            sqlite_where=db.text("organization_id IS NULL"),
        ),
        db.Index(
            "uq_tariff_coefficient_type_local_code",
            "organization_id",
            "code",
            unique=True,
            postgresql_where=db.text("organization_id IS NOT NULL"),
            sqlite_where=db.text("organization_id IS NOT NULL"),
        ),
    )


class TariffCoefficientValue(db.Model):
    __tablename__ = "tariff_coefficient_value"

    id = db.Column(db.Integer, primary_key=True)
    parameter_set_id = db.Column(
        db.Integer,
        db.ForeignKey("calculation_parameter_set.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    coefficient_type_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_coefficient_type.id"),
        nullable=False,
        index=True,
    )
    value = db.Column(db.Numeric(12, 6), nullable=False)
    condition_kind = db.Column(
        db.String(40),
        nullable=False,
        default="ALWAYS",
        server_default="ALWAYS",
    )
    condition_data = db.Column(CALCULATION_JSON_TYPE, nullable=True)
    priority = db.Column(
        db.Integer,
        nullable=False,
        default=100,
        server_default="100",
    )
    minimum_value = db.Column(db.Numeric(12, 6), nullable=True)
    maximum_value = db.Column(db.Numeric(12, 6), nullable=True)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=False)
    source_text = db.Column(db.String(500), nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    parameter_set = db.relationship(
        "CalculationParameterSet",
        backref=db.backref(
            "coefficient_values",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    coefficient_type = db.relationship(
        "TariffCoefficientType",
        backref=db.backref("values", lazy=True),
    )
    created_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "value >= 0",
            name="ck_tariff_coefficient_value_nonnegative",
        ),
        db.CheckConstraint(
            "condition_kind IN ('ALWAYS','ACTIVITY','PLAN_KIND')",
            name="ck_tariff_coefficient_value_condition",
        ),
        db.CheckConstraint(
            "valid_to >= valid_from",
            name="ck_tariff_coefficient_value_period",
        ),
        db.CheckConstraint(
            "minimum_value IS NULL OR maximum_value IS NULL "
            "OR maximum_value >= minimum_value",
            name="ck_tariff_coefficient_value_limits",
        ),
        db.Index(
            "ix_tariff_coefficient_value_resolution",
            "parameter_set_id",
            "coefficient_type_id",
            "valid_from",
            "valid_to",
            "priority",
        ),
    )


class TariffAllowanceType(db.Model):
    __tablename__ = "tariff_allowance_type"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organization_settings.id"),
        nullable=True,
        index=True,
    )
    code = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    amount_kind = db.Column(db.String(30), nullable=False)
    scope_kind = db.Column(db.String(40), nullable=False)
    is_manual_allowed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.false(),
    )
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=db.true(),
        index=True,
    )
    valid_from = db.Column(db.Date, nullable=True)
    valid_to = db.Column(db.Date, nullable=True)

    organization = db.relationship("OrganizationSettings")

    __table_args__ = (
        db.CheckConstraint(
            "amount_kind IN ('FIXED','PERCENT')",
            name="ck_tariff_allowance_type_amount",
        ),
        db.CheckConstraint(
            "scope_kind IN ('EMPLOYEE','ASSIGNMENT','TARIFF_LINE')",
            name="ck_tariff_allowance_type_scope",
        ),
        db.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_tariff_allowance_type_period",
        ),
        db.Index(
            "uq_tariff_allowance_type_global_code",
            "code",
            unique=True,
            postgresql_where=db.text("organization_id IS NULL"),
            sqlite_where=db.text("organization_id IS NULL"),
        ),
        db.Index(
            "uq_tariff_allowance_type_local_code",
            "organization_id",
            "code",
            unique=True,
            postgresql_where=db.text("organization_id IS NOT NULL"),
            sqlite_where=db.text("organization_id IS NOT NULL"),
        ),
    )


class TariffAllowanceRule(db.Model):
    __tablename__ = "tariff_allowance_rule"

    id = db.Column(db.Integer, primary_key=True)
    parameter_set_id = db.Column(
        db.Integer,
        db.ForeignKey("calculation_parameter_set.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    allowance_type_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_allowance_type.id"),
        nullable=False,
        index=True,
    )
    fixed_amount = db.Column(db.Numeric(14, 2), nullable=True)
    percent_value = db.Column(db.Numeric(12, 6), nullable=True)
    base_kind = db.Column(
        db.String(40),
        nullable=False,
        default="BASE",
        server_default="BASE",
    )
    condition_data = db.Column(CALCULATION_JSON_TYPE, nullable=True)
    priority = db.Column(
        db.Integer,
        nullable=False,
        default=100,
        server_default="100",
    )
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date, nullable=False)
    source_text = db.Column(db.String(500), nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    parameter_set = db.relationship(
        "CalculationParameterSet",
        backref=db.backref(
            "allowance_rules",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    allowance_type = db.relationship(
        "TariffAllowanceType",
        backref=db.backref("rules", lazy=True),
    )
    created_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "base_kind IN ('BASE','SUBTOTAL')",
            name="ck_tariff_allowance_rule_base",
        ),
        db.CheckConstraint(
            "valid_to >= valid_from",
            name="ck_tariff_allowance_rule_period",
        ),
        db.CheckConstraint(
            "(fixed_amount IS NOT NULL AND fixed_amount >= 0) "
            "OR (percent_value IS NOT NULL AND percent_value >= 0)",
            name="ck_tariff_allowance_rule_value",
        ),
        db.Index(
            "ix_tariff_allowance_rule_resolution",
            "parameter_set_id",
            "allowance_type_id",
            "valid_from",
            "valid_to",
            "priority",
        ),
    )


class TariffCalculationRun(db.Model):
    __tablename__ = "tariff_calculation_run"

    id = db.Column(db.Integer, primary_key=True)
    tariff_version_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parameter_set_id = db.Column(
        db.Integer,
        db.ForeignKey("calculation_parameter_set.id"),
        nullable=False,
        index=True,
    )
    run_no = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.String(30),
        nullable=False,
        default="QUEUED",
        server_default="QUEUED",
        index=True,
    )
    started_at = db.Column(db.DateTime, nullable=True, index=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    input_revision = db.Column(db.Integer, nullable=False)
    algorithm_version = db.Column(db.String(80), nullable=False)
    input_hash = db.Column(db.String(128), nullable=False, index=True)
    summary_data = db.Column(CALCULATION_JSON_TYPE, nullable=True)
    error_text = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    tariff_version = db.relationship(
        "TariffVersion",
        backref=db.backref(
            "calculation_runs",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    parameter_set = db.relationship("CalculationParameterSet")
    created_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "status IN "
            "('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="ck_tariff_calculation_run_status",
        ),
        db.CheckConstraint(
            "run_no > 0 AND input_revision >= 0",
            name="ck_tariff_calculation_run_numbers",
        ),
        db.UniqueConstraint(
            "tariff_version_id",
            "run_no",
            name="uq_tariff_calculation_run_version_number",
        ),
        db.Index(
            "ix_tariff_calculation_run_version_status",
            "tariff_version_id",
            "status",
        ),
    )


class TariffLine(db.Model):
    __tablename__ = "tariff_line"

    id = db.Column(db.Integer, primary_key=True)
    calculation_run_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_calculation_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workload_assignment_id = db.Column(
        db.Integer,
        db.ForeignKey("workload_assignment.id"),
        nullable=False,
        index=True,
    )
    employee_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True,
    )
    position_code = db.Column(db.String(80), nullable=False)
    position_title = db.Column(db.String(180), nullable=False)
    education_activity_id = db.Column(
        db.Integer,
        db.ForeignKey("education_activity.id"),
        nullable=False,
        index=True,
    )
    teaching_group_id = db.Column(
        db.Integer,
        db.ForeignKey("teaching_group.id"),
        nullable=True,
        index=True,
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("department.id"),
        nullable=True,
        index=True,
    )
    building_id = db.Column(
        db.Integer,
        db.ForeignKey("buildings.id"),
        nullable=True,
        index=True,
    )
    date_from = db.Column(db.Date, nullable=False)
    date_to = db.Column(db.Date, nullable=False)
    weekly_hours = db.Column(db.Numeric(8, 3), nullable=False)
    annual_hours = db.Column(db.Numeric(10, 3), nullable=False)
    rate_norm_hours = db.Column(db.Numeric(8, 3), nullable=False)
    fte_value = db.Column(db.Numeric(10, 6), nullable=False)
    population_value = db.Column(db.Numeric(12, 3), nullable=False)
    student_hour_rate = db.Column(db.Numeric(14, 6), nullable=False)
    base_amount_raw = db.Column(db.Numeric(18, 6), nullable=False)
    base_amount = db.Column(db.Numeric(14, 2), nullable=False)
    total_amount_raw = db.Column(db.Numeric(18, 6), nullable=False)
    total_amount = db.Column(db.Numeric(14, 2), nullable=False)
    formula_snapshot = db.Column(CALCULATION_JSON_TYPE, nullable=False)
    line_hash = db.Column(db.String(128), nullable=False)

    calculation_run = db.relationship(
        "TariffCalculationRun",
        backref=db.backref(
            "lines",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )
    workload_assignment = db.relationship(
        "WorkloadAssignment",
        backref=db.backref("tariff_lines", lazy=True),
    )
    employee = db.relationship("User")
    education_activity = db.relationship("EducationActivity")
    teaching_group = db.relationship("TeachingGroup")
    department = db.relationship("Department")
    building = db.relationship("Building")

    __table_args__ = (
        db.CheckConstraint(
            "date_to >= date_from",
            name="ck_tariff_line_period",
        ),
        db.CheckConstraint(
            "weekly_hours >= 0 AND annual_hours >= 0 "
            "AND rate_norm_hours > 0 AND fte_value >= 0 "
            "AND population_value >= 0 AND student_hour_rate >= 0",
            name="ck_tariff_line_inputs",
        ),
        db.CheckConstraint(
            "base_amount >= 0 AND total_amount >= 0",
            name="ck_tariff_line_amounts",
        ),
        db.UniqueConstraint(
            "calculation_run_id",
            "workload_assignment_id",
            name="uq_tariff_line_run_assignment",
        ),
        db.Index(
            "ix_tariff_line_run_employee_department",
            "calculation_run_id",
            "employee_user_id",
            "department_id",
        ),
    )


class TariffLineComponent(db.Model):
    __tablename__ = "tariff_line_component"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    tariff_line_id = db.Column(
        db.Integer,
        db.ForeignKey("tariff_line.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    component_kind = db.Column(db.String(30), nullable=False, index=True)
    component_code = db.Column(db.String(80), nullable=False)
    component_name = db.Column(db.String(255), nullable=False)
    sequence_no = db.Column(db.Integer, nullable=False)
    numeric_value = db.Column(db.Numeric(18, 6), nullable=True)
    amount_raw = db.Column(db.Numeric(18, 6), nullable=True)
    amount_value = db.Column(db.Numeric(14, 2), nullable=True)
    calculation_expression = db.Column(db.Text, nullable=True)
    source_entity_type = db.Column(db.String(80), nullable=True)
    source_entity_id = db.Column(db.Integer, nullable=True)
    manual_reason = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    tariff_line = db.relationship(
        "TariffLine",
        backref=db.backref(
            "components",
            lazy=True,
            cascade="all, delete-orphan",
            order_by="TariffLineComponent.sequence_no",
        ),
    )
    created_by = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "component_kind IN "
            "('INPUT','COEFFICIENT','ALLOWANCE','MANUAL','TOTAL')",
            name="ck_tariff_line_component_kind",
        ),
        db.CheckConstraint(
            "sequence_no > 0",
            name="ck_tariff_line_component_sequence",
        ),
        db.CheckConstraint(
            "component_kind <> 'MANUAL' "
            "OR (manual_reason IS NOT NULL AND created_by_user_id IS NOT NULL)",
            name="ck_tariff_line_component_manual",
        ),
        db.UniqueConstraint(
            "tariff_line_id",
            "sequence_no",
            name="uq_tariff_line_component_sequence",
        ),
        db.Index(
            "ix_tariff_line_component_line_kind",
            "tariff_line_id",
            "component_kind",
        ),
    )


__all__ = [
    "ALLOWANCE_AMOUNT_KINDS",
    "ALLOWANCE_BASE_KINDS",
    "ALLOWANCE_SCOPES",
    "CALCULATION_RUN_STATUSES",
    "COEFFICIENT_CALCULATION_KINDS",
    "COEFFICIENT_CONDITION_KINDS",
    "COEFFICIENT_SCOPES",
    "CalculationParameterSet",
    "PARAMETER_SET_STATUSES",
    "ROUNDING_RULES",
    "TARIFF_COMPONENT_KINDS",
    "TariffAllowanceRule",
    "TariffAllowanceType",
    "TariffCalculationRun",
    "TariffCoefficientType",
    "TariffCoefficientValue",
    "TariffLine",
    "TariffLineComponent",
    "TariffRateNorm",
]
