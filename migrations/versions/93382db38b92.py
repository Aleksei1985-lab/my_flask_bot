"""Added selected_service_category to Client

Revision ID: 93382db38b92
Revises: <предыдущий_идентификатор_ревизии>  # Укажите идентификатор предыдущей ревизии, если есть
Create Date: 2025-02-12 16:00:41.315141

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '93382db38b92'
down_revision = None  # или предыдущая версия, если такая есть
branch_labels = None
depends_on = None

def upgrade():
    # Примените ваши изменения здесь
    op.create_table(
        'example_table',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(length=50)),
    )

def downgrade():
    # Откатите изменения здесь
    op.drop_table('example_table')