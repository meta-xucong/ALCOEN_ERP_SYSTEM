"""Migration helper for assembly tiered products and partial acceptance batches."""

from __future__ import annotations

import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db


TABLES = [
    'assembly_products',
    'assembly_product_components',
    'assembly_order_components',
    'assembly_acceptance_batches',
    'assembly_acceptance_signatures',
]


def _columns(table_name: str) -> list[str]:
    rows = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return [row[1] for row in rows]


def migrate() -> None:
    """Run app lightweight migrations and print the upgraded assembly schema."""
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("Migration: v2.0 assembly tiered products and partial acceptance")
        print("=" * 60)
        for table_name in TABLES:
            print(f"{table_name}: {', '.join(_columns(table_name))}")
        print("=" * 60)
        print("Migration completed.")
        print("=" * 60)


if __name__ == "__main__":
    migrate()
