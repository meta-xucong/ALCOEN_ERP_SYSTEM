#!/usr/bin/env python
"""Allow repeated AI CATS work-order batch numbers without deleting data."""

from __future__ import annotations

import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, BASE_DIR)

from app import _ensure_qc_work_order_batch_no_index, create_app, db


def migrate() -> None:
    """Replace the legacy unique batch-number key with a normal lookup index."""
    app = create_app()
    with app.app_context():
        _ensure_qc_work_order_batch_no_index()
        with db.engine.connect() as connection:
            index_rows = connection.exec_driver_sql(
                'PRAGMA index_list(qc_work_orders)'
            ).fetchall()
            for index_row in index_rows:
                if not bool(index_row[2]):
                    continue
                index_name = index_row[1].replace('"', '""')
                columns = connection.exec_driver_sql(
                    f'PRAGMA index_info("{index_name}")'
                ).fetchall()
                if [column_row[2] for column_row in columns] == ['batch_no']:
                    raise RuntimeError('工件订单批次编号唯一索引迁移失败')
        print('[OK] 工件订单批次编号已调整为可重复')


if __name__ == '__main__':
    migrate()
