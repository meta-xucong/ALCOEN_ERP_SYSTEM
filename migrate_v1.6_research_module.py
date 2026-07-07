#!/usr/bin/env python
"""Migration for the AI CATS research/experiment module schema."""

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
    """Ensure research-module tables exist on older SQLite deployments."""
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("Migration: v1.6 research module")
        print("=" * 60)

        # create_app() already applies db.create_all() and lightweight schema upgrades.
        expected_tables = [
            "research_projects",
            "research_project_attachments",
            "research_batches",
            "research_batch_attachments",
            "research_review_records",
            "research_acceptance_signatures",
            "research_batch_histories",
        ]

        for table_name in expected_tables:
            cols = _columns(table_name)
            print(f"{table_name}: {', '.join(cols)}")

        print("=" * 60)
        print("Migration completed.")
        print("=" * 60)


if __name__ == "__main__":
    migrate()
