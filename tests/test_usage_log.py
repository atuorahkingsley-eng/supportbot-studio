"""Tests for Bug 7 — UsageLog (bot_id, date) uniqueness + dialect-aware upsert.

Pre-fix the daily logger could create duplicate rows for the same
``(bot_id, date)`` tuple under concurrent / retried runs, corrupting the
monthly billing roll-up. The fix is twofold:

  1. UniqueConstraint('bot_id', 'date', name='uq_usagelog_bot_date') on the
     model (mirrored by an Alembic migration that deduplicates pre-existing
     rows before adding the constraint).
  2. Dialect-aware ``insert(...).on_conflict_do_update(...)`` in
     ``_log_daily_usage`` keyed on that conflict target.

Originally ``_log_daily_usage`` passed ``constraint="uq_usagelog_bot_date"``
to ``on_conflict_do_update`` — Postgres-only syntax that crashed on SQLite
(local dev, CI, test env) with::

    TypeError: Insert.on_conflict_do_update() got an unexpected
    keyword argument 'constraint'

The fix swapped to ``index_elements=["bot_id", "date"]``, which both
dialects accept. The fourth test (``test_upsert_works_on_sqlite``) is
the regression guard for that fix — it invokes the production function
directly so any future revert is caught immediately.

The first three tests exercise the same upsert idiom via a local helper
(matching the SQLite-correct invocation) to lock in the DB-level
contracts: no duplicates on the same key, separate rows for different
keys.
"""

from datetime import date

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database import UsageLog


# ── Helpers ───────────────────────────────────────────────────────────────────

def _upsert(db, *, bot_id: str, d: date, total: int):
    """Issue the upsert main.py SHOULD use on SQLite — keyed on
    ``index_elements`` rather than ``constraint=``. Same semantic intent;
    SQLite-compatible invocation.

    Behaviourally identical to what the Postgres branch does with
    ``constraint="uq_usagelog_bot_date"`` because both target the same
    UNIQUE on (bot_id, date) defined on the UsageLog model.
    """
    stmt = sqlite_insert(UsageLog).values(
        bot_id=bot_id,
        date=d,
        total_messages=total,
        ai_messages=total,
        auto_reply_messages=0,
        voice_messages=0,
        leads_captured=0,
        estimated_api_cost=round(total * 0.003, 4),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["bot_id", "date"],
        set_={
            "total_messages": stmt.excluded.total_messages,
            "ai_messages": stmt.excluded.ai_messages,
            "auto_reply_messages": stmt.excluded.auto_reply_messages,
            "voice_messages": stmt.excluded.voice_messages,
            "leads_captured": stmt.excluded.leads_captured,
            "estimated_api_cost": stmt.excluded.estimated_api_cost,
        },
    )
    db.execute(stmt)
    db.commit()


# ── 1. Concurrent upsert for same (bot_id, date) collapses into 1 row ─────────

def test_no_duplicate_on_concurrent_upsert(test_db):
    """Fire 10 upserts in a row for the same ``(bot_id, date)``. After all
    complete, exactly ONE row exists — the unique constraint plus ON
    CONFLICT DO UPDATE replaces the would-be duplicates.

    SQLite serialises writes through a single connection (StaticPool), so
    "concurrent" here really means "ten sequential upserts that would each
    have inserted a new row pre-fix"; the assertion that matters is the
    end state, not the scheduling. The DB-level constraint is what
    guarantees that parallel writes on Postgres collapse the same way.
    """
    today = date(2026, 5, 12)
    for i in range(10):
        # Vary the total so we can also check the final UPDATE actually
        # writes the LAST value, not just collapses silently.
        _upsert(test_db, bot_id="bot_dup", d=today, total=i + 1)

    rows = test_db.query(UsageLog).filter(
        UsageLog.bot_id == "bot_dup",
        UsageLog.date == today,
    ).all()
    assert len(rows) == 1, f"Expected exactly 1 row after upserts, got {len(rows)}"

    # The last upsert (i=9, total=10) should be the surviving value —
    # proves the set_={...} clause actually applied on conflict (not just
    # that the INSERT was silently dropped).
    assert rows[0].total_messages == 10


