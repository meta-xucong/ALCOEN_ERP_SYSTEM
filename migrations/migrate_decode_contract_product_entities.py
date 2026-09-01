#!/usr/bin/env python
"""Decode HTML entities accidentally persisted in delivery product models."""

from __future__ import annotations

from html import unescape
import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("ERP_DB_PATH", BASE_DIR / "data" / "erp.db"))
MODEL_TABLES = ("contract_products", "transactions")


def _decode_until_stable(value: str) -> str:
    """Undo repeated HTML escaping without touching ordinary model text."""
    decoded = value
    for _ in range(5):
        next_value = unescape(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def migrate(db_path: Path | str = DB_PATH) -> dict[str, int]:
    """Repair affected model fields and return the number of rows per table."""
    connection = sqlite3.connect(db_path)
    changed_rows: dict[str, int] = {}
    try:
        for table_name in MODEL_TABLES:
            rows = connection.execute(
                f"SELECT id, product_model FROM {table_name} "
                "WHERE product_model IS NOT NULL AND instr(product_model, '&') > 0"
            ).fetchall()
            updates = [
                (_decode_until_stable(product_model), record_id)
                for record_id, product_model in rows
                if _decode_until_stable(product_model) != product_model
            ]
            if updates:
                connection.executemany(
                    f"UPDATE {table_name} SET product_model = ? WHERE id = ?",
                    updates,
                )
            changed_rows[table_name] = len(updates)
        connection.commit()
        return changed_rows
    finally:
        connection.close()


if __name__ == "__main__":
    results = migrate()
    print(f"Entity decoding complete: {results}")
