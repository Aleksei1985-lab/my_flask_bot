"""Add reminder_sent to appointments

Revision ID: b5eda678baf5
Revises: c0e2475baa01
Create Date: 2025-02-25 02:18:13.757823
"""
from alembic import op
import sqlalchemy as sa

revision = 'b5eda678baf5'
down_revision = 'c0e2475baa01'
branch_labels = None
depends_on = None

def upgrade():
    # Шаг 1: Добавляем колонку как nullable=True с default=False
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reminder_sent', sa.Boolean(), nullable=True, default=False))

    # Шаг 2: Устанавливаем значение False для всех существующих записей
    op.execute("UPDATE appointments SET reminder_sent = FALSE WHERE reminder_sent IS NULL")

    # Шаг 3: Изменяем колонку на NOT NULL
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.alter_column('reminder_sent', nullable=False)

def downgrade():
    # Удаляем колонку при откате
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.drop_column('reminder_sent')