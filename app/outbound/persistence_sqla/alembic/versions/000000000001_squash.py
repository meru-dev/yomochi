from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "000000000001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ── seed data ─────────────────────────────────────────────────────────────────

_SEEDED_AT = datetime(2026, 5, 25, 0, 0, 0, tzinfo=UTC)


def _gid(i: int) -> str:
    return f"00000000-0000-7000-8001-{i:012d}"


def _lid(i: int) -> str:
    return f"00000000-0000-7000-8002-{i:012d}"


_GROUPS = [
    (_gid(1),  "Food & Drink",    "🍽️", "#FF6B35", "expense"),
    (_gid(2),  "Home",            "🏠", "#45B7D1", "expense"),
    (_gid(3),  "Transport",       "🚗", "#4ECDC4", "expense"),
    (_gid(4),  "Health",          "🏥", "#FFEAA7", "expense"),
    (_gid(5),  "Shopping",        "🛍️", "#F08080", "expense"),
    (_gid(6),  "Personal Care",   "💄", "#FFB6C1", "expense"),
    (_gid(7),  "Entertainment",   "🎬", "#DDA0DD", "expense"),
    (_gid(8),  "Education",       "📚", "#87CEEB", "expense"),
    (_gid(9),  "Financial",       "🛡️", "#9370DB", "expense"),
    (_gid(10), "Employment",      "💼", "#3CB371", "income"),
    (_gid(11), "Self-employment", "💻", "#1E90FF", "income"),
    (_gid(12), "Passive Income",  "📈", "#32CD32", "income"),
    (_gid(13), "Other Income",    "💰", "#FFD700", "income"),
]

_LEAVES = [
    # Food & Drink
    (_lid(1),  "Groceries",                 "🛒", "#90EE90", "expense", _gid(1)),
    (_lid(2),  "Restaurants & Dining",      "🍽️", "#FF6B35", "expense", _gid(1)),
    (_lid(3),  "Cafés & Coffee",            "☕", "#D2B48C", "expense", _gid(1)),
    (_lid(4),  "Alcohol & Bars",            "🍺", "#DAA520", "expense", _gid(1)),
    (_lid(5),  "Convenience Store",         "🏪", "#FF8C00", "expense", _gid(1)),
    # Home
    (_lid(6),  "Rent & Housing",            "🏠", "#45B7D1", "expense", _gid(2)),
    (_lid(7),  "Utilities",                 "💡", "#96CEB4", "expense", _gid(2)),
    (_lid(8),  "Home Goods",                "🛠️", "#B0C4DE", "expense", _gid(2)),
    # Transport
    (_lid(9),  "Public Transit",            "🚇", "#4ECDC4", "expense", _gid(3)),
    (_lid(10), "Taxi & Rideshare",          "🚕", "#20B2AA", "expense", _gid(3)),
    (_lid(11), "Car & Fuel",               "⛽", "#708090", "expense", _gid(3)),
    # Health
    (_lid(12), "Medical & Pharmacy",        "🏥", "#FFEAA7", "expense", _gid(4)),
    (_lid(13), "Fitness & Sports",          "🏋️", "#98FB98", "expense", _gid(4)),
    # Shopping
    (_lid(14), "Clothing & Shoes",          "👗", "#F08080", "expense", _gid(5)),
    (_lid(15), "Electronics",               "📱", "#B0C4DE", "expense", _gid(5)),
    (_lid(16), "General Shopping",          "🛍️", "#FFA07A", "expense", _gid(5)),
    # Personal Care
    (_lid(17), "Beauty & Grooming",         "💄", "#FFB6C1", "expense", _gid(6)),
    (_lid(18), "Pets",                      "🐾", "#F4A460", "expense", _gid(6)),
    # Entertainment
    (_lid(19), "Movies & Events",           "🎬", "#DDA0DD", "expense", _gid(7)),
    (_lid(20), "Streaming & Subscriptions", "📺", "#9370DB", "expense", _gid(7)),
    (_lid(21), "Hobbies",                   "🎨", "#87CEEB", "expense", _gid(7)),
    # Education
    (_lid(22), "Courses & Tuition",         "📚", "#87CEEB", "expense", _gid(8)),
    (_lid(23), "Books & Supplies",          "📖", "#778899", "expense", _gid(8)),
    # Financial
    (_lid(24), "Insurance",                 "🛡️", "#9370DB", "expense", _gid(9)),
    (_lid(25), "Taxes & Fees",              "🧾", "#BC8F8F", "expense", _gid(9)),
    (_lid(26), "Gifts & Donations",         "🎁", "#FF69B4", "expense", _gid(9)),
    # Employment
    (_lid(27), "Salary",                    "💼", "#3CB371", "income",  _gid(10)),
    (_lid(28), "Bonus",                     "🎯", "#2E8B57", "income",  _gid(10)),
    # Self-employment
    (_lid(29), "Freelance",                 "💻", "#1E90FF", "income",  _gid(11)),
    (_lid(30), "Business Income",           "📊", "#4169E1", "income",  _gid(11)),
    # Passive Income
    (_lid(31), "Investments & Dividends",   "📈", "#32CD32", "income",  _gid(12)),
    (_lid(32), "Rental Income",             "🏘️", "#228B22", "income",  _gid(12)),
    # Other Income
    (_lid(33), "Refunds & Cashback",        "💰", "#FFD700", "income",  _gid(13)),
    (_lid(34), "Government Benefits",       "🏛️", "#DAA520", "income",  _gid(13)),
    (_lid(35), "Other",                     "📦", "#808080", "income",  _gid(13)),
]


# ── upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False, server_default="free"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # ── audit_events (range-partitioned; partition management outside Alembic) ─
    op.execute(
        """
        CREATE TABLE audit_events (
            id           UUID        NOT NULL,
            event_type   VARCHAR(50) NOT NULL,
            user_id      UUID,
            occurred_at  TIMESTAMPTZ NOT NULL,
            ip           INET,
            user_agent   TEXT,
            PRIMARY KEY (id, occurred_at)
        ) PARTITION BY RANGE (occurred_at)
        """
    )
    op.execute(
        "CREATE INDEX ix_audit_events_user_id"
        " ON audit_events (user_id) WHERE user_id IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_audit_events_occurred_at ON audit_events (occurred_at)")
    op.execute("CREATE TABLE audit_events_default PARTITION OF audit_events DEFAULT")

    # ── password_reset_tokens ─────────────────────────────────────────────────
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
    )
    op.create_index(
        op.f("ix_password_reset_tokens_token_hash"),
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )

    # ── categories ────────────────────────────────────────────────────────────
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("icon", sa.String(10), nullable=True),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("type", sa.String(7), nullable=False, server_default="expense"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_categories_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_index(
        "uq_categories_user_id_name",
        "categories",
        ["user_id", "name"],
        unique=True,
        postgresql_where="user_id IS NOT NULL",
    )
    op.create_index(
        op.f("ix_categories_user_id"),
        "categories",
        ["user_id"],
        postgresql_where="user_id IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_categories_parent_id",
        "categories",
        "categories",
        ["parent_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "ALTER TABLE categories ADD CONSTRAINT ck_categories_type"
        " CHECK (type IN ('income', 'expense'))"
    )

    # ── outbox_events ─────────────────────────────────────────────────────────
    op.create_table(
        "outbox_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("failed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("trace_context", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_outbox_events_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
    )
    op.create_index(
        op.f("ix_outbox_events_status"),
        "outbox_events",
        ["status"],
        postgresql_where="status = 'PENDING'",
    )
    op.create_index(
        op.f("ix_outbox_events_user_id"),
        "outbox_events",
        ["user_id"],
    )
    op.create_index(
        "ix_outbox_events_pending_created_at",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    # ── recurring_rules ───────────────────────────────────────────────────────
    op.create_table(
        "recurring_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_value", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("merchant", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recurrence", sa.String(20), nullable=False),
        sa.Column("day_of_month", sa.SmallInteger(), nullable=True),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=True),
        sa.Column("month", sa.SmallInteger(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("next_fire_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_recurring_rules_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_recurring_rules_category_id_categories",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recurring_rules"),
        sa.CheckConstraint("day_of_month BETWEEN 1 AND 28", name="ck_recurring_rules_day_of_month"),
        sa.CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_recurring_rules_day_of_week"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name="ck_recurring_rules_month"),
    )
    op.create_index(
        "ix_recurring_rules_due",
        "recurring_rules",
        ["next_fire_date", "status"],
        postgresql_where=sa.text("status = 'active'"),
    )

    # ── transactions ──────────────────────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_value", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("merchant", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("recurring_rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_transactions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recurring_rule_id"],
            ["recurring_rules.id"],
            name="fk_transactions_recurring_rule_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
    )
    op.create_index(op.f("ix_transactions_user_id"), "transactions", ["user_id"])
    op.create_index(op.f("ix_transactions_date"), "transactions", ["date"])
    op.create_index(op.f("ix_transactions_user_id_date"), "transactions", ["user_id", "date"])
    op.create_index(
        "uq_transactions_recurring_rule_date",
        "transactions",
        ["recurring_rule_id", "date"],
        unique=True,
        postgresql_where=sa.text("recurring_rule_id IS NOT NULL"),
    )
    op.execute(
        "CREATE INDEX ix_transactions_merchant_trgm"
        " ON transactions USING GIN (merchant gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_transactions_notes_trgm"
        " ON transactions USING GIN (notes gin_trgm_ops)"
    )

    # ── seed categories ───────────────────────────────────────────────────────
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO categories (id, name, icon, color, type, parent_id, is_system, user_id, created_at)"
            " VALUES (:id, :name, :icon, :color, :type, NULL, TRUE, NULL, :created_at)"
        ),
        [
            {"id": id_, "name": name, "icon": icon, "color": color, "type": type_, "created_at": _SEEDED_AT}
            for id_, name, icon, color, type_ in _GROUPS
        ],
    )
    conn.execute(
        sa.text(
            "INSERT INTO categories (id, name, icon, color, type, parent_id, is_system, user_id, created_at)"
            " VALUES (:id, :name, :icon, :color, :type, :parent_id, TRUE, NULL, :created_at)"
        ),
        [
            {
                "id": id_, "name": name, "icon": icon, "color": color,
                "type": type_, "parent_id": parent_id, "created_at": _SEEDED_AT,
            }
            for id_, name, icon, color, type_, parent_id in _LEAVES
        ],
    )

    # ── insights ──────────────────────────────────────────────────────────────
    op.create_table(
        "insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("context_quality", sa.String(20), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("impact_score", sa.SmallInteger(), nullable=True),
        sa.Column("generated_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("budget_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("processing_deadline", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_insights_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "CREATE INDEX ix_insights_user_id_created_at_id"
        " ON insights (user_id, created_at DESC, id DESC)"
    )

    # ── dirty_periods ─────────────────────────────────────────────────────────
    op.create_table(
        "dirty_periods",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_dirty_periods_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("user_id", "year", "month", name="uq_dirty_periods_user_year_month"),
    )

    # ── user_financial_chunks (hash-partitioned 16 parts) ─────────────────────
    op.execute(
        """
        CREATE TABLE user_financial_chunks (
            id           UUID         NOT NULL DEFAULT gen_random_uuid(),
            user_id      UUID         NOT NULL,
            chunk_type   VARCHAR(30)  NOT NULL,
            period_year  SMALLINT     NOT NULL,
            period_month SMALLINT     NOT NULL,
            content      TEXT         NOT NULL,
            embedding    VECTOR(1536),
            semantic_hash VARCHAR(64) NOT NULL,
            metadata     JSONB        NOT NULL DEFAULT '{}',
            created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ,
            PRIMARY KEY (id, user_id)
        ) PARTITION BY HASH (user_id)
        """
    )
    for i in range(16):
        op.execute(
            f"CREATE TABLE user_financial_chunks_{i}"
            f" PARTITION OF user_financial_chunks"
            f" FOR VALUES WITH (modulus 16, remainder {i})"
        )
    op.execute(
        "CREATE UNIQUE INDEX uq_chunks_user_type_period"
        " ON user_financial_chunks (user_id, chunk_type, period_year, period_month)"
    )
    op.execute(
        "CREATE INDEX ix_chunks_user_id_embedding"
        " ON user_financial_chunks"
        " USING hnsw (embedding vector_cosine_ops)"
        " WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "ALTER TABLE user_financial_chunks"
        " ADD CONSTRAINT fk_chunks_user_id_users"
        " FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
    )

    # ── user_alerts ───────────────────────────────────────────────────────────
    op.create_table(
        "user_alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("subtype", sa.String(100), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("period_year", sa.SmallInteger(), nullable=False),
        sa.Column("period_month", sa.SmallInteger(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_alerts_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_user_alerts_user_id_created_at",
        "user_alerts",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_unique_constraint(
        "ux_user_alerts_dedup",
        "user_alerts",
        ["user_id", "subtype", "period_year", "period_month"],
    )
    op.create_index(
        "ix_user_alerts_unread",
        "user_alerts",
        ["user_id"],
        postgresql_where=sa.text("is_read = FALSE"),
    )

    # ── portrait_queue ────────────────────────────────────────────────────────
    op.create_table(
        "portrait_queue",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "marked_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_portrait_queue_user_id_users",
            ondelete="CASCADE",
        ),
    )

    # ── chat_turns ────────────────────────────────────────────────────────────
    op.create_table(
        "chat_turns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunks_used", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_chat_turns_user_id_users",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_chat_turns_user_id_created_at",
        "chat_turns",
        ["user_id", sa.text("created_at DESC")],
    )
    op.execute(
        "ALTER TABLE chat_turns ADD CONSTRAINT ck_chat_turns_role"
        " CHECK (role IN ('user', 'assistant'))"
    )


# ── downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    op.drop_table("chat_turns")
    op.drop_table("portrait_queue")
    op.drop_table("user_alerts")
    op.execute("DROP TABLE IF EXISTS user_financial_chunks CASCADE")
    op.drop_table("dirty_periods")
    op.drop_table("insights")
    op.drop_table("outbox_events")
    # Drop transactions FK to recurring_rules before dropping recurring_rules
    op.drop_index("uq_transactions_recurring_rule_date", table_name="transactions")
    op.drop_constraint("fk_transactions_recurring_rule_id", "transactions", type_="foreignkey")
    op.drop_table("transactions")
    op.drop_table("recurring_rules")
    op.execute("DELETE FROM categories WHERE is_system = TRUE")
    op.drop_constraint("fk_categories_parent_id", "categories", type_="foreignkey")
    op.drop_table("categories")
    op.drop_table("password_reset_tokens")
    op.execute("DROP TABLE audit_events_default")
    op.execute("DROP TABLE audit_events")
    op.drop_table("users")
