#!/usr/bin/env python
"""
Migration for v1.5 contract payment/invoice amount updates.

This migration keeps older databases compatible with the current ERP code by:
1. Ensuring `contracts.actual_received_value` and `contracts.discount_value` exist.
2. Rebuilding `payment_records` so `payment_amount` / `payment_date` are optional.
3. Adding `payment_records.invoice_amount`.
4. Backfilling legacy invoice rows so historical `invoice_date` implies an invoice amount.
"""
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db


def _get_table_info(table_name: str) -> list:
    return db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()


def _get_columns(table_name: str) -> list[str]:
    return [row[1] for row in _get_table_info(table_name)]


def _column_notnull_map(table_name: str) -> dict[str, bool]:
    return {row[1]: bool(row[3]) for row in _get_table_info(table_name)}


def _ensure_contract_amount_columns() -> None:
    contract_columns = _get_columns("contracts")

    if "actual_received_value" not in contract_columns:
        print("[1/6] add contracts.actual_received_value")
        db.session.execute(text("ALTER TABLE contracts ADD COLUMN actual_received_value FLOAT DEFAULT 0"))
    else:
        print("[1/6] contracts.actual_received_value already exists")

    if "discount_value" not in contract_columns:
        print("[2/6] add contracts.discount_value")
        db.session.execute(text("ALTER TABLE contracts ADD COLUMN discount_value FLOAT DEFAULT 0"))
    else:
        print("[2/6] contracts.discount_value already exists")

    print("[3/6] normalize contract amount fields")
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
            END,
            2
        )
    """))


def _needs_payment_table_rebuild() -> bool:
    payment_columns = _get_columns("payment_records")
    payment_notnull = _column_notnull_map("payment_records")

    if "invoice_amount" not in payment_columns:
        return True
    if "invoice_date" not in payment_columns:
        return True
    if payment_notnull.get("payment_amount", False):
        return True
    if payment_notnull.get("payment_date", False):
        return True
    return False


def _rebuild_payment_records() -> None:
    print("[4/6] rebuild payment_records for optional payment fields and invoice amount")
    payment_columns = set(_get_columns("payment_records"))
    has_invoice_date = "invoice_date" in payment_columns
    has_invoice_amount = "invoice_amount" in payment_columns

    invoice_date_expr = "invoice_date" if has_invoice_date else "NULL"
    invoice_amount_expr = (
        "CASE "
        "WHEN COALESCE(invoice_amount, 0) > 0 THEN ROUND(invoice_amount, 2) "
        f"WHEN {invoice_date_expr} IS NOT NULL AND COALESCE(payment_amount, 0) > 0 THEN ROUND(payment_amount, 2) "
        "ELSE NULL END"
        if has_invoice_amount
        else (
            "CASE "
            f"WHEN {invoice_date_expr} IS NOT NULL AND COALESCE(payment_amount, 0) > 0 THEN ROUND(payment_amount, 2) "
            "ELSE NULL END"
        )
    )

    db.session.execute(text("PRAGMA foreign_keys=OFF"))
    db.session.execute(text("""
        CREATE TABLE payment_records_new (
            id INTEGER PRIMARY KEY,
            contract_id INTEGER,
            company_name VARCHAR(100) NOT NULL,
            payment_amount FLOAT,
            invoice_amount FLOAT,
            payment_date DATE,
            invoice_date DATE,
            transaction_id INTEGER,
            contract_product_id INTEGER,
            handler VARCHAR(50),
            remark TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY(contract_id) REFERENCES contracts(id),
            FOREIGN KEY(transaction_id) REFERENCES transactions(id),
            FOREIGN KEY(contract_product_id) REFERENCES contract_products(id)
        )
    """))
    db.session.execute(text(f"""
        INSERT INTO payment_records_new (
            id,
            contract_id,
            company_name,
            payment_amount,
            invoice_amount,
            payment_date,
            invoice_date,
            transaction_id,
            contract_product_id,
            handler,
            remark,
            created_at,
            updated_at
        )
        SELECT
            id,
            contract_id,
            company_name,
            CASE
                WHEN COALESCE(payment_amount, 0) > 0 THEN ROUND(payment_amount, 2)
                ELSE NULL
            END,
            {invoice_amount_expr},
            payment_date,
            {invoice_date_expr},
            transaction_id,
            contract_product_id,
            handler,
            remark,
            created_at,
            updated_at
        FROM payment_records
    """))
    db.session.execute(text("DROP TABLE payment_records"))
    db.session.execute(text("ALTER TABLE payment_records_new RENAME TO payment_records"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_records_contract_id ON payment_records(contract_id)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_records_company_name ON payment_records(company_name)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_records_payment_date ON payment_records(payment_date)"))
    db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_records_invoice_date ON payment_records(invoice_date)"))
    db.session.execute(text("PRAGMA foreign_keys=ON"))


def migrate() -> None:
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("Migration: v1.5 contract invoice amounts")
        print("=" * 60)

        _ensure_contract_amount_columns()

        if _needs_payment_table_rebuild():
            _rebuild_payment_records()
        else:
            print("[4/6] payment_records already matches the new schema")

        print("[5/6] normalize legacy payment/invoice values")
        db.session.execute(text("""
            UPDATE payment_records
            SET payment_amount = NULL
            WHERE payment_amount IS NOT NULL AND payment_amount <= 0
        """))
        db.session.execute(text("""
            UPDATE payment_records
            SET invoice_amount = NULL
            WHERE invoice_amount IS NOT NULL AND invoice_amount <= 0
        """))
        db.session.execute(text("""
            UPDATE payment_records
            SET invoice_amount = ROUND(payment_amount, 2)
            WHERE invoice_amount IS NULL
              AND invoice_date IS NOT NULL
              AND payment_amount IS NOT NULL
              AND payment_amount > 0
        """))
        db.session.execute(text("""
            UPDATE payment_records
            SET payment_amount = ROUND(payment_amount, 2)
            WHERE payment_amount IS NOT NULL
        """))
        db.session.execute(text("""
            UPDATE payment_records
            SET invoice_amount = ROUND(invoice_amount, 2)
            WHERE invoice_amount IS NOT NULL
        """))

        db.session.commit()

        print("[6/6] verify schema")
        print("contracts columns:", ", ".join(_get_columns("contracts")))
        print("payment_records columns:", ", ".join(_get_columns("payment_records")))
        print("=" * 60)
        print("Migration completed.")
        print("=" * 60)


if __name__ == "__main__":
    migrate()
