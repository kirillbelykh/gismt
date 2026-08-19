"""add cascade delete for box_items

Revision ID: d486ce2e47a2
Revises: ec7ffc0feef7
Create Date: 2026-01-08 18:24:49.139073

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd486ce2e47a2'
down_revision = 'ec7ffc0feef7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "box_items_box_id_fkey",
        "box_items",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "box_items_box_id_fkey",
        source_table="box_items",
        referent_table="boxes",
        local_cols=["box_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "box_items_box_id_fkey",
        "box_items",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "box_items_box_id_fkey",
        source_table="box_items",
        referent_table="boxes",
        local_cols=["box_id"],
        remote_cols=["id"],
    )
