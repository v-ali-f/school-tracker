"""education activity catalog

Revision ID: 2b6d8f3a91c4
Revises: f9487aa87d4f
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "2b6d8f3a91c4"
down_revision = "f9487aa87d4f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "education_activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_name", sa.String(length=120), nullable=True),
        sa.Column("activity_kind", sa.String(length=40), nullable=False),
        sa.Column("education_level", sa.String(length=20), nullable=True),
        sa.Column("is_global", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_tariffable", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "activity_kind IN ("
            "'SUBJECT','COURSE','MODULE','EXTRACURRICULAR_COURSE',"
            "'ADDITIONAL_PROGRAM','CLUB_OR_SECTION','OLYMPIAD_DIRECTION'"
            ")",
            name="ck_education_activity_kind",
        ),
        sa.CheckConstraint(
            "(is_global AND organization_id IS NULL) OR "
            "(NOT is_global AND organization_id IS NOT NULL)",
            name="ck_education_activity_organization_scope",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_education_activity_valid_period",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user.id"],
            name="fk_education_activity_created_by_user_id_user",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization_settings.id"],
            name="fk_education_activity_organization_id_organization_settings",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["user.id"],
            name="fk_education_activity_updated_by_user_id_user",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_education_activity"),
    )
    op.create_index(
        "ix_education_activity_activity_kind",
        "education_activity",
        ["activity_kind"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_catalog",
        "education_activity",
        ["organization_id", "activity_kind", "is_active"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_education_level",
        "education_activity",
        ["education_level"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_is_active",
        "education_activity",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_organization_id",
        "education_activity",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_education_activity_global_code",
        "education_activity",
        ["code"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    op.create_index(
        "uq_education_activity_local_code",
        "education_activity",
        ["organization_id", "code"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )

    op.add_column(
        "subject",
        sa.Column("education_activity_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_subject_education_activity_id_education_activity",
        "subject",
        "education_activity",
        ["education_activity_id"],
        ["id"],
    )
    op.create_index(
        "ix_subject_education_activity_id",
        "subject",
        ["education_activity_id"],
        unique=True,
    )

    op.create_table(
        "education_activity_alias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("education_activity_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("alias", sa.String(length=300), nullable=False),
        sa.Column("normalized_alias", sa.String(length=300), nullable=False),
        sa.Column(
            "source_module",
            sa.String(length=50),
            server_default="GENERAL",
            nullable=False,
        ),
        sa.Column(
            "source_system",
            sa.String(length=100),
            server_default="",
            nullable=False,
        ),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "match_priority",
            sa.SmallInteger(),
            server_default="100",
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_education_activity_alias_valid_period",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["user.id"],
            name="fk_education_activity_alias_confirmed_by_user_id_user",
        ),
        sa.ForeignKeyConstraint(
            ["education_activity_id"],
            ["education_activity.id"],
            name="fk_education_activity_alias_activity",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization_settings.id"],
            name="fk_education_activity_alias_organization",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_education_activity_alias"),
    )
    op.create_index(
        "ix_education_activity_alias_education_activity_id",
        "education_activity_alias",
        ["education_activity_id"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_alias_is_active",
        "education_activity_alias",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_alias_normalized_alias",
        "education_activity_alias",
        ["normalized_alias"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_alias_organization_id",
        "education_activity_alias",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_alias_source_module",
        "education_activity_alias",
        ["source_module"],
        unique=False,
    )
    op.create_index(
        "uq_education_activity_alias_global",
        "education_activity_alias",
        ["normalized_alias", "source_module", "source_system"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    op.create_index(
        "uq_education_activity_alias_local",
        "education_activity_alias",
        ["organization_id", "normalized_alias", "source_module", "source_system"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )

    op.create_table(
        "education_activity_department",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("education_activity_id", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_education_activity_department_valid_period",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
            name="fk_education_activity_department_department",
        ),
        sa.ForeignKeyConstraint(
            ["education_activity_id"],
            ["education_activity.id"],
            name="fk_education_activity_department_activity",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_education_activity_department"),
        sa.UniqueConstraint(
            "education_activity_id",
            "department_id",
            "valid_from",
            name="uq_education_activity_department_period",
        ),
    )
    op.create_index(
        "ix_education_activity_department_department_id",
        "education_activity_department",
        ["department_id"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_department_education_activity_id",
        "education_activity_department",
        ["education_activity_id"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_department_is_active",
        "education_activity_department",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_education_activity_department_period",
        "education_activity_department",
        ["department_id", "valid_from", "valid_to"],
        unique=False,
    )
    op.create_index(
        "uq_education_activity_department_default_period",
        "education_activity_department",
        ["education_activity_id", "department_id"],
        unique=True,
        postgresql_where=sa.text("valid_from IS NULL"),
    )
    op.create_index(
        "uq_education_activity_department_current_primary",
        "education_activity_department",
        ["education_activity_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_primary AND is_active AND valid_to IS NULL"
        ),
    )

    op.create_table(
        "external_activity_mapping_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("academic_year_id", sa.Integer(), nullable=True),
        sa.Column("source_module", sa.String(length=50), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=True),
        sa.Column("source_value", sa.String(length=500), nullable=False),
        sa.Column("normalized_value", sa.String(length=500), nullable=False),
        sa.Column("education_activity_id", sa.Integer(), nullable=True),
        sa.Column("education_plan_item_id", sa.Integer(), nullable=True),
        sa.Column("mapping_method", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("import_batch_type", sa.String(length=50), nullable=True),
        sa.Column("import_batch_id", sa.BigInteger(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_external_activity_mapping_confidence",
        ),
        sa.CheckConstraint(
            "mapping_method IN ("
            "'CODE','CANONICAL_NAME','ALIAS','MANUAL','AMBIGUOUS','UNMATCHED'"
            ")",
            name="ck_external_activity_mapping_method",
        ),
        sa.ForeignKeyConstraint(
            ["academic_year_id"],
            ["academic_year.id"],
            name="fk_external_activity_mapping_academic_year",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["user.id"],
            name="fk_external_activity_mapping_confirmed_by_user",
        ),
        sa.ForeignKeyConstraint(
            ["education_activity_id"],
            ["education_activity.id"],
            name="fk_external_activity_mapping_activity",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization_settings.id"],
            name="fk_external_activity_mapping_organization",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_external_activity_mapping_log"),
    )
    op.create_index(
        "ix_external_activity_mapping_log_academic_year_id",
        "external_activity_mapping_log",
        ["academic_year_id"],
        unique=False,
    )
    op.create_index(
        "ix_external_activity_mapping_log_created_at",
        "external_activity_mapping_log",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_external_activity_mapping_log_education_activity_id",
        "external_activity_mapping_log",
        ["education_activity_id"],
        unique=False,
    )
    op.create_index(
        "ix_external_activity_mapping_log_education_plan_item_id",
        "external_activity_mapping_log",
        ["education_plan_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_external_activity_mapping_log_mapping_method",
        "external_activity_mapping_log",
        ["mapping_method"],
        unique=False,
    )
    op.create_index(
        "ix_external_activity_mapping_log_normalized_value",
        "external_activity_mapping_log",
        ["normalized_value"],
        unique=False,
    )
    op.create_index(
        "ix_external_activity_mapping_log_organization_id",
        "external_activity_mapping_log",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_external_activity_mapping_log_source_module",
        "external_activity_mapping_log",
        ["source_module"],
        unique=False,
    )
    op.create_index(
        "ix_external_activity_mapping_source",
        "external_activity_mapping_log",
        ["source_module", "source_system", "normalized_value"],
        unique=False,
    )

    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO education_activity (
            code,
            name,
            short_name,
            activity_kind,
            is_global,
            is_tariffable,
            is_active,
            created_at,
            updated_at
        )
        SELECT
            'LEGACY_SUBJECT_' || s.id,
            s.name,
            s.short_name,
            'SUBJECT',
            TRUE,
            TRUE,
            TRUE,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM subject s
        WHERE s.education_activity_id IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM education_activity ea
              WHERE ea.code = 'LEGACY_SUBJECT_' || s.id
                AND ea.organization_id IS NULL
          )
    """))
    connection.execute(sa.text("""
        UPDATE subject s
        SET education_activity_id = ea.id
        FROM education_activity ea
        WHERE s.education_activity_id IS NULL
          AND ea.code = 'LEGACY_SUBJECT_' || s.id
          AND ea.organization_id IS NULL
    """))
    connection.execute(sa.text("""
        INSERT INTO education_activity_alias (
            education_activity_id,
            alias,
            normalized_alias,
            source_module,
            source_system,
            match_priority,
            is_active,
            created_at,
            updated_at
        )
        SELECT DISTINCT ON (
            trim(regexp_replace(
                lower(replace(m.olympiad_subject_name, 'ё', 'е')),
                '[^0-9a-zа-я]+',
                ' ',
                'g'
            ))
        )
            s.education_activity_id,
            m.olympiad_subject_name,
            trim(regexp_replace(
                lower(replace(m.olympiad_subject_name, 'ё', 'е')),
                '[^0-9a-zа-я]+',
                ' ',
                'g'
            )),
            'OLYMPIAD',
            'LEGACY_OLYMPIAD_MAPPING',
            m.priority,
            m.is_active,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM olympiad_subject_mapping m
        JOIN subject s ON s.id = m.subject_id
        WHERE s.education_activity_id IS NOT NULL
          AND trim(coalesce(m.olympiad_subject_name, '')) <> ''
        ORDER BY
            trim(regexp_replace(
                lower(replace(m.olympiad_subject_name, 'ё', 'е')),
                '[^0-9a-zа-я]+',
                ' ',
                'g'
            )),
            m.priority ASC,
            m.id ASC
        ON CONFLICT DO NOTHING
    """))
    connection.execute(sa.text("""
        INSERT INTO education_activity_department (
            education_activity_id,
            department_id,
            is_primary,
            is_active,
            created_at,
            updated_at
        )
        SELECT
            mapped.education_activity_id,
            mapped.department_id,
            mapped.row_num = 1,
            TRUE,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM (
            SELECT
                s.education_activity_id,
                ds.department_id,
                row_number() OVER (
                    PARTITION BY s.education_activity_id
                    ORDER BY ds.id
                ) AS row_num
            FROM department_subject ds
            JOIN subject s ON s.id = ds.subject_id
            WHERE s.education_activity_id IS NOT NULL
        ) mapped
        ON CONFLICT DO NOTHING
    """))


