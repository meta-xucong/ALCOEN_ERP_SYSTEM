#!/usr/bin/env python
"""
数据库迁移脚本：
1. contracts 新增 actual_received_value、discount_value
2. payment_records 新增 invoice_date
3. 回填合同金额字段并统一保留 2 位小数
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text


def _get_columns(table_name: str) -> list:
    result = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return [row[1] for row in result]


def migrate():
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("Migration: add invoice/actual amount fields")
        print("=" * 60)

        contract_columns = _get_columns("contracts")
        payment_columns = _get_columns("payment_records")

        if "actual_received_value" not in contract_columns:
            print("[1/5] add contracts.actual_received_value")
            db.session.execute(text("ALTER TABLE contracts ADD COLUMN actual_received_value FLOAT DEFAULT 0"))
        else:
            print("[1/5] contracts.actual_received_value already exists")

        if "discount_value" not in contract_columns:
            print("[2/5] add contracts.discount_value")
            db.session.execute(text("ALTER TABLE contracts ADD COLUMN discount_value FLOAT DEFAULT 0"))
        else:
            print("[2/5] contracts.discount_value already exists")

        if "invoice_date" not in payment_columns:
            print("[3/5] add payment_records.invoice_date")
            db.session.execute(text("ALTER TABLE payment_records ADD COLUMN invoice_date DATE"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_records_invoice_date ON payment_records(invoice_date)"))
        else:
            print("[3/5] payment_records.invoice_date already exists")

        print("[4/5] backfill and normalize contract amount fields")
        db.session.execute(text("""
            UPDATE contracts
            SET actual_received_value = COALESCE(actual_received_value, total_value, 0)
            WHERE actual_received_value IS NULL
        """))
        db.session.execute(text("""
            UPDATE contracts
            SET total_value = ROUND(COALESCE(total_value, 0), 2),
                actual_received_value = ROUND(COALESCE(actual_received_value, 0), 2)
        """))
        db.session.execute(text("""
            UPDATE contracts
            SET discount_value = ROUND(
                CASE
                    WHEN COALESCE(total_value, 0) - COALESCE(actual_received_value, 0) > 0
                    THEN COALESCE(total_value, 0) - COALESCE(actual_received_value, 0)
                    ELSE 0
                END, 2
            )
        """))

        db.session.commit()

        print("[5/5] verify schema with PRAGMA")
        print("contracts columns:", ", ".join(_get_columns("contracts")))
        print("payment_records columns:", ", ".join(_get_columns("payment_records")))

        print("=" * 60)
        print("Migration completed.")
        print("=" * 60)


if __name__ == "__main__":
    migrate()
