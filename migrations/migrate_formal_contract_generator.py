#!/usr/bin/env python
"""Create the additive schema used by the formal contract generator."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import inspect, text

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app import create_app, db  # noqa: E402


TABLES = (
    'formal_contract_parties',
    'formal_contracts',
    'formal_contract_items',
    'formal_contract_templates',
    'formal_contract_documents',
    'formal_contract_syncs',
)

FORMAL_CONTRACT_COLUMNS = {
    'department_id': 'INTEGER',
    'party_a_billing_address': 'VARCHAR(255)',
    'party_a_phone': 'VARCHAR(50)',
    'party_a_tax_no': 'VARCHAR(100)',
    'party_a_bank_name': 'VARCHAR(150)',
    'party_a_bank_account': 'VARCHAR(100)',
}

FORMAL_CONTRACT_TEMPLATE_COLUMNS = {
    'department_id': 'INTEGER',
}


def migrate() -> None:
    """Run the app's additive table creation and verify every new table."""
    os.environ.setdefault(
        'DATABASE_URL',
        f"sqlite:///{BASE_DIR / 'data' / 'erp.db'}",
    )
    app = create_app('default')
    with app.app_context():
        with db.engine.begin() as connection:
            existing_columns = {
                column['name']
                for column in inspect(db.engine).get_columns('formal_contracts')
            }
            for column, definition in FORMAL_CONTRACT_COLUMNS.items():
                if column not in existing_columns:
                    connection.execute(
                        text(
                            f'ALTER TABLE formal_contracts '
                            f'ADD COLUMN {column} {definition}'
                        )
                    )
            template_columns = {
                column['name']
                for column in inspect(db.engine).get_columns('formal_contract_templates')
            }
            for column, definition in FORMAL_CONTRACT_TEMPLATE_COLUMNS.items():
                if column not in template_columns:
                    connection.execute(
                        text(
                            f'ALTER TABLE formal_contract_templates '
                            f'ADD COLUMN {column} {definition}'
                        )
                    )
        inspector = inspect(db.engine)
        missing = [table for table in TABLES if not inspector.has_table(table)]
        if missing:
            raise RuntimeError(f'Formal contract tables are missing: {", ".join(missing)}')
        print(f'Formal contract migration complete: {db.engine.url}')
        for table in TABLES:
            columns = [column['name'] for column in inspect(db.engine).get_columns(table)]
            print(f'{table}: {", ".join(columns)}')


if __name__ == '__main__':
    migrate()
