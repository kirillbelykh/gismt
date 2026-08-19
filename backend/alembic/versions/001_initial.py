"""Initial migration

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # Products
    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('gtin', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('package_capacity', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_products_id'), 'products', ['id'], unique=False)
    op.create_index(op.f('ix_products_gtin'), 'products', ['gtin'], unique=True)

    # Batches
    op.create_table(
        'batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_number', sa.String(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('prod_date', sa.Date(), nullable=False),
        sa.Column('exp_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_batches_id'), 'batches', ['id'], unique=False)
    op.create_index(op.f('ix_batches_batch_number'), 'batches', ['batch_number'], unique=False)

    # Orders
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('external_order_id', sa.String(), nullable=True),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('batch_number', sa.String(), nullable=False),
        sa.Column('prod_date', sa.Date(), nullable=False),
        sa.Column('exp_date', sa.Date(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('ORDERING', 'READY', 'ERROR', name='orderstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_id'), 'orders', ['id'], unique=False)
    op.create_index(op.f('ix_orders_external_order_id'), 'orders', ['external_order_id'], unique=True)

    # Marking codes
    op.create_table(
        'marking_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code_raw', sa.String(), nullable=False),
        sa.Column('sntin', sa.String(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('PRINTED', 'UNUSED', 'RESERVED', 'APPLIED', 'IN_CIRCULATION', 'ERROR', 'AGGREGATED', name='markingcodestatus'), nullable=False),
        sa.Column('printed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_marking_codes_id'), 'marking_codes', ['id'], unique=False)
    op.create_index('idx_marking_codes_code_raw', 'marking_codes', ['code_raw'], unique=False)
    op.create_index('idx_marking_codes_sntin', 'marking_codes', ['sntin'], unique=False)

    # Boxes
    op.create_table(
        'boxes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sscc', sa.String(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=True),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('SCANNED', 'RESERVED', 'APPLY_SENT', 'AGGREGATED', 'TURNOVER_DONE', 'ERROR', name='boxstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_boxes_id'), 'boxes', ['id'], unique=False)
    op.create_index(op.f('ix_boxes_sscc'), 'boxes', ['sscc'], unique=True)

    # Box items
    op.create_table(
        'box_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('box_id', sa.Integer(), nullable=False),
        sa.Column('marking_code_id', sa.Integer(), nullable=False),
        sa.Column('scanned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['box_id'], ['boxes.id'], ),
        sa.ForeignKeyConstraint(['marking_code_id'], ['marking_codes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_box_items_id'), 'box_items', ['id'], unique=False)

    # SSCC counters
    op.create_table(
        'sscc_counters',
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('last_serial_int', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('date'),
        sa.UniqueConstraint('date', name='uq_sscc_counters_date')
    )

    # Task log
    op.create_table(
        'task_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_type', sa.String(), nullable=False),
        sa.Column('related_id', sa.Integer(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', name='taskstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_task_log_id'), 'task_log', ['id'], unique=False)
    op.create_index(op.f('ix_task_log_task_type'), 'task_log', ['task_type'], unique=False)
    op.create_index(op.f('ix_task_log_related_id'), 'task_log', ['related_id'], unique=False)
    op.create_index('idx_task_log_idempotency', 'task_log', ['task_type', 'related_id'], unique=False)


def downgrade() -> None:
    # Удаляем таблицы если они существуют
    op.execute("DROP TABLE IF EXISTS task_log CASCADE")
    op.execute("DROP TABLE IF EXISTS sscc_counters CASCADE")
    op.execute("DROP TABLE IF EXISTS box_items CASCADE")
    op.execute("DROP TABLE IF EXISTS boxes CASCADE")
    op.execute("DROP TABLE IF EXISTS marking_codes CASCADE")
    op.execute("DROP TABLE IF EXISTS orders CASCADE")
    op.execute("DROP TABLE IF EXISTS batches CASCADE")
    op.execute("DROP TABLE IF EXISTS products CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")

    # Удаляем типы если они существуют
    op.execute("DROP TYPE IF EXISTS taskstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS boxstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS markingcodestatus CASCADE")
    op.execute("DROP TYPE IF EXISTS orderstatus CASCADE")