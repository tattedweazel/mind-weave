"""Add transcription_jobs table, audio_file_artifacts.transient flag, transcribe_file palette key.

Revision ID: s2t3u4v5w6x7
Revises: r1s2t3u4v5w6
Create Date: 2026-05-07

Summary:
  - transcription_jobs: persisted lifecycle of provider-abstracted transcribe_file requests.
  - audio_file_artifacts.transient: flag rows spilled by runtime uploads so the lifespan
    poller / cleanup hooks can purge them after their owning transcription_job finishes.
  - Add transcribe_file to palettes.colors JSON for existing palettes.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "s2t3u4v5w6x7"
down_revision: Union[str, Sequence[str], None] = "r1s2t3u4v5w6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLORS = {"transcribe_file": "#16a34a"}


def upgrade() -> None:
    # 1) audio_file_artifacts.transient
    with op.batch_alter_table("audio_file_artifacts") as batch:
        batch.add_column(
            sa.Column(
                "transient",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    op.create_index(
        op.f("ix_audio_file_artifacts_transient"),
        "audio_file_artifacts",
        ["transient"],
        unique=False,
    )

    # 2) transcription_jobs
    op.create_table(
        "transcription_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("node_id", sa.String(length=255), nullable=True),
        sa.Column("for_loop_id", sa.String(length=255), nullable=True),
        sa.Column("for_loop_iteration", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_job_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("audio_artifact_id", sa.UUID(), nullable=True),
        sa.Column("audio_filename", sa.String(length=512), nullable=False),
        sa.Column("audio_mime_type", sa.String(length=128), nullable=False),
        sa.Column("audio_size_bytes", sa.Integer(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("transcript_json", sa.JSON(), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=False),
        sa.Column("provider_error", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.ForeignKeyConstraint(["audio_artifact_id"], ["audio_file_artifacts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transcription_jobs_user_id"), "transcription_jobs", ["user_id"], unique=False)
    op.create_index(op.f("ix_transcription_jobs_run_id"), "transcription_jobs", ["run_id"], unique=False)
    op.create_index(op.f("ix_transcription_jobs_node_id"), "transcription_jobs", ["node_id"], unique=False)
    op.create_index(op.f("ix_transcription_jobs_provider"), "transcription_jobs", ["provider"], unique=False)
    op.create_index(
        op.f("ix_transcription_jobs_provider_job_id"),
        "transcription_jobs",
        ["provider_job_id"],
        unique=False,
    )
    op.create_index(op.f("ix_transcription_jobs_status"), "transcription_jobs", ["status"], unique=False)
    op.create_index(
        op.f("ix_transcription_jobs_audio_artifact_id"),
        "transcription_jobs",
        ["audio_artifact_id"],
        unique=False,
    )
    op.create_index(op.f("ix_transcription_jobs_created_at"), "transcription_jobs", ["created_at"], unique=False)

    # 3) Seed the new palette color into existing rows.
    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, colors FROM palettes")).fetchall()
    for (palette_id, colors_json) in rows:
        if colors_json is None:
            continue
        colors = json.loads(colors_json) if isinstance(colors_json, str) else dict(colors_json)
        updated = False
        for key, value in NEW_COLORS.items():
            if key not in colors:
                colors[key] = value
                updated = True
        if updated:
            conn.execute(
                text("UPDATE palettes SET colors = :colors WHERE id = :id"),
                {"colors": json.dumps(colors), "id": str(palette_id)},
            )


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, colors FROM palettes")).fetchall()
    for (palette_id, colors_json) in rows:
        if colors_json is None:
            continue
        colors = json.loads(colors_json) if isinstance(colors_json, str) else dict(colors_json)
        updated = False
        for key in NEW_COLORS:
            if key in colors:
                del colors[key]
                updated = True
        if updated:
            conn.execute(
                text("UPDATE palettes SET colors = :colors WHERE id = :id"),
                {"colors": json.dumps(colors), "id": str(palette_id)},
            )

    op.drop_index(op.f("ix_transcription_jobs_created_at"), table_name="transcription_jobs")
    op.drop_index(op.f("ix_transcription_jobs_audio_artifact_id"), table_name="transcription_jobs")
    op.drop_index(op.f("ix_transcription_jobs_status"), table_name="transcription_jobs")
    op.drop_index(op.f("ix_transcription_jobs_provider_job_id"), table_name="transcription_jobs")
    op.drop_index(op.f("ix_transcription_jobs_provider"), table_name="transcription_jobs")
    op.drop_index(op.f("ix_transcription_jobs_node_id"), table_name="transcription_jobs")
    op.drop_index(op.f("ix_transcription_jobs_run_id"), table_name="transcription_jobs")
    op.drop_index(op.f("ix_transcription_jobs_user_id"), table_name="transcription_jobs")
    op.drop_table("transcription_jobs")

    op.drop_index(op.f("ix_audio_file_artifacts_transient"), table_name="audio_file_artifacts")
    with op.batch_alter_table("audio_file_artifacts") as batch:
        batch.drop_column("transient")
