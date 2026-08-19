"""add cascade delete for batches

Revision ID: bfcd75307fac
Revises: d486ce2e47a2
Create Date: 2026-01-08 19:58:41.538117

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bfcd75307fac'
down_revision = 'd486ce2e47a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Добавляем order_id в batches ВРЕМЕННО nullable
    with op.batch_alter_table("batches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "order_id",
                sa.Integer(),
                nullable=True,
            )
        )

    # 2. Переносим связь orders.batch_id -> batches.order_id
    op.execute(
        """
        UPDATE batches
        SET order_id = orders.id
        FROM orders
        WHERE orders.batch_id = batches.id
        """
    )

    # 3. Делаем order_id NOT NULL + FK + UNIQUE + CASCADE
    with op.batch_alter_table("batches") as batch_op:
        batch_op.alter_column("order_id", nullable=False)
        batch_op.create_foreign_key(
            "batches_order_id_fkey",
            "orders",
            ["order_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_batches_order_id",
            ["order_id"],
        )

    # 4. Удаляем batch_id из orders
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint(
            "orders_batch_id_fkey",
            type_="foreignkey"
        )
        batch_op.drop_column("batch_id")

    # 5. Удаляем batch_id из boxes
    with op.batch_alter_table("boxes") as batch_op:
        batch_op.drop_constraint(
            "boxes_batch_id_fkey",
            type_="foreignkey"
        )
        batch_op.drop_column("batch_id")


def downgrade() -> None:
    # 1. Возвращаем batch_id в boxes
    with op.batch_alter_table("boxes") as batch_op:
        batch_op.add_column(
            sa.Column("batch_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "boxes_batch_id_fkey",
            "batches",
            ["batch_id"],
            ["id"],
        )

    # 2. Удаляем order_id из batches
    with op.batch_alter_table("batches") as batch_op:
        batch_op.drop_constraint(
            "batches_order_id_fkey",
            type_="foreignkey"
        )
        batch_op.drop_column("order_id")

    # 3. Возвращаем batch_id в orders
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(
            sa.Column("batch_id", sa.Integer(), nullable=False)
        )
        batch_op.create_foreign_key(
            "orders_batch_id_fkey",
            "batches",
            ["batch_id"],
            ["id"],
        )
