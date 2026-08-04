#!/usr/bin/env python
"""Add the delivery batch column used by contract delivery-note printing."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("ERP_DB_PATH", BASE_DIR / "data" / "erp.db"))


def main() -> None:
    """Add the nullable batch column and its lookup index idempotently."""
    connection = sqlite3.connect(DB_PATH)
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(transactions)").fetchall()
        }
        if "delivery_batch_no" not in columns:
            connection.execute(
                "ALTER TABLE transactions ADD COLUMN delivery_batch_no VARCHAR(100)"
            )

        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_transactions_delivery_batch_no "
            "ON transactions (delivery_batch_no)"
        )
        connection.commit()
        print(f"Migration complete: {DB_PATH}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
