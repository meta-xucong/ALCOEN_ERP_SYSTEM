"""Migration helper for assembly outbound shipping and COA templates."""

from __future__ import annotations

import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db


TABLES = [
    'qc_workpiece_attachments',
    'assembly_product_attachments',
    'assembly_outbound_orders',
    'assembly_outbound_batches',
    'assembly_outbound_signatures',
    'assembly_outbound_histories',
]


def _columns(table_name: str) -> list[str]:
    rows = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return [row[1] for row in rows]


def migrate() -> None:
    """Run app lightweight migrations and print the upgraded outbound schema."""
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("Migration: v2.1 assembly outbound shipping and COA templates")
        print("=" * 60)
        for table_name in TABLES:
            print(f"{table_name}: {', '.join(_columns(table_name))}")
        print("=" * 60)
        print("Migration completed.")
        print("=" * 60)


if __name__ == "__main__":
    migrate()
