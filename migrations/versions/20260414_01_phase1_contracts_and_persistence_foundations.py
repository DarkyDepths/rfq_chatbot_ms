"""Create Phase 1 chatbot session and conversation tables.

The Phase 1/2 persistence model stays normalized intentionally: ``user_id`` and
``rfq_id`` live on ``chatbot_sessions`` and are reached from messages through
``conversation_id -> chatbot_conversations.session_id``. The implementation
plan's Phase 1 table map defines thin conversation/message tables, so
denormalized copies are deferred until a proven query need exists.

Revision ID: 20260414_01
Revises:
Create Date: 2026-04-14 15:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260414_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


session_mode_enum = sa.Enum(
    "rfq_bound",
    "portfolio",
    "pending_pivot",
    name="session_mode",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "chatbot_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("rfq_id", sa.String(length=255), nullable=True),
        sa.Column("mode", session_mode_enum, nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chatbot_sessions_mode"), "chatbot_sessions", ["mode"], unique=False)
    op.create_index(op.f("ix_chatbot_sessions_rfq_id"), "chatbot_sessions", ["rfq_id"], unique=False)
    op.create_index(op.f("ix_chatbot_sessions_user_id"), "chatbot_sessions", ["user_id"], unique=False)

    op.create_table(
        "chatbot_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chatbot_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chatbot_conversations_session_id"),
        "chatbot_conversations",
        ["session_id"],
        unique=False,
    )

    op.create_table(
        "chatbot_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["chatbot_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "turn_number",
            name="uq_chatbot_messages_conversation_turn_number",
        ),
    )
    op.create_index(
        op.f("ix_chatbot_messages_conversation_id"),
        "chatbot_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_chatbot_messages_timestamp"),
        "chatbot_messages",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_chatbot_messages_timestamp"), table_name="chatbot_messages")
    op.drop_index(op.f("ix_chatbot_messages_conversation_id"), table_name="chatbot_messages")
    op.drop_table("chatbot_messages")

    op.drop_index(op.f("ix_chatbot_conversations_session_id"), table_name="chatbot_conversations")
    op.drop_table("chatbot_conversations")

    op.drop_index(op.f("ix_chatbot_sessions_user_id"), table_name="chatbot_sessions")
    op.drop_index(op.f("ix_chatbot_sessions_rfq_id"), table_name="chatbot_sessions")
    op.drop_index(op.f("ix_chatbot_sessions_mode"), table_name="chatbot_sessions")
    op.drop_table("chatbot_sessions")
