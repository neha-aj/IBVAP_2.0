"""add thermal fusion + edge deployment fields (M11)

Widens `ck_cameras_type` to accept 'thermal' and 'dual' -- existing rows
are already valid members of the new, larger set, so this is a
non-destructive ALTER. Adds `thermal_source_url` (the thermal half of a
`dual` camera pair) and `deployment_mode` (which detection profile owns
this camera -- 'central' default, unchanged Phase 1/2 behavior, or 'edge').

Note: numbered 0005, not 0004 as the M11 design doc's own §10 checklist
names it -- 0004 is already taken by `0004_add_requires_ppe.py` (Phase 2
M21, landed after this doc's last verification pass). Same content, just
the correct next revision in the actual chain.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_cameras_type", "cameras", schema="camera", type_="check")
    op.create_check_constraint(
        "ck_cameras_type",
        "cameras",
        "type in ('rtsp','usb','ip','file','webcam','thermal','dual')",
        schema="camera",
    )
    op.add_column("cameras", sa.Column("thermal_source_url", sa.String(), nullable=True), schema="camera")
    op.add_column(
        "cameras",
        sa.Column("deployment_mode", sa.String(), nullable=False, server_default="central"),
        schema="camera",
    )


def downgrade() -> None:
    op.drop_column("cameras", "deployment_mode", schema="camera")
    op.drop_column("cameras", "thermal_source_url", schema="camera")
    op.drop_constraint("ck_cameras_type", "cameras", schema="camera", type_="check")
    op.create_check_constraint(
        "ck_cameras_type",
        "cameras",
        "type in ('rtsp','usb','ip','file','webcam')",
        schema="camera",
    )