# ── 2. Different dates → separate rows ────────────────────────────────────────

def test_different_dates_create_separate_rows(test_db):
    """The unique constraint is on (bot_id, date), not bot_id alone. Two
    different dates for the same bot must coexist."""
    bot_id = "bot_dates"
    d1 = date(2026, 5, 1)
    d2 = date(2026, 5, 2)

    _upsert(test_db, bot_id=bot_id, d=d1, total=5)
    _upsert(test_db, bot_id=bot_id, d=d2, total=7)

    rows = test_db.query(UsageLog).filter(UsageLog.bot_id == bot_id).all()
    assert len(rows) == 2, f"Expected 2 rows for 2 dates, got {len(rows)}"

    dates_seen = {r.date for r in rows}
    assert dates_seen == {d1, d2}


# ── 3. Different bots → separate rows ─────────────────────────────────────────

def test_different_bots_create_separate_rows(test_db):
    """Same date but different bot_id: the constraint is keyed on the pair,
    so both rows survive. Catches the failure mode where a too-loose
    UniqueConstraint (only on ``date``) would have collapsed all tenants
    into one bill."""
    today = date(2026, 5, 12)
    _upsert(test_db, bot_id="bot_a", d=today, total=3)
    _upsert(test_db, bot_id="bot_b", d=today, total=4)

    rows = test_db.query(UsageLog).filter(UsageLog.date == today).all()
    assert len(rows) == 2

    bots_seen = {r.bot_id for r in rows}
    assert bots_seen == {"bot_a", "bot_b"}

    # Each tenant's count is independent.
    by_bot = {r.bot_id: r.total_messages for r in rows}
    assert by_bot["bot_a"] == 3
    assert by_bot["bot_b"] == 4


# ── 4. Regression: _log_daily_usage works on SQLite ───────────────────────────

def test_upsert_works_on_sqlite(test_client, test_db, test_tenant):
    """Regression test for the ``constraint=`` vs ``index_elements=``
    portability bug in ``backend/main.py:_log_daily_usage``.

    Pre-fix the helper called::

        stmt.on_conflict_do_update(constraint="uq_usagelog_bot_date", ...)

    which is Postgres-only — the SQLite dialect's
    ``on_conflict_do_update`` rejects ``constraint=`` with::

        TypeError: Insert.on_conflict_do_update() got an unexpected
        keyword argument 'constraint'

    Post-fix the helper passes ``index_elements=["bot_id", "date"]``,
    which both dialects accept. This test invokes the production
    function directly against the SQLite test engine and asserts it
    completes without raising. Running it twice also exercises the
    upsert path — a successful second call proves ON CONFLICT actually
    fired (otherwise the unique constraint would raise IntegrityError).

    The ``test_client`` fixture is included for its side effect:
    it monkeypatches ``backend.main.SessionLocal`` to the test engine,
    so the ``SessionLocal()`` call inside ``_log_daily_usage`` lands on
    our in-memory DB rather than whatever DATABASE_URL points to.
    """
    from backend.main import _log_daily_usage

    # First call: INSERT path. Must not raise TypeError.
    _log_daily_usage()

    # Second call: ON CONFLICT DO UPDATE path. Must not raise
    # IntegrityError (unique constraint violation) — proves the upsert
    # actually upserted and didn't try to insert a duplicate.
    _log_daily_usage()

    # And exactly one row survives for this tenant+date.
    rows = test_db.query(UsageLog).filter(
        UsageLog.bot_id == test_tenant.bot_id,
        UsageLog.date == date.today(),
    ).all()
    assert len(rows) == 1, (
        f"Expected 1 UsageLog row after 2 invocations, got {len(rows)} — "
        "the second call should have UPDATEd, not INSERTed."
    )