def downgrade():
    op.drop_index(
        "ix_external_activity_mapping_source",
        table_name="external_activity_mapping_log",
    )
    op.drop_index(
        "ix_external_activity_mapping_log_source_module",
        table_name="external_activity_mapping_log",
    )
    op.drop_index(
        "ix_external_activity_mapping_log_organization_id",
        table_name="external_activity_mapping_log",
    )
    op.drop_index(
        "ix_external_activity_mapping_log_normalized_value",
        table_name="external_activity_mapping_log",
    )
    op.drop_index(
        "ix_external_activity_mapping_log_mapping_method",
        table_name="external_activity_mapping_log",
    )
    op.drop_index(
        "ix_external_activity_mapping_log_education_plan_item_id",
        table_name="external_activity_mapping_log",
    )
    op.drop_index(
        "ix_external_activity_mapping_log_education_activity_id",
        table_name="external_activity_mapping_log",
    )
    op.drop_index(
        "ix_external_activity_mapping_log_created_at",
        table_name="external_activity_mapping_log",
    )
    op.drop_index(
        "ix_external_activity_mapping_log_academic_year_id",
        table_name="external_activity_mapping_log",
    )
    op.drop_table("external_activity_mapping_log")

    op.drop_index(
        "ix_education_activity_department_period",
        table_name="education_activity_department",
    )
    op.drop_index(
        "ix_education_activity_department_is_active",
        table_name="education_activity_department",
    )
    op.drop_index(
        "ix_education_activity_department_education_activity_id",
        table_name="education_activity_department",
    )
    op.drop_index(
        "ix_education_activity_department_department_id",
        table_name="education_activity_department",
    )
    op.drop_table("education_activity_department")

    op.drop_index(
        "uq_education_activity_alias_local",
        table_name="education_activity_alias",
    )
    op.drop_index(
        "uq_education_activity_alias_global",
        table_name="education_activity_alias",
    )
    op.drop_index(
        "ix_education_activity_alias_source_module",
        table_name="education_activity_alias",
    )
    op.drop_index(
        "ix_education_activity_alias_organization_id",
        table_name="education_activity_alias",
    )
    op.drop_index(
        "ix_education_activity_alias_normalized_alias",
        table_name="education_activity_alias",
    )
    op.drop_index(
        "ix_education_activity_alias_is_active",
        table_name="education_activity_alias",
    )
    op.drop_index(
        "ix_education_activity_alias_education_activity_id",
        table_name="education_activity_alias",
    )
    op.drop_table("education_activity_alias")

    op.drop_index("ix_subject_education_activity_id", table_name="subject")
    op.drop_constraint(
        "fk_subject_education_activity_id_education_activity",
        "subject",
        type_="foreignkey",
    )
    op.drop_column("subject", "education_activity_id")

    op.drop_index(
        "uq_education_activity_local_code",
        table_name="education_activity",
    )
    op.drop_index(
        "uq_education_activity_global_code",
        table_name="education_activity",
    )
    op.drop_index("ix_education_activity_organization_id", table_name="education_activity")
    op.drop_index("ix_education_activity_is_active", table_name="education_activity")
    op.drop_index("ix_education_activity_education_level", table_name="education_activity")
    op.drop_index("ix_education_activity_catalog", table_name="education_activity")
    op.drop_index("ix_education_activity_activity_kind", table_name="education_activity")
    op.drop_table("education_activity")
