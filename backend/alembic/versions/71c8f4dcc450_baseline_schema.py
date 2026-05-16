"""baseline schema

Revision ID: 71c8f4dcc450
Revises: 
Create Date: 2026-04-27 18:53:44.299432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


# revision identifiers, used by Alembic.
revision: str = '71c8f4dcc450'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _idx(name: str, table: str, col: str, unique: bool = False) -> None:
    """Create index with IF NOT EXISTS for cross-dialect safety."""
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({col})"
    )


_TABLES_DEFS: list[tuple[str, str, list]] = [
    ('bot_config', 'bot_config', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('business_name', sa.String(), nullable=True),
        sa.Column('agent_name', sa.String(), nullable=True),
        sa.Column('brand_color', sa.String(), nullable=True),
        sa.Column('welcome_message', sa.String(), nullable=True),
        sa.Column('escalation_email', sa.String(), nullable=True),
        sa.Column('voice_enabled', sa.Boolean(), nullable=True),
        sa.Column('greeting_message', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('conversations', 'conversations', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('escalated', sa.Boolean(), nullable=True),
        sa.Column('customer_email', sa.String(), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=True),
        sa.Column('primary_language', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('error_logs', 'error_logs', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('error_type', sa.String(), nullable=False),
        sa.Column('error_message', sa.String(), nullable=False),
        sa.Column('traceback', sa.Text(), nullable=True),
        sa.Column('endpoint', sa.String(), nullable=True),
        sa.Column('request_data', sa.Text(), nullable=True),
        sa.Column('auto_healed', sa.Boolean(), nullable=True),
        sa.Column('heal_action', sa.String(), nullable=True),
        sa.Column('heal_diagnosis', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True),
        sa.Column('max_retries', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('notified', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('faq_entries', 'faq_entries', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('source_filename', sa.String(), nullable=True),
        sa.Column('embedding_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('leads', 'leads', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('visitor_id', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('interest', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('buying_signal_score', sa.Integer(), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('followed_up', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('pending_escalations', 'pending_escalations', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('customer_email', sa.String(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True),
        sa.Column('retry_after', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('report_schedules', 'report_schedules', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('frequency', sa.String(), nullable=True),
        sa.Column('send_via', sa.String(), nullable=True),
        sa.Column('send_at_hour', sa.Integer(), nullable=True),
        sa.Column('send_on_day', sa.Integer(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('last_sent_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('sales_configs', 'sales_configs', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('greeting_delay_seconds', sa.Integer(), nullable=True),
        sa.Column('greeting_message', sa.String(), nullable=True),
        sa.Column('discount_code', sa.String(), nullable=True),
        sa.Column('discount_message', sa.String(), nullable=True),
        sa.Column('demo_booking_url', sa.String(), nullable=True),
        sa.Column('exit_intent_enabled', sa.Boolean(), nullable=True),
        sa.Column('exit_intent_message', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('super_admins', 'super_admins', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    ]),
    ('tenants', 'tenants', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=False),
        sa.Column('owner_name', sa.String(), nullable=False),
        sa.Column('owner_email', sa.String(), nullable=False),
        sa.Column('company_name', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('api_key', sa.String(), nullable=False),
        sa.Column('plan', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('monthly_message_limit', sa.Integer(), nullable=True),
        sa.Column('messages_used_this_month', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('api_key'),
        sa.UniqueConstraint('owner_email'),
    ]),
    ('usage_logs', 'usage_logs', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('total_messages', sa.Integer(), nullable=True),
        sa.Column('ai_messages', sa.Integer(), nullable=True),
        sa.Column('auto_reply_messages', sa.Integer(), nullable=True),
        sa.Column('escalations', sa.Integer(), nullable=True),
        sa.Column('leads_captured', sa.Integer(), nullable=True),
        sa.Column('voice_messages', sa.Integer(), nullable=True),
        sa.Column('estimated_api_cost', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('visitors', 'visitors', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('visitor_id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('first_seen', sa.DateTime(), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('visit_count', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bot_id', 'visitor_id', name='uq_visitor_bot'),
    ]),
    ('webhook_configs', 'webhook_configs', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('webhook_url', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('notify_on', sa.String(), nullable=True),
        sa.Column('last_test_ok', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('messages', 'messages', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('was_auto_reply', sa.Boolean(), nullable=True),
        sa.Column('detected_language', sa.String(), nullable=True),
        sa.Column('input_method', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id']),
        sa.PrimaryKeyConstraint('id'),
    ]),
    ('visitor_conversations', 'visitor_conversations', [
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bot_id', sa.String(), nullable=True),
        sa.Column('visitor_id', sa.String(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id']),
        sa.PrimaryKeyConstraint('id'),
    ]),
]

_INDEXES: list[tuple[str, str, str, bool]] = [
    ('ix_bot_config_bot_id', 'bot_config', 'bot_id', False),
    ('ix_bot_config_id', 'bot_config', 'id', False),
    ('ix_conversations_bot_id', 'conversations', 'bot_id', False),
    ('ix_conversations_id', 'conversations', 'id', False),
    ('ix_conversations_session_id', 'conversations', 'session_id', True),
    ('ix_error_logs_bot_id', 'error_logs', 'bot_id', False),
    ('ix_faq_entries_bot_id', 'faq_entries', 'bot_id', False),
    ('ix_faq_entries_id', 'faq_entries', 'id', False),
    ('ix_leads_bot_id', 'leads', 'bot_id', False),
    ('ix_leads_id', 'leads', 'id', False),
    ('ix_pending_escalations_bot_id', 'pending_escalations', 'bot_id', False),
    ('ix_report_schedules_bot_id', 'report_schedules', 'bot_id', False),
    ('ix_report_schedules_id', 'report_schedules', 'id', False),
    ('ix_sales_configs_bot_id', 'sales_configs', 'bot_id', False),
    ('ix_sales_configs_id', 'sales_configs', 'id', False),
    ('ix_usage_logs_bot_id', 'usage_logs', 'bot_id', False),
    ('ix_visitors_bot_id', 'visitors', 'bot_id', False),
    ('ix_visitors_email', 'visitors', 'email', False),
    ('ix_visitors_id', 'visitors', 'id', False),
    ('ix_visitors_visitor_id', 'visitors', 'visitor_id', False),
    ('ix_webhook_configs_bot_id', 'webhook_configs', 'bot_id', False),
    ('ix_webhook_configs_id', 'webhook_configs', 'id', False),
    ('ix_messages_bot_id', 'messages', 'bot_id', False),
    ('ix_messages_id', 'messages', 'id', False),
    ('ix_visitor_conversations_bot_id', 'visitor_conversations', 'bot_id', False),
    ('ix_visitor_conversations_id', 'visitor_conversations', 'id', False),
    ('ix_visitor_conversations_visitor_id', 'visitor_conversations', 'visitor_id', False),
    ('ix_tenants_bot_id', 'tenants', 'bot_id', True),
]


def upgrade() -> None:
    """Upgrade schema — idempotent: skips existing tables/indexes."""
    bind = op.get_bind()
    inspector = reflection.Inspector.from_engine(bind)
    existing = set(inspector.get_table_names())

    # Create tables if not already present
    for table_name, _, columns in _TABLES_DEFS:
        if table_name not in existing:
            op.create_table(table_name, *columns)

    # Create indexes with IF NOT EXISTS
    for idx_name, tbl, col, _unique in _INDEXES:
        _idx(idx_name, tbl, col)


def downgrade() -> None:
    """Downgrade schema — only drops tables that exist."""
    bind = op.get_bind()
    inspector = reflection.Inspector.from_engine(bind)
    existing = set(inspector.get_table_names())

    # Drop tables in reverse order (FK-safe)
    for table_name, _, _ in reversed(_TABLES_DEFS):
        if table_name in existing:
            op.drop_table(table_name)
