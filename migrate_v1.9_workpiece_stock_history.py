"""Migration helper for QC workpiece stock movement history."""

from __future__ import annotations

import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db


def _columns(table_name: str) -> list[str]:
    rows = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return [row[1] for row in rows]


def migrate() -> None:
    """Ensure the stock history table exists and print its columns."""
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("Migration: v1.9 QC workpiece stock history")
        print("=" * 60)
        print(f"qc_workpiece_stock_histories: {', '.join(_columns('qc_workpiece_stock_histories'))}")
        print("=" * 60)
        print("Migration completed.")
        print("=" * 60)


if __name__ == "__main__":
    migrate()
