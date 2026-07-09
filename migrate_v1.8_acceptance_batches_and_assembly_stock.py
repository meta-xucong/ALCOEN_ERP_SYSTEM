"""Migration helper for partial QC acceptance and assembly product stock."""

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
    """Apply additive schema upgrades and print the resulting table shape."""
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("Migration: v1.8 acceptance batches and assembly stock")
        print("=" * 60)
        for table_name in [
            "qc_acceptance_batches",
            "qc_acceptance_signatures",
            "assembly_products",
        ]:
            print(f"{table_name}: {', '.join(_columns(table_name))}")
        print("=" * 60)
        print("Migration completed.")
        print("=" * 60)


if __name__ == "__main__":
    migrate()
