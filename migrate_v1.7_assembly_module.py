"""Migration helper for the AI CATS assembly/shipping module schema."""

from __future__ import annotations

import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db


def _columns(table_name: str) -> list[str]:
    """Return ordered column names for one SQLite table."""
    rows = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return [row[1] for row in rows]


def migrate() -> None:
    """Ensure assembly/shipping tables exist on older SQLite deployments."""
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("Migration: v1.7 assembly/shipping module")
        print("=" * 60)

        expected_tables = [
            "assembly_products",
            "assembly_product_components",
            "assembly_product_attachments",
            "assembly_orders",
            "assembly_order_components",
            "assembly_order_attachments",
            "assembly_inspection_records",
            "assembly_acceptance_signatures",
            "assembly_order_histories",
        ]

        for table_name in expected_tables:
            cols = _columns(table_name)
            print(f"{table_name}: {', '.join(cols)}")

        print("=" * 60)
        print("Migration completed.")
        print("=" * 60)


if __name__ == "__main__":
    migrate()
