from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text  # Импортируйте текстовый метод

def upgrade():
    # Получим подключение
    conn = op.get_bind()
    result = conn.execute(text("PRAGMA table_info(clients);"))  # Используйте text
    # Проверяем существование столбца
    if 'selected_service_category' not in [col['name'] for col in result]:
        with op.batch_alter_table('clients', schema=None) as batch_op:
            batch_op.add_column(sa.Column('selected_service_category', sa.Integer(), nullable=True))

def downgrade():
    with op.batch_alter_table('clients', schema=None) as batch_op:
        batch_op.drop_column('selected_service_category')