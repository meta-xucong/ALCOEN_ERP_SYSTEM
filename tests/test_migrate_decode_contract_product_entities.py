"""Regression tests for delivery product model entity cleanup."""

from __future__ import annotations

import sqlite3

from migrations.migrate_decode_contract_product_entities import migrate


def test_migrate_decodes_delivery_product_models_and_is_idempotent(tmp_path):
    """The migration should decode only escaped values and remain safe to rerun."""
    database_path = tmp_path / "erp.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE contract_products (id INTEGER PRIMARY KEY, product_model TEXT);
        CREATE TABLE transactions (id INTEGER PRIMARY KEY, product_model TEXT);
        INSERT INTO contract_products (id, product_model) VALUES
            (1, 'OD1/8&#39;&#39;,20\u03bcm'),
            (2, '4.6*10mm');
        INSERT INTO transactions (id, product_model) VALUES
            (1, 'OD1/8&amp;#39;&amp;#39;,20\u03bcm'),
            (2, '5um');
        """
    )
    connection.commit()
    connection.close()

    assert migrate(database_path) == {"contract_products": 1, "transactions": 1}

    connection = sqlite3.connect(database_path)
    contract_models = connection.execute(
        "SELECT product_model FROM contract_products ORDER BY id"
    ).fetchall()
    transaction_models = connection.execute(
        "SELECT product_model FROM transactions ORDER BY id"
    ).fetchall()
    connection.close()
    assert contract_models == [("OD1/8'',20\u03bcm",), ("4.6*10mm",)]
    assert transaction_models == [("OD1/8'',20\u03bcm",), ("5um",)]

    assert migrate(database_path) == {"contract_products": 0, "transactions": 0}
