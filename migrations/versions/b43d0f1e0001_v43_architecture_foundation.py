"""v43 architecture foundation

Revision ID: b43d0f1e0001
Revises: 859d6b9ccb7f
Create Date: 2026-03-10 13:05:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b43d0f1e0001'
down_revision = '859d6b9ccb7f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'child_movement',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('child_id', sa.Integer(), sa.ForeignKey('child.id'), nullable=False),
        sa.Column('academic_year_id', sa.Integer(), sa.ForeignKey('academic_year.id'), nullable=True),
        sa.Column('movement_type', sa.String(length=30), nullable=False),
        sa.Column('movement_date', sa.Date(), nullable=False),
        sa.Column('from_class_id', sa.Integer(), sa.ForeignKey('school_class.id'), nullable=True),
        sa.Column('to_class_id', sa.Integer(), sa.ForeignKey('school_class.id'), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('order_number', sa.String(length=100), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_child_movement_child_id', 'child_movement', ['child_id'])
    op.create_index('ix_child_movement_academic_year_id', 'child_movement', ['academic_year_id'])
    op.create_index('ix_child_movement_movement_type', 'child_movement', ['movement_type'])

    op.create_table(
        'support_case',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('child_id', sa.Integer(), sa.ForeignKey('child.id'), nullable=False),
        sa.Column('academic_year_id', sa.Integer(), sa.ForeignKey('academic_year.id'), nullable=True),
        sa.Column('support_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_support_case_child_id', 'support_case', ['child_id'])
    op.create_index('ix_support_case_academic_year_id', 'support_case', ['academic_year_id'])
    op.create_index('ix_support_case_support_type', 'support_case', ['support_type'])
    op.create_index('ix_support_case_status', 'support_case', ['status'])

    op.create_table(
        'system_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('object_type', sa.String(length=100), nullable=True),
        sa.Column('object_id', sa.String(length=100), nullable=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_system_log_user_id', 'system_log', ['user_id'])
    op.create_index('ix_system_log_action', 'system_log', ['action'])
    op.create_index('ix_system_log_object_type', 'system_log', ['object_type'])
    op.create_index('ix_system_log_object_id', 'system_log', ['object_id'])
    op.create_index('ix_system_log_created_at', 'system_log', ['created_at'])


def downgrade():
    op.drop_index('ix_system_log_created_at', table_name='system_log')
    op.drop_index('ix_system_log_object_id', table_name='system_log')
    op.drop_index('ix_system_log_object_type', table_name='system_log')
    op.drop_index('ix_system_log_action', table_name='system_log')
    op.drop_index('ix_system_log_user_id', table_name='system_log')
    op.drop_table('system_log')

    op.drop_index('ix_support_case_status', table_name='support_case')
    op.drop_index('ix_support_case_support_type', table_name='support_case')
    op.drop_index('ix_support_case_academic_year_id', table_name='support_case')
    op.drop_index('ix_support_case_child_id', table_name='support_case')
    op.drop_table('support_case')

    op.drop_index('ix_child_movement_movement_type', table_name='child_movement')
    op.drop_index('ix_child_movement_academic_year_id', table_name='child_movement')
    op.drop_index('ix_child_movement_child_id', table_name='child_movement')
    op.drop_table('child_movement')
