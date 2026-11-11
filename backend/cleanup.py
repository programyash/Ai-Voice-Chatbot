"""Remove locally stored customer data older than a chosen retention window."""
import argparse
from datetime import datetime, timedelta, timezone

from backend.app.db import connection, init_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()
    if not 1 <= args.days <= 3650:
        raise SystemExit("--days must be between 1 and 3650")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    init_db()
    with connection() as db:
        db.execute("DELETE FROM messages WHERE conversation_id IN (SELECT id FROM conversations WHERE updated_at < ?)", (cutoff,))
        conversations = db.execute("DELETE FROM conversations WHERE updated_at < ?", (cutoff,)).rowcount
        leads = db.execute("DELETE FROM leads WHERE created_at < ?", (cutoff,)).rowcount
        visits = db.execute("DELETE FROM visits WHERE created_at < ?", (cutoff,)).rowcount
        callbacks = db.execute("DELETE FROM callbacks WHERE created_at < ?", (cutoff,)).rowcount
    print({"conversations": conversations, "leads": leads, "visits": visits, "callbacks": callbacks})


if __name__ == "__main__":
    main()
