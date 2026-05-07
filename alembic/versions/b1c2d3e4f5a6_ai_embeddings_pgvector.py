"""Phase 5 – pgvector extension and ai_embeddings table.

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-05-07 04:00:00.000000

Adds:
  • CREATE EXTENSION IF NOT EXISTS vector  (PostgreSQL only)
  • ai_embeddings table with a vector(768) column
  • HNSW index for fast approximate nearest-neighbour search

SQLite-safe: every PostgreSQL-specific DDL is guarded by dialect checks.
On SQLite a plain TEXT column stores the embedding as a JSON-serialised list;
the HNSW index and vector extension are skipped entirely.
"""
import sqlalchemy as sa
from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None

_EMBED_DIM = 768


def _dialect() -> str:
    return op.get_bind().dialect.name


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(table: str, index_name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(i["name"] == index_name for i in insp.get_indexes(table))


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    dialect = _dialect()

    # 5.1 — pgvector extension (PostgreSQL only)
    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 5.2 — ai_embeddings table
    if not _has_table("ai_embeddings"):
        if dialect == "postgresql":
            # Use the pgvector VECTOR type directly via raw DDL so we don't
            # need pgvector as a Python dependency at migration time.
            op.execute(f"""
                CREATE TABLE ai_embeddings (
                    id              SERIAL PRIMARY KEY,
                    source_table    VARCHAR(100) NOT NULL,
                    source_id       INTEGER      NOT NULL,
                    chunk_index     INTEGER      NOT NULL DEFAULT 0,
                    embedding       VECTOR({_EMBED_DIM}) NOT NULL,
                    model_name      VARCHAR(100) NOT NULL DEFAULT 'nomic-embed-text',
                    computed_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    content_hash    VARCHAR(64)  NULL
                )
            """)

            # Unique index: one embedding per (source_table, source_id, chunk_index, model_name)
            op.execute("""
                CREATE UNIQUE INDEX uq_ai_embeddings_source
                    ON ai_embeddings (source_table, source_id, chunk_index, model_name)
            """)

            # 5.2 HNSW index — cosine distance, m=16, ef_construction=64
            if not _has_index("ai_embeddings", "idx_ai_embeddings_hnsw"):
                op.execute("""
                    CREATE INDEX idx_ai_embeddings_hnsw
                        ON ai_embeddings
                        USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64)
                """)

            # B-tree index for fast lookup by source
            op.execute("""
                CREATE INDEX idx_ai_embeddings_source_lookup
                    ON ai_embeddings (source_table, source_id)
            """)

        else:
            # SQLite fallback: store embedding as JSON text; no vector ops
            op.create_table(
                "ai_embeddings",
                sa.Column("id",           sa.Integer(),     primary_key=True),
                sa.Column("source_table", sa.String(100),   nullable=False),
                sa.Column("source_id",    sa.Integer(),     nullable=False),
                sa.Column("chunk_index",  sa.Integer(),     nullable=False, server_default="0"),
                sa.Column("embedding",    sa.Text(),        nullable=False),  # JSON list
                sa.Column("model_name",   sa.String(100),   nullable=False, server_default="nomic-embed-text"),
                sa.Column("computed_at",  sa.DateTime(),    server_default=sa.func.now()),
                sa.Column("content_hash", sa.String(64),    nullable=True),
                sa.UniqueConstraint(
                    "source_table", "source_id", "chunk_index", "model_name",
                    name="uq_ai_embeddings_source",
                ),
            )
            op.create_index(
                "idx_ai_embeddings_source_lookup",
                "ai_embeddings",
                ["source_table", "source_id"],
            )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    dialect = _dialect()

    if _has_table("ai_embeddings"):
        if dialect == "postgresql":
            op.execute("DROP TABLE IF EXISTS ai_embeddings CASCADE")
        else:
            op.drop_table("ai_embeddings")

    # Leave the vector extension installed; dropping it would break other
    # objects that depend on it and cannot be undone safely in a single step.
