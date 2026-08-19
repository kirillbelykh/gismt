"""add cascade delete for order relations

Revision ID: ec7ffc0feef7
Revises: 5c7b93541fb9
Create Date: 2026-01-08 18:20:18.276705

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ec7ffc0feef7'
down_revision = '5c7b93541fb9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # boxes.order_id -> orders.id ON DELETE CASCADE
    op.drop_constraint(
        "boxes_order_id_fkey",
        "boxes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "boxes_order_id_fkey",
        source_table="boxes",
        referent_table="orders",
        local_cols=["order_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # marking_codes.order_id -> orders.id ON DELETE CASCADE
    op.drop_constraint(
        "marking_codes_order_id_fkey",
        "marking_codes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "marking_codes_order_id_fkey",
        source_table="marking_codes",
        referent_table="orders",
        local_cols=["order_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # rollback marking_codes FK (без CASCADE)
    op.drop_constraint(
        "marking_codes_order_id_fkey",
        "marking_codes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "marking_codes_order_id_fkey",
        source_table="marking_codes",
        referent_table="orders",
        local_cols=["order_id"],
        remote_cols=["id"],
    )

    # rollback boxes FK (без CASCADE)
    op.drop_constraint(
        "boxes_order_id_fkey",
        "boxes",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "boxes_order_id_fkey",
        source_table="boxes",
        referent_table="orders",
        local_cols=["order_id"],
        remote_cols=["id"],
    )
