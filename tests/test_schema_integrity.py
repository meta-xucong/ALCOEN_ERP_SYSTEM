"""Database schema integrity checks for key business tables."""

from __future__ import annotations

from sqlalchemy import text


def _columns(db_session, table_name: str):
    rows = db_session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def test_contract_related_tables_have_required_columns(db_session):
    """Core contract tables must expose required fields."""
    contract_cols = _columns(db_session, "contracts")
    tx_cols = _columns(db_session, "transactions")
    pay_cols = _columns(db_session, "payment_records")

    assert {"contract_no", "company_name", "delivery_status", "payment_status", "created_by_id"} <= contract_cols
    assert {"contract_id", "contract_product_id", "product_code", "handler", "delivery_date"} <= tx_cols
    assert {"contract_id", "contract_product_id", "payment_amount", "payment_date"} <= pay_cols


def test_transaction_table_has_no_legacy_payment_date_column(db_session):
    """v1.3 split should keep payment date in payment_records, not transactions."""
    tx_cols = _columns(db_session, "transactions")
    assert "payment_date" not in tx_cols
