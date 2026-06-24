"""Supabase + LangGraph checkpointer wiring.

`get_checkpointer()` is an async context manager — use it like:

    async with get_checkpointer() as saver:
        graph = build_graph(saver)
        ...

Falls back to in-memory MemorySaver if SUPABASE_DB_URL is not set, so the
graph still runs (without persistence) during local dev.

NOTE: Supabase's transaction pooler (port 6543) is PgBouncer in transaction
mode, which does NOT support prepared statements. We pass `prepare_threshold=0`
to psycopg so it disables them. If you switch to a direct (5432) or session-
pooler connection, the same kwargs are harmless.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from hireguard.settings import settings, use_postgres_checkpointer

# Connection kwargs that make psycopg play nicely with Supabase's tx pooler.
_PG_KWARGS = {
    "autocommit": True,
    "prepare_threshold": None,  # disable server-side prepared statements (PgBouncer tx-mode)
}


@asynccontextmanager
async def get_checkpointer():
    """Yields a LangGraph checkpointer. Postgres (via Supabase) if configured,
    else in-memory MemorySaver."""
    if use_postgres_checkpointer():
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        async with AsyncConnectionPool(
            conninfo=settings()["SUPABASE_DB_URL"],
            max_size=10,
            kwargs=_PG_KWARGS,
            open=False,
        ) as pool:
            await pool.open()
            saver = AsyncPostgresSaver(pool)
            await saver.setup()
            yield saver
    else:
        from langgraph.checkpoint.memory import MemorySaver

        yield MemorySaver()


def get_supabase():
    """Returns a supabase-py client. Used by Member B (rules KG) and persist node."""
    from supabase import create_client

    s = settings()
    if not s["SUPABASE_URL"] or not s["SUPABASE_KEY"]:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY required. See .env.example.")
    return create_client(s["SUPABASE_URL"], s["SUPABASE_KEY"])


async def save_audit_memo(run_id: str, packet_json: str, memo_json: str) -> None:
    """Persist a final approved audit memo to the audit_memos table.

    Called by the persist step after HITL approval. Best-effort: if Supabase
    is misconfigured we log and continue — the demo still works without it.
    """
    import logging

    if not use_postgres_checkpointer():
        logging.warning("SUPABASE_DB_URL not set; skipping persistence.")
        return

    import psycopg

    async with await psycopg.AsyncConnection.connect(
        settings()["SUPABASE_DB_URL"], **_PG_KWARGS
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO audit_memos (run_id, packet, memo, approved_at)
                VALUES (%s, %s::jsonb, %s::jsonb, NOW())
                """,
                (run_id, packet_json, memo_json),
            )
