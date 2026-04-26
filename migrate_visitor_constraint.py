"""
Migration: drop the global UNIQUE on visitors.visitor_id and replace it with
a composite UNIQUE on (bot_id, visitor_id).

Safe to run multiple times — detects current schema state and skips when
the table is already migrated or doesn't exist yet.

Usage:
    python migrate_visitor_constraint.py
"""
import os
import sqlite3
import sys
from datetime import datetime

DB_PATH = os.path.join("data", "supportbot.db")


def _table_exists(cur, name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def _has_single_column_visitor_id_unique(cur) -> bool:
    """True if any UNIQUE index on visitors covers visitor_id alone."""
    cur.execute("PRAGMA index_list('visitors')")
    for row in cur.fetchall():
        # row: (seq, name, unique, origin, partial)
        idx_name, is_unique = row[1], row[2]
        if not is_unique:
            continue
        cur.execute(f"PRAGMA index_info('{idx_name}')")
        cols = [r[2] for r in cur.fetchall()]
        if cols == ["visitor_id"]:
            return True
    return False


def _has_composite_unique(cur) -> bool:
    """True if a UNIQUE index on (bot_id, visitor_id) already exists."""
    cur.execute("PRAGMA index_list('visitors')")
    for row in cur.fetchall():
        idx_name, is_unique = row[1], row[2]
        if not is_unique:
            continue
        cur.execute(f"PRAGMA index_info('{idx_name}')")
        cols = sorted(r[2] for r in cur.fetchall())
        if cols == sorted(["bot_id", "visitor_id"]):
            return True
    return False


def migrate() -> int:
    if not os.path.exists(DB_PATH):
        print(f"[skip] {DB_PATH} not found — fresh deploys create the correct schema automatically.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    conn.isolation_level = None  # we'll manage the transaction explicitly
    cur = conn.cursor()

    try:
        if not _table_exists(cur, "visitors"):
            print("[skip] visitors table does not exist yet — nothing to migrate.")
            return 0

        has_single = _has_single_column_visitor_id_unique(cur)
        has_composite = _has_composite_unique(cur)

        if not has_single and has_composite:
            print("[skip] visitors table already migrated (composite unique on (bot_id, visitor_id) present).")
            return 0

        if not has_single and not has_composite:
            # Old single-column unique already gone, but composite missing — just add it.
            print("[info] No single-column UNIQUE found; adding composite unique index only.")
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_visitor_bot ON visitors(bot_id, visitor_id)"
            )
            print("[ok] Composite unique index created.")
            return 0

        # Full table rebuild path
        backup_name = f"visitors_backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        print(f"[info] Rebuilding visitors table. Backup: {backup_name}")

        cur.execute("BEGIN")
        cur.execute("PRAGMA foreign_keys=OFF")

        cur.execute("""
            CREATE TABLE visitors_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT DEFAULT 'default',
                visitor_id TEXT NOT NULL,
                email TEXT,
                first_seen DATETIME,
                last_seen DATETIME,
                visit_count INTEGER DEFAULT 1,
                name TEXT,
                tags TEXT DEFAULT '[]',
                notes TEXT,
                CONSTRAINT uq_visitor_bot UNIQUE (bot_id, visitor_id)
            )
        """)

        cur.execute("""
            INSERT INTO visitors_new
                (id, bot_id, visitor_id, email, first_seen, last_seen,
                 visit_count, name, tags, notes)
            SELECT id, COALESCE(bot_id, 'default'), visitor_id, email,
                   first_seen, last_seen, visit_count, name,
                   COALESCE(tags, '[]'), notes
            FROM visitors
        """)
        migrated_rows = cur.execute("SELECT COUNT(*) FROM visitors_new").fetchone()[0]

        cur.execute(f"ALTER TABLE visitors RENAME TO {backup_name}")
        cur.execute("ALTER TABLE visitors_new RENAME TO visitors")

        cur.execute("CREATE INDEX IF NOT EXISTS ix_visitors_bot_id ON visitors(bot_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_visitors_visitor_id ON visitors(visitor_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_visitors_email ON visitors(email)")

        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("COMMIT")

        print(f"[ok] Migrated {migrated_rows} visitor row(s). Old table preserved as {backup_name}.")
        print("[ok] Composite UNIQUE(bot_id, visitor_id) is now in place.")
        return 0

    except Exception as e:
        try:
            cur.execute("ROLLBACK")
        except Exception:
            pass
        print(f"[fail] Migration aborted: {e}")
        return 1

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(migrate())
