import os
from flask import Flask, abort, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from config import config

# 尝试加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"[INFO] 已加载环境变量文件: {env_path}")
except ImportError:
    pass  # python-dotenv 未安装，忽略

db = SQLAlchemy()

VIDEO_CACHE_SECONDS = 7 * 24 * 60 * 60
VIDEO_ASSET_FILENAMES = frozenset({
    'video/video_main.mp4',
    'video/video_login.mp4',
})


class AlcoenFlask(Flask):
    """Serve the shared background videos with a safe, long-lived cache."""

    def get_send_file_max_age(self, filename):
        """Cache only versioned background videos; leave other static files unchanged."""
        normalized_filename = str(filename or '').replace('\\', '/')
        if normalized_filename in VIDEO_ASSET_FILENAMES:
            return VIDEO_CACHE_SECONDS
        return super().get_send_file_max_age(filename)


def _quote_sqlite_identifier(identifier: str) -> str:
    """Quote one SQLite identifier supplied by schema introspection."""
    return '"' + identifier.replace('"', '""') + '"'


def _rebuild_qc_work_orders_without_unique_batch_no(connection) -> None:
    """Rebuild the legacy table only when batch_no is a table-level UNIQUE key."""
    table_name = 'qc_work_orders'
    replacement_name = 'qc_work_orders_batch_no_rebuild'
    columns = connection.exec_driver_sql(f'PRAGMA table_info({table_name})').fetchall()
    foreign_keys = connection.exec_driver_sql(f'PRAGMA foreign_key_list({table_name})').fetchall()
    index_rows = connection.exec_driver_sql(f'PRAGMA index_list({table_name})').fetchall()

    column_names = [row[1] for row in columns]
    column_definitions = []
    for _, column_name, column_type, not_null, default_value, primary_key in columns:
        definition = f'{_quote_sqlite_identifier(column_name)} {column_type or "TEXT"}'
        if not_null:
            definition += ' NOT NULL'
        if default_value is not None:
            definition += f' DEFAULT {default_value}'
        if primary_key:
            definition += ' PRIMARY KEY'
        column_definitions.append(definition)

    foreign_keys_by_id = {}
    for row in foreign_keys:
        foreign_keys_by_id.setdefault(row[0], []).append(row)
    for key_rows in foreign_keys_by_id.values():
        first = key_rows[0]
        source_columns = ', '.join(_quote_sqlite_identifier(row[3]) for row in key_rows)
        target_columns = ', '.join(_quote_sqlite_identifier(row[4]) for row in key_rows)
        foreign_key = (
            f'FOREIGN KEY ({source_columns}) REFERENCES {_quote_sqlite_identifier(first[2])} '
            f'({target_columns})'
        )
        if first[6] and first[6] != 'NO ACTION':
            foreign_key += f' ON DELETE {first[6]}'
        if first[5] and first[5] != 'NO ACTION':
            foreign_key += f' ON UPDATE {first[5]}'
        column_definitions.append(foreign_key)

    preserved_indexes = []
    for index_row in index_rows:
        index_name, is_unique = index_row[1], bool(index_row[2])
        index_columns = [
            column_row[2]
            for column_row in connection.exec_driver_sql(
                f'PRAGMA index_info({_quote_sqlite_identifier(index_name)})'
            ).fetchall()
        ]
        if is_unique and index_columns == ['batch_no']:
            continue
        if not index_name.startswith('sqlite_autoindex'):
            preserved_indexes.append((index_name, is_unique, index_columns))

    quoted_table = _quote_sqlite_identifier(table_name)
    quoted_replacement = _quote_sqlite_identifier(replacement_name)
    quoted_columns = ', '.join(_quote_sqlite_identifier(column_name) for column_name in column_names)
    connection.exec_driver_sql(f'DROP TABLE IF EXISTS {quoted_replacement}')
    connection.exec_driver_sql(
        f'CREATE TABLE {quoted_replacement} ({", ".join(column_definitions)})'
    )
    connection.exec_driver_sql(
        f'INSERT INTO {quoted_replacement} ({quoted_columns}) '
        f'SELECT {quoted_columns} FROM {quoted_table}'
    )
    connection.exec_driver_sql(f'DROP TABLE {quoted_table}')
    connection.exec_driver_sql(f'ALTER TABLE {quoted_replacement} RENAME TO {quoted_table}')

    for index_name, is_unique, index_columns in preserved_indexes:
        quoted_index_columns = ', '.join(_quote_sqlite_identifier(column_name) for column_name in index_columns)
        unique_clause = 'UNIQUE ' if is_unique else ''
        connection.exec_driver_sql(
            f'CREATE {unique_clause}INDEX {_quote_sqlite_identifier(index_name)} '
            f'ON {quoted_table} ({quoted_index_columns})'
        )


def _ensure_qc_work_order_batch_no_index() -> None:
    """Replace legacy unique batch-number indexes without changing order rows."""
    with db.engine.begin() as connection:
        index_rows = connection.exec_driver_sql('PRAGMA index_list(qc_work_orders)').fetchall()
        unique_batch_indexes = []
        for index_row in index_rows:
            index_name, is_unique = index_row[1], bool(index_row[2])
            if not is_unique:
                continue
            index_columns = [
                column_row[2]
                for column_row in connection.exec_driver_sql(
                    f'PRAGMA index_info({_quote_sqlite_identifier(index_name)})'
                ).fetchall()
            ]
            if index_columns == ['batch_no']:
                unique_batch_indexes.append(index_name)

        if any(name.startswith('sqlite_autoindex') for name in unique_batch_indexes):
            connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
            try:
                _rebuild_qc_work_orders_without_unique_batch_no(connection)
            finally:
                connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        else:
            for index_name in unique_batch_indexes:
                connection.exec_driver_sql(f'DROP INDEX IF EXISTS {_quote_sqlite_identifier(index_name)}')

        connection.exec_driver_sql(
            'CREATE INDEX IF NOT EXISTS ix_qc_work_orders_batch_no '
            'ON qc_work_orders (batch_no)'
        )


def _run_lightweight_schema_upgrades():
    """Apply additive QC schema upgrades for SQLite deployments without Alembic."""
    inspector = inspect(db.engine)

    if not inspector.has_table('user_departments'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE user_departments (
                    user_id INTEGER NOT NULL,
                    department_id INTEGER NOT NULL,
                    created_at DATETIME,
                    PRIMARY KEY (user_id, department_id),
                    FOREIGN KEY(user_id) REFERENCES users (id),
                    FOREIGN KEY(department_id) REFERENCES departments (id)
                )
                '''
            )

    if inspector.has_table('users') and inspector.has_table('user_departments'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                INSERT INTO user_departments (user_id, department_id, created_at)
                SELECT users.id, users.department_id, CURRENT_TIMESTAMP
                FROM users
                WHERE users.department_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM user_departments
                      WHERE user_departments.user_id = users.id
                        AND user_departments.department_id = users.department_id
                  )
                '''
            )

    if inspector.has_table('transactions'):
        transaction_columns = {
            column['name'] for column in inspector.get_columns('transactions')
        }
        with db.engine.begin() as connection:
            if 'delivery_batch_no' not in transaction_columns:
                connection.exec_driver_sql(
                    'ALTER TABLE transactions ADD COLUMN delivery_batch_no VARCHAR(100)'
                )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_transactions_delivery_batch_no '
                'ON transactions (delivery_batch_no)'
            )

    if inspector.has_table('qc_work_orders'):
        order_columns = {column['name'] for column in inspector.get_columns('qc_work_orders')}
        alter_statements = []
        if 'workpiece_id' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN workpiece_id INTEGER')
        if 'workpiece_type' not in order_columns:
            alter_statements.append(
                "ALTER TABLE qc_work_orders ADD COLUMN workpiece_type VARCHAR(20) NOT NULL DEFAULT 'self_produced'"
            )
        if 'inventory_posted_at' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN inventory_posted_at DATETIME')
        if 'drawing_note_file_path' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN drawing_note_file_path VARCHAR(500)')
        if 'drawing_note_file_type' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN drawing_note_file_type VARCHAR(50)')
        if 'drawing_note_original_name' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN drawing_note_original_name VARCHAR(255)')
        if 'guide_certificate_file_path' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN guide_certificate_file_path VARCHAR(500)')
        if 'guide_certificate_file_type' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN guide_certificate_file_type VARCHAR(50)')
        if 'guide_certificate_original_name' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN guide_certificate_original_name VARCHAR(255)')
        if 'remark_note_file_path' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN remark_note_file_path VARCHAR(500)')
        if 'remark_note_file_type' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN remark_note_file_type VARCHAR(50)')
        if 'remark_note_original_name' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN remark_note_original_name VARCHAR(255)')
        if alter_statements:
            with db.engine.begin() as connection:
                for statement in alter_statements:
                    connection.exec_driver_sql(statement)

        # Business batch numbers are reusable. This covers both the named
        # unique index made by SQLAlchemy and older table-level UNIQUE keys.
        _ensure_qc_work_order_batch_no_index()

    if inspector.has_table('qc_workpieces'):
        workpiece_columns = {column['name'] for column in inspector.get_columns('qc_workpieces')}
        alter_statements = []
        if 'workpiece_type' not in workpiece_columns:
            alter_statements.append(
                "ALTER TABLE qc_workpieces ADD COLUMN workpiece_type VARCHAR(20) NOT NULL DEFAULT 'self_produced'"
            )
        if 'stock_quantity' not in workpiece_columns:
            alter_statements.append('ALTER TABLE qc_workpieces ADD COLUMN stock_quantity FLOAT NOT NULL DEFAULT 0')
        if alter_statements:
            with db.engine.begin() as connection:
                for statement in alter_statements:
                    connection.exec_driver_sql(statement)

    if not inspector.has_table('qc_workpiece_stock_histories'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE qc_workpiece_stock_histories (
                    id INTEGER NOT NULL,
                    workpiece_id INTEGER NOT NULL,
                    work_order_id INTEGER,
                    acceptance_batch_id INTEGER,
                    assembly_order_id INTEGER,
                    assembly_acceptance_batch_id INTEGER,
                    outbound_order_id INTEGER,
                    outbound_batch_id INTEGER,
                    operator_id INTEGER,
                    change_type VARCHAR(50) NOT NULL DEFAULT 'acceptance_in',
                    batch_no VARCHAR(100),
                    production_quantity FLOAT,
                    accepted_quantity FLOAT,
                    quantity_delta FLOAT NOT NULL DEFAULT 0,
                    stock_before FLOAT NOT NULL DEFAULT 0,
                    stock_after FLOAT NOT NULL DEFAULT 0,
                    note TEXT,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(workpiece_id) REFERENCES qc_workpieces (id) ON DELETE CASCADE,
                    FOREIGN KEY(work_order_id) REFERENCES qc_work_orders (id) ON DELETE SET NULL,
                    FOREIGN KEY(acceptance_batch_id) REFERENCES qc_acceptance_batches (id) ON DELETE SET NULL,
                    FOREIGN KEY(assembly_order_id) REFERENCES assembly_orders (id) ON DELETE SET NULL,
                    FOREIGN KEY(assembly_acceptance_batch_id) REFERENCES assembly_acceptance_batches (id) ON DELETE SET NULL,
                    FOREIGN KEY(outbound_order_id) REFERENCES assembly_outbound_orders (id) ON DELETE SET NULL,
                    FOREIGN KEY(outbound_batch_id) REFERENCES assembly_outbound_batches (id) ON DELETE SET NULL,
                    FOREIGN KEY(operator_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_workpiece_id ON qc_workpiece_stock_histories (workpiece_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_work_order_id ON qc_workpiece_stock_histories (work_order_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_acceptance_batch_id ON qc_workpiece_stock_histories (acceptance_batch_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_operator_id ON qc_workpiece_stock_histories (operator_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_batch_no ON qc_workpiece_stock_histories (batch_no)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_created_at ON qc_workpiece_stock_histories (created_at)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_assembly_order_id ON qc_workpiece_stock_histories (assembly_order_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_assembly_acceptance_batch_id ON qc_workpiece_stock_histories (assembly_acceptance_batch_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_outbound_order_id ON qc_workpiece_stock_histories (outbound_order_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_outbound_batch_id ON qc_workpiece_stock_histories (outbound_batch_id)'
            )
    else:
        stock_history_columns = {column['name'] for column in inspector.get_columns('qc_workpiece_stock_histories')}
        stock_history_alters = []
        for column_name, column_type in (
            ('assembly_order_id', 'INTEGER'),
            ('assembly_acceptance_batch_id', 'INTEGER'),
            ('outbound_order_id', 'INTEGER'),
            ('outbound_batch_id', 'INTEGER'),
        ):
            if column_name not in stock_history_columns:
                stock_history_alters.append(f'ALTER TABLE qc_workpiece_stock_histories ADD COLUMN {column_name} {column_type}')
        if stock_history_alters:
            with db.engine.begin() as connection:
                for statement in stock_history_alters:
                    connection.exec_driver_sql(statement)
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_assembly_order_id ON qc_workpiece_stock_histories (assembly_order_id)')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_assembly_acceptance_batch_id ON qc_workpiece_stock_histories (assembly_acceptance_batch_id)')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_outbound_order_id ON qc_workpiece_stock_histories (outbound_order_id)')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_qc_workpiece_stock_histories_outbound_batch_id ON qc_workpiece_stock_histories (outbound_batch_id)')

    if not inspector.has_table('qc_work_order_histories'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE qc_work_order_histories (
                    id INTEGER NOT NULL,
                    work_order_id INTEGER NOT NULL,
                    operator_id INTEGER,
                    action VARCHAR(100) NOT NULL,
                    detail TEXT,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(work_order_id) REFERENCES qc_work_orders (id) ON DELETE CASCADE,
                    FOREIGN KEY(operator_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_work_order_histories_work_order_id ON qc_work_order_histories (work_order_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_work_order_histories_operator_id ON qc_work_order_histories (operator_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_work_order_histories_created_at ON qc_work_order_histories (created_at)'
            )

    if not inspector.has_table('qc_acceptance_batches'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE qc_acceptance_batches (
                    id INTEGER NOT NULL,
                    work_order_id INTEGER NOT NULL,
                    production_quantity FLOAT NOT NULL DEFAULT 0,
                    accepted_quantity FLOAT NOT NULL DEFAULT 0,
                    completed_at DATETIME,
                    inventory_posted_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(work_order_id) REFERENCES qc_work_orders (id) ON DELETE CASCADE
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_qc_acceptance_batches_work_order_id ON qc_acceptance_batches (work_order_id)'
            )

    if inspector.has_table('qc_acceptance_signatures'):
        signature_columns = {column['name'] for column in inspector.get_columns('qc_acceptance_signatures')}
        alter_statements = []
        if 'acceptance_batch_id' not in signature_columns:
            alter_statements.append('ALTER TABLE qc_acceptance_signatures ADD COLUMN acceptance_batch_id INTEGER')
        if alter_statements:
            with db.engine.begin() as connection:
                for statement in alter_statements:
                    connection.exec_driver_sql(statement)
                connection.exec_driver_sql(
                    'CREATE INDEX IF NOT EXISTS ix_qc_acceptance_signatures_acceptance_batch_id ON qc_acceptance_signatures (acceptance_batch_id)'
                )
        with db.engine.begin() as connection:
            index_rows = connection.exec_driver_sql('PRAGMA index_list(qc_acceptance_signatures)').fetchall()
            has_legacy_unique = False
            for index_row in index_rows:
                index_name = index_row[1]
                is_unique = bool(index_row[2])
                if not is_unique:
                    continue
                columns = [
                    column_row[2]
                    for column_row in connection.exec_driver_sql(f'PRAGMA index_info({index_name})').fetchall()
                ]
                if columns == ['work_order_id', 'signer_role']:
                    has_legacy_unique = True
                    break
            if has_legacy_unique:
                connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
                connection.exec_driver_sql('ALTER TABLE qc_acceptance_signatures RENAME TO qc_acceptance_signatures_legacy')
                connection.exec_driver_sql(
                    '''
                    CREATE TABLE qc_acceptance_signatures (
                        id INTEGER NOT NULL,
                        work_order_id INTEGER NOT NULL,
                        acceptance_batch_id INTEGER,
                        signer_id INTEGER NOT NULL,
                        signer_role VARCHAR(50) NOT NULL,
                        signed_at DATETIME,
                        PRIMARY KEY (id),
                        FOREIGN KEY(work_order_id) REFERENCES qc_work_orders (id) ON DELETE CASCADE,
                        FOREIGN KEY(acceptance_batch_id) REFERENCES qc_acceptance_batches (id) ON DELETE CASCADE,
                        FOREIGN KEY(signer_id) REFERENCES users (id)
                    )
                    '''
                )
                if 'acceptance_batch_id' in signature_columns:
                    connection.exec_driver_sql(
                        '''
                        INSERT INTO qc_acceptance_signatures
                            (id, work_order_id, acceptance_batch_id, signer_id, signer_role, signed_at)
                        SELECT id, work_order_id, acceptance_batch_id, signer_id, signer_role, signed_at
                        FROM qc_acceptance_signatures_legacy
                        '''
                    )
                else:
                    connection.exec_driver_sql(
                        '''
                        INSERT INTO qc_acceptance_signatures
                            (id, work_order_id, acceptance_batch_id, signer_id, signer_role, signed_at)
                        SELECT id, work_order_id, NULL, signer_id, signer_role, signed_at
                        FROM qc_acceptance_signatures_legacy
                        '''
                    )
                connection.exec_driver_sql('DROP TABLE qc_acceptance_signatures_legacy')
                connection.exec_driver_sql(
                    'CREATE INDEX IF NOT EXISTS ix_qc_acceptance_signatures_work_order_id ON qc_acceptance_signatures (work_order_id)'
                )
                connection.exec_driver_sql(
                    'CREATE INDEX IF NOT EXISTS ix_qc_acceptance_signatures_acceptance_batch_id ON qc_acceptance_signatures (acceptance_batch_id)'
                )
                connection.exec_driver_sql('PRAGMA foreign_keys=ON')

    if inspector.has_table('qc_inspection_records'):
        inspection_columns = {column['name'] for column in inspector.get_columns('qc_inspection_records')}
        alter_statements = []
        if 'report_file_path' not in inspection_columns:
            alter_statements.append(
                'ALTER TABLE qc_inspection_records ADD COLUMN report_file_path VARCHAR(500)'
            )
        if 'report_file_type' not in inspection_columns:
            alter_statements.append(
                'ALTER TABLE qc_inspection_records ADD COLUMN report_file_type VARCHAR(50)'
            )
        if 'report_original_name' not in inspection_columns:
            alter_statements.append(
                'ALTER TABLE qc_inspection_records ADD COLUMN report_original_name VARCHAR(255)'
            )
        if alter_statements:
            with db.engine.begin() as connection:
                for statement in alter_statements:
                    connection.exec_driver_sql(statement)

    if not inspector.has_table('research_projects'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE research_projects (
                    id INTEGER NOT NULL,
                    project_code VARCHAR(100) NOT NULL,
                    project_name VARCHAR(200) NOT NULL,
                    project_category VARCHAR(50),
                    research_direction VARCHAR(200),
                    creator_id INTEGER NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    UNIQUE (project_code),
                    FOREIGN KEY(creator_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_projects_project_code ON research_projects (project_code)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_projects_project_name ON research_projects (project_name)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_projects_project_category ON research_projects (project_category)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_projects_creator_id ON research_projects (creator_id)'
            )

    if not inspector.has_table('research_project_attachments'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE research_project_attachments (
                    id INTEGER NOT NULL,
                    project_id INTEGER NOT NULL,
                    attach_type VARCHAR(50) NOT NULL,
                    title VARCHAR(255),
                    content TEXT,
                    file_path VARCHAR(500) NOT NULL,
                    file_type VARCHAR(50),
                    is_required BOOLEAN,
                    sort_order INTEGER,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(project_id) REFERENCES research_projects (id) ON DELETE CASCADE
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_project_attachments_project_id ON research_project_attachments (project_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_project_attachments_attach_type ON research_project_attachments (attach_type)'
            )

    if not inspector.has_table('research_batches'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE research_batches (
                    id INTEGER NOT NULL,
                    batch_no VARCHAR(100) NOT NULL,
                    project_id INTEGER,
                    project_name_snapshot VARCHAR(200) NOT NULL,
                    sample_quantity FLOAT NOT NULL DEFAULT 0,
                    researcher_id INTEGER NOT NULL,
                    reviewer_id INTEGER,
                    status VARCHAR(50) NOT NULL DEFAULT 'draft',
                    research_submitted_at DATETIME,
                    review_completed_at DATETIME,
                    accepted_at DATETIME,
                    returned_at DATETIME,
                    return_reason TEXT,
                    initiation_note_file_path VARCHAR(500),
                    initiation_note_file_type VARCHAR(50),
                    initiation_note_original_name VARCHAR(255),
                    phase_result_file_path VARCHAR(500),
                    phase_result_file_type VARCHAR(50),
                    phase_result_original_name VARCHAR(255),
                    supplementary_note_file_path VARCHAR(500),
                    supplementary_note_file_type VARCHAR(50),
                    supplementary_note_original_name VARCHAR(255),
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    UNIQUE (batch_no),
                    FOREIGN KEY(project_id) REFERENCES research_projects (id) ON DELETE SET NULL,
                    FOREIGN KEY(researcher_id) REFERENCES users (id),
                    FOREIGN KEY(reviewer_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batches_batch_no ON research_batches (batch_no)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batches_project_id ON research_batches (project_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batches_status ON research_batches (status)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batches_researcher_id ON research_batches (researcher_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batches_reviewer_id ON research_batches (reviewer_id)'
            )

    if not inspector.has_table('research_batch_attachments'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE research_batch_attachments (
                    id INTEGER NOT NULL,
                    batch_id INTEGER NOT NULL,
                    attach_type VARCHAR(50) NOT NULL,
                    source_type VARCHAR(30) NOT NULL DEFAULT 'project_snapshot',
                    title VARCHAR(255),
                    content TEXT,
                    file_path VARCHAR(500) NOT NULL,
                    file_type VARCHAR(50),
                    is_required BOOLEAN,
                    sort_order INTEGER,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(batch_id) REFERENCES research_batches (id) ON DELETE CASCADE
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batch_attachments_batch_id ON research_batch_attachments (batch_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batch_attachments_attach_type ON research_batch_attachments (attach_type)'
            )

    if not inspector.has_table('research_review_records'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE research_review_records (
                    id INTEGER NOT NULL,
                    batch_id INTEGER NOT NULL,
                    reviewer_id INTEGER NOT NULL,
                    attachment_id INTEGER NOT NULL,
                    result VARCHAR(20) NOT NULL DEFAULT 'draft',
                    suggestion TEXT,
                    feedback_file_path VARCHAR(500),
                    feedback_file_type VARCHAR(50),
                    feedback_original_name VARCHAR(255),
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(batch_id) REFERENCES research_batches (id) ON DELETE CASCADE,
                    FOREIGN KEY(reviewer_id) REFERENCES users (id),
                    FOREIGN KEY(attachment_id) REFERENCES research_batch_attachments (id) ON DELETE CASCADE
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_review_records_batch_id ON research_review_records (batch_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_review_records_attachment_id ON research_review_records (attachment_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_review_records_reviewer_id ON research_review_records (reviewer_id)'
            )

    if not inspector.has_table('research_acceptance_signatures'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE research_acceptance_signatures (
                    id INTEGER NOT NULL,
                    batch_id INTEGER NOT NULL,
                    signer_id INTEGER NOT NULL,
                    signer_role VARCHAR(50) NOT NULL,
                    signed_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(batch_id) REFERENCES research_batches (id) ON DELETE CASCADE,
                    FOREIGN KEY(signer_id) REFERENCES users (id),
                    UNIQUE (batch_id, signer_role)
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_acceptance_signatures_batch_id ON research_acceptance_signatures (batch_id)'
            )

    if not inspector.has_table('research_batch_histories'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE research_batch_histories (
                    id INTEGER NOT NULL,
                    batch_id INTEGER NOT NULL,
                    operator_id INTEGER,
                    action VARCHAR(100) NOT NULL,
                    detail TEXT,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(batch_id) REFERENCES research_batches (id) ON DELETE CASCADE,
                    FOREIGN KEY(operator_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batch_histories_batch_id ON research_batch_histories (batch_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batch_histories_operator_id ON research_batch_histories (operator_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_research_batch_histories_created_at ON research_batch_histories (created_at)'
            )

    if not inspector.has_table('assembly_products'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_products (
                    id INTEGER NOT NULL,
                    product_code VARCHAR(100) NOT NULL,
                    product_name VARCHAR(200) NOT NULL,
                    creator_id INTEGER NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    UNIQUE (product_code),
                    FOREIGN KEY(creator_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_products_product_code ON assembly_products (product_code)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_products_product_name ON assembly_products (product_name)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_products_creator_id ON assembly_products (creator_id)'
            )

    if inspector.has_table('assembly_products'):
        product_columns = {column['name'] for column in inspector.get_columns('assembly_products')}
        alter_statements = []
        if 'product_level' not in product_columns:
            alter_statements.append('ALTER TABLE assembly_products ADD COLUMN product_level INTEGER NOT NULL DEFAULT 1')
        if 'stock_quantity' not in product_columns:
            alter_statements.append('ALTER TABLE assembly_products ADD COLUMN stock_quantity FLOAT NOT NULL DEFAULT 0')
        if alter_statements:
            with db.engine.begin() as connection:
                for statement in alter_statements:
                    connection.exec_driver_sql(statement)

    if not inspector.has_table('assembly_product_components'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_product_components (
                    id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    workpiece_id INTEGER NOT NULL,
                    workpiece_code_snapshot VARCHAR(100) NOT NULL,
                    workpiece_name_snapshot VARCHAR(200) NOT NULL,
                    quantity_per_unit FLOAT NOT NULL DEFAULT 1,
                    sort_order INTEGER,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(product_id) REFERENCES assembly_products (id) ON DELETE CASCADE,
                    FOREIGN KEY(workpiece_id) REFERENCES qc_workpieces (id) ON DELETE RESTRICT
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_product_components_product_id ON assembly_product_components (product_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_product_components_workpiece_id ON assembly_product_components (workpiece_id)'
            )

    if inspector.has_table('assembly_product_components'):
        with db.engine.begin() as connection:
            component_columns = {row[1]: row for row in connection.exec_driver_sql('PRAGMA table_info(assembly_product_components)').fetchall()}
            needs_rebuild = (
                'component_type' not in component_columns
                or 'component_product_id' not in component_columns
                or bool(component_columns.get('workpiece_id') and component_columns['workpiece_id'][3])
            )
            if needs_rebuild:
                connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
                connection.exec_driver_sql('ALTER TABLE assembly_product_components RENAME TO assembly_product_components_legacy')
                connection.exec_driver_sql(
                    '''
                    CREATE TABLE assembly_product_components (
                        id INTEGER NOT NULL,
                        product_id INTEGER NOT NULL,
                        component_type VARCHAR(20) NOT NULL DEFAULT 'workpiece',
                        workpiece_id INTEGER,
                        component_product_id INTEGER,
                        workpiece_code_snapshot VARCHAR(100) NOT NULL,
                        workpiece_name_snapshot VARCHAR(200) NOT NULL,
                        quantity_per_unit FLOAT NOT NULL DEFAULT 1,
                        sort_order INTEGER,
                        created_at DATETIME,
                        PRIMARY KEY (id),
                        FOREIGN KEY(product_id) REFERENCES assembly_products (id) ON DELETE CASCADE,
                        FOREIGN KEY(workpiece_id) REFERENCES qc_workpieces (id) ON DELETE RESTRICT,
                        FOREIGN KEY(component_product_id) REFERENCES assembly_products (id) ON DELETE RESTRICT
                    )
                    '''
                )
                legacy_columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(assembly_product_components_legacy)').fetchall()}
                if 'component_type' in legacy_columns:
                    connection.exec_driver_sql(
                        '''
                        INSERT INTO assembly_product_components
                            (id, product_id, component_type, workpiece_id, component_product_id, workpiece_code_snapshot, workpiece_name_snapshot, quantity_per_unit, sort_order, created_at)
                        SELECT id, product_id, COALESCE(component_type, 'workpiece'), workpiece_id, component_product_id, workpiece_code_snapshot, workpiece_name_snapshot, quantity_per_unit, sort_order, created_at
                        FROM assembly_product_components_legacy
                        '''
                    )
                else:
                    connection.exec_driver_sql(
                        '''
                        INSERT INTO assembly_product_components
                            (id, product_id, component_type, workpiece_id, component_product_id, workpiece_code_snapshot, workpiece_name_snapshot, quantity_per_unit, sort_order, created_at)
                        SELECT id, product_id, 'workpiece', workpiece_id, NULL, workpiece_code_snapshot, workpiece_name_snapshot, quantity_per_unit, sort_order, created_at
                        FROM assembly_product_components_legacy
                        '''
                    )
                connection.exec_driver_sql('DROP TABLE assembly_product_components_legacy')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_components_product_id ON assembly_product_components (product_id)')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_components_component_type ON assembly_product_components (component_type)')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_components_workpiece_id ON assembly_product_components (workpiece_id)')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_components_component_product_id ON assembly_product_components (component_product_id)')
                connection.exec_driver_sql('PRAGMA foreign_keys=ON')

    if not inspector.has_table('assembly_product_attachments'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_product_attachments (
                    id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    attach_type VARCHAR(50) NOT NULL,
                    title VARCHAR(255),
                    content TEXT,
                    file_path VARCHAR(500) NOT NULL,
                    file_type VARCHAR(50),
                    is_required BOOLEAN,
                    sort_order INTEGER,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(product_id) REFERENCES assembly_products (id) ON DELETE CASCADE
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_product_attachments_product_id ON assembly_product_attachments (product_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_product_attachments_attach_type ON assembly_product_attachments (attach_type)'
            )

    if not inspector.has_table('assembly_product_stock_histories'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_product_stock_histories (
                    id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    assembly_order_id INTEGER,
                    assembly_acceptance_batch_id INTEGER,
                    outbound_order_id INTEGER,
                    outbound_batch_id INTEGER,
                    operator_id INTEGER,
                    change_type VARCHAR(50) NOT NULL DEFAULT 'acceptance_in',
                    batch_no VARCHAR(100),
                    production_quantity FLOAT,
                    accepted_quantity FLOAT,
                    quantity_delta FLOAT NOT NULL DEFAULT 0,
                    stock_before FLOAT NOT NULL DEFAULT 0,
                    stock_after FLOAT NOT NULL DEFAULT 0,
                    note TEXT,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(product_id) REFERENCES assembly_products (id) ON DELETE CASCADE,
                    FOREIGN KEY(assembly_order_id) REFERENCES assembly_orders (id) ON DELETE SET NULL,
                    FOREIGN KEY(assembly_acceptance_batch_id) REFERENCES assembly_acceptance_batches (id) ON DELETE SET NULL,
                    FOREIGN KEY(outbound_order_id) REFERENCES assembly_outbound_orders (id) ON DELETE SET NULL,
                    FOREIGN KEY(outbound_batch_id) REFERENCES assembly_outbound_batches (id) ON DELETE SET NULL,
                    FOREIGN KEY(operator_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_stock_histories_product_id ON assembly_product_stock_histories (product_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_stock_histories_assembly_order_id ON assembly_product_stock_histories (assembly_order_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_stock_histories_assembly_acceptance_batch_id ON assembly_product_stock_histories (assembly_acceptance_batch_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_stock_histories_outbound_order_id ON assembly_product_stock_histories (outbound_order_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_stock_histories_outbound_batch_id ON assembly_product_stock_histories (outbound_batch_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_stock_histories_operator_id ON assembly_product_stock_histories (operator_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_stock_histories_batch_no ON assembly_product_stock_histories (batch_no)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_product_stock_histories_created_at ON assembly_product_stock_histories (created_at)')

    if inspector.has_table('assembly_outbound_batches'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                INSERT INTO assembly_product_stock_histories (
                    product_id, outbound_order_id, outbound_batch_id, operator_id,
                    change_type, batch_no, production_quantity, accepted_quantity,
                    quantity_delta, stock_before, stock_after, note, created_at
                )
                SELECT
                    o.product_id, o.id, b.id, o.initiator_id,
                    'outbound_out', o.outbound_no, b.outbound_quantity, b.outbound_quantity,
                    -b.outbound_quantity,
                    COALESCE(p.stock_quantity, 0) + COALESCE(b.outbound_quantity, 0),
                    COALESCE(p.stock_quantity, 0),
                    '历史补录：出厂批次已完成，补充产品库出库流水',
                    COALESCE(b.inventory_posted_at, b.completed_at, CURRENT_TIMESTAMP)
                FROM assembly_outbound_orders o
                JOIN assembly_outbound_batches b ON b.order_id = o.id
                JOIN assembly_products p ON p.id = o.product_id
                WHERE o.item_type = 'product'
                  AND b.completed_at IS NOT NULL
                  AND b.inventory_posted_at IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM assembly_product_stock_histories h
                      WHERE h.product_id = o.product_id
                        AND h.outbound_order_id = o.id
                        AND h.outbound_batch_id = b.id
                        AND h.change_type = 'outbound_out'
                  )
                '''
            )
            connection.exec_driver_sql(
                '''
                INSERT INTO qc_workpiece_stock_histories (
                    workpiece_id, outbound_order_id, outbound_batch_id, operator_id,
                    change_type, batch_no, production_quantity, accepted_quantity,
                    quantity_delta, stock_before, stock_after, note, created_at
                )
                SELECT
                    o.workpiece_id, o.id, b.id, o.initiator_id,
                    'outbound_out', o.outbound_no, b.outbound_quantity, b.outbound_quantity,
                    -b.outbound_quantity,
                    COALESCE(w.stock_quantity, 0) + COALESCE(b.outbound_quantity, 0),
                    COALESCE(w.stock_quantity, 0),
                    '历史补录：出厂批次已完成，补充工件库出库流水',
                    COALESCE(b.inventory_posted_at, b.completed_at, CURRENT_TIMESTAMP)
                FROM assembly_outbound_orders o
                JOIN assembly_outbound_batches b ON b.order_id = o.id
                JOIN qc_workpieces w ON w.id = o.workpiece_id
                WHERE o.item_type = 'workpiece'
                  AND b.completed_at IS NOT NULL
                  AND b.inventory_posted_at IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM qc_workpiece_stock_histories h
                      WHERE h.workpiece_id = o.workpiece_id
                        AND h.outbound_order_id = o.id
                        AND h.outbound_batch_id = b.id
                        AND h.change_type = 'outbound_out'
                  )
                '''
            )

    if inspector.has_table('assembly_order_components'):
        with db.engine.begin() as connection:
            order_component_columns = {
                row[1] for row in connection.exec_driver_sql('PRAGMA table_info(assembly_order_components)').fetchall()
            }
            alter_statements = []
            if 'component_type' not in order_component_columns:
                alter_statements.append("ALTER TABLE assembly_order_components ADD COLUMN component_type VARCHAR(20) NOT NULL DEFAULT 'workpiece'")
            if 'component_product_id' not in order_component_columns:
                alter_statements.append('ALTER TABLE assembly_order_components ADD COLUMN component_product_id INTEGER')
            for statement in alter_statements:
                connection.exec_driver_sql(statement)
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_order_components_component_type ON assembly_order_components (component_type)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_order_components_component_product_id ON assembly_order_components (component_product_id)')

    if inspector.has_table('assembly_acceptance_batches'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                INSERT INTO assembly_product_stock_histories (
                    product_id, assembly_order_id, assembly_acceptance_batch_id, operator_id,
                    change_type, batch_no, production_quantity, accepted_quantity,
                    quantity_delta, stock_before, stock_after, note, created_at
                )
                SELECT
                    o.product_id, o.id, b.id, o.controller_id,
                    'acceptance_in', o.batch_no, b.production_quantity, b.accepted_quantity,
                    b.accepted_quantity,
                    MAX(COALESCE(p.stock_quantity, 0) - COALESCE(b.accepted_quantity, 0), 0),
                    COALESCE(p.stock_quantity, 0),
                    '历史补录：装配验收已完成，补充产品库入库流水',
                    COALESCE(b.inventory_posted_at, b.completed_at, CURRENT_TIMESTAMP)
                FROM assembly_orders o
                JOIN assembly_acceptance_batches b ON b.order_id = o.id
                JOIN assembly_products p ON p.id = o.product_id
                WHERE b.completed_at IS NOT NULL
                  AND b.inventory_posted_at IS NOT NULL
                  AND o.product_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM assembly_product_stock_histories h
                      WHERE h.product_id = o.product_id
                        AND h.assembly_order_id = o.id
                        AND h.assembly_acceptance_batch_id = b.id
                        AND h.change_type = 'acceptance_in'
                  )
                '''
            )
            connection.exec_driver_sql(
                '''
                INSERT INTO qc_workpiece_stock_histories (
                    workpiece_id, assembly_order_id, assembly_acceptance_batch_id, operator_id,
                    change_type, batch_no, production_quantity, accepted_quantity,
                    quantity_delta, stock_before, stock_after, note, created_at
                )
                SELECT
                    c.workpiece_id, o.id, b.id, o.controller_id,
                    'assembly_consumption', o.batch_no, b.production_quantity, b.accepted_quantity,
                    -(COALESCE(c.quantity_per_unit, 0) * COALESCE(b.accepted_quantity, 0)),
                    COALESCE(w.stock_quantity, 0) + (COALESCE(c.quantity_per_unit, 0) * COALESCE(b.accepted_quantity, 0)),
                    COALESCE(w.stock_quantity, 0),
                    '历史补录：装配验收已完成，补充工件库组件扣减流水',
                    COALESCE(b.inventory_posted_at, b.completed_at, CURRENT_TIMESTAMP)
                FROM assembly_orders o
                JOIN assembly_acceptance_batches b ON b.order_id = o.id
                JOIN assembly_order_components c ON c.order_id = o.id
                JOIN qc_workpieces w ON w.id = c.workpiece_id
                WHERE b.completed_at IS NOT NULL
                  AND b.inventory_posted_at IS NOT NULL
                  AND COALESCE(c.component_type, 'workpiece') = 'workpiece'
                  AND c.workpiece_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM qc_workpiece_stock_histories h
                      WHERE h.workpiece_id = c.workpiece_id
                        AND h.assembly_order_id = o.id
                        AND h.assembly_acceptance_batch_id = b.id
                        AND h.change_type = 'assembly_consumption'
                  )
                '''
            )
            connection.exec_driver_sql(
                '''
                INSERT INTO assembly_product_stock_histories (
                    product_id, assembly_order_id, assembly_acceptance_batch_id, operator_id,
                    change_type, batch_no, production_quantity, accepted_quantity,
                    quantity_delta, stock_before, stock_after, note, created_at
                )
                SELECT
                    c.component_product_id, o.id, b.id, o.controller_id,
                    'assembly_consumption', o.batch_no, b.production_quantity, b.accepted_quantity,
                    -(COALESCE(c.quantity_per_unit, 0) * COALESCE(b.accepted_quantity, 0)),
                    COALESCE(p.stock_quantity, 0) + (COALESCE(c.quantity_per_unit, 0) * COALESCE(b.accepted_quantity, 0)),
                    COALESCE(p.stock_quantity, 0),
                    '历史补录：装配验收已完成，补充产品库组件扣减流水',
                    COALESCE(b.inventory_posted_at, b.completed_at, CURRENT_TIMESTAMP)
                FROM assembly_orders o
                JOIN assembly_acceptance_batches b ON b.order_id = o.id
                JOIN assembly_order_components c ON c.order_id = o.id
                JOIN assembly_products p ON p.id = c.component_product_id
                WHERE b.completed_at IS NOT NULL
                  AND b.inventory_posted_at IS NOT NULL
                  AND c.component_type = 'product'
                  AND c.component_product_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM assembly_product_stock_histories h
                      WHERE h.product_id = c.component_product_id
                        AND h.assembly_order_id = o.id
                        AND h.assembly_acceptance_batch_id = b.id
                        AND h.change_type = 'assembly_consumption'
                  )
                '''
            )

    if not inspector.has_table('assembly_orders'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_orders (
                    id INTEGER NOT NULL,
                    batch_no VARCHAR(100) NOT NULL,
                    product_id INTEGER,
                    product_name_snapshot VARCHAR(200) NOT NULL,
                    quantity FLOAT NOT NULL DEFAULT 0,
                    controller_id INTEGER NOT NULL,
                    inspector_id INTEGER,
                    status VARCHAR(50) NOT NULL DEFAULT 'draft',
                    assembly_submitted_at DATETIME,
                    inspection_completed_at DATETIME,
                    accepted_at DATETIME,
                    inventory_posted_at DATETIME,
                    rejected_at DATETIME,
                    rejection_reason TEXT,
                    registration_note_file_path VARCHAR(500),
                    registration_note_file_type VARCHAR(50),
                    registration_note_original_name VARCHAR(255),
                    certificate_note_file_path VARCHAR(500),
                    certificate_note_file_type VARCHAR(50),
                    certificate_note_original_name VARCHAR(255),
                    remark_note_file_path VARCHAR(500),
                    remark_note_file_type VARCHAR(50),
                    remark_note_original_name VARCHAR(255),
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    UNIQUE (batch_no),
                    FOREIGN KEY(product_id) REFERENCES assembly_products (id) ON DELETE SET NULL,
                    FOREIGN KEY(controller_id) REFERENCES users (id),
                    FOREIGN KEY(inspector_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_orders_batch_no ON assembly_orders (batch_no)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_orders_product_id ON assembly_orders (product_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_orders_status ON assembly_orders (status)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_orders_controller_id ON assembly_orders (controller_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_orders_inspector_id ON assembly_orders (inspector_id)'
            )

    if not inspector.has_table('assembly_order_components'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_order_components (
                    id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL,
                    workpiece_id INTEGER,
                    workpiece_code_snapshot VARCHAR(100) NOT NULL,
                    workpiece_name_snapshot VARCHAR(200) NOT NULL,
                    quantity_per_unit FLOAT NOT NULL DEFAULT 1,
                    total_required_quantity FLOAT NOT NULL DEFAULT 0,
                    sort_order INTEGER,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(order_id) REFERENCES assembly_orders (id) ON DELETE CASCADE,
                    FOREIGN KEY(workpiece_id) REFERENCES qc_workpieces (id) ON DELETE SET NULL
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_order_components_order_id ON assembly_order_components (order_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_order_components_workpiece_id ON assembly_order_components (workpiece_id)'
            )

    if inspector.has_table('assembly_order_components'):
        alter_statements = []
        with db.engine.begin() as connection:
            order_component_columns = {
                row[1] for row in connection.exec_driver_sql('PRAGMA table_info(assembly_order_components)').fetchall()
            }
            if 'component_type' not in order_component_columns:
                alter_statements.append("ALTER TABLE assembly_order_components ADD COLUMN component_type VARCHAR(20) NOT NULL DEFAULT 'workpiece'")
            if 'component_product_id' not in order_component_columns:
                alter_statements.append('ALTER TABLE assembly_order_components ADD COLUMN component_product_id INTEGER')
            if alter_statements:
                for statement in alter_statements:
                    connection.exec_driver_sql(statement)
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_order_components_component_type ON assembly_order_components (component_type)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_order_components_component_product_id ON assembly_order_components (component_product_id)')

    if not inspector.has_table('assembly_order_attachments'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_order_attachments (
                    id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL,
                    attach_type VARCHAR(50) NOT NULL,
                    source_type VARCHAR(30) NOT NULL DEFAULT 'product_snapshot',
                    title VARCHAR(255),
                    content TEXT,
                    file_path VARCHAR(500) NOT NULL,
                    file_type VARCHAR(50),
                    is_required BOOLEAN,
                    sort_order INTEGER,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(order_id) REFERENCES assembly_orders (id) ON DELETE CASCADE
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_order_attachments_order_id ON assembly_order_attachments (order_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_order_attachments_attach_type ON assembly_order_attachments (attach_type)'
            )

    if not inspector.has_table('assembly_inspection_records'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_inspection_records (
                    id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL,
                    inspector_id INTEGER NOT NULL,
                    attachment_id INTEGER NOT NULL,
                    result VARCHAR(20) NOT NULL DEFAULT 'draft',
                    remark TEXT,
                    report_file_path VARCHAR(500),
                    report_file_type VARCHAR(50),
                    report_original_name VARCHAR(255),
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(order_id) REFERENCES assembly_orders (id) ON DELETE CASCADE,
                    FOREIGN KEY(inspector_id) REFERENCES users (id),
                    FOREIGN KEY(attachment_id) REFERENCES assembly_order_attachments (id) ON DELETE CASCADE
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_inspection_records_order_id ON assembly_inspection_records (order_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_inspection_records_attachment_id ON assembly_inspection_records (attachment_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_inspection_records_inspector_id ON assembly_inspection_records (inspector_id)'
            )

    if not inspector.has_table('assembly_acceptance_batches'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_acceptance_batches (
                    id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL,
                    production_quantity FLOAT NOT NULL DEFAULT 0,
                    accepted_quantity FLOAT NOT NULL DEFAULT 0,
                    completed_at DATETIME,
                    inventory_posted_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(order_id) REFERENCES assembly_orders (id) ON DELETE CASCADE
                )
                '''
            )
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_acceptance_batches_order_id ON assembly_acceptance_batches (order_id)')

    if not inspector.has_table('assembly_acceptance_signatures'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_acceptance_signatures (
                    id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL,
                    acceptance_batch_id INTEGER,
                    signer_id INTEGER NOT NULL,
                    signer_role VARCHAR(50) NOT NULL,
                    signed_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(order_id) REFERENCES assembly_orders (id) ON DELETE CASCADE,
                    FOREIGN KEY(acceptance_batch_id) REFERENCES assembly_acceptance_batches (id) ON DELETE CASCADE,
                    FOREIGN KEY(signer_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_acceptance_signatures_order_id ON assembly_acceptance_signatures (order_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_acceptance_signatures_acceptance_batch_id ON assembly_acceptance_signatures (acceptance_batch_id)')

    if inspector.has_table('assembly_acceptance_signatures'):
        with db.engine.begin() as connection:
            signature_columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(assembly_acceptance_signatures)').fetchall()}
            index_rows = connection.exec_driver_sql('PRAGMA index_list(assembly_acceptance_signatures)').fetchall()
            has_legacy_unique = False
            for index_row in index_rows:
                index_name = index_row[1]
                is_unique = bool(index_row[2])
                if not is_unique:
                    continue
                columns = [column_row[2] for column_row in connection.exec_driver_sql(f'PRAGMA index_info({index_name})').fetchall()]
                if columns == ['order_id', 'signer_role']:
                    has_legacy_unique = True
                    break
            if 'acceptance_batch_id' not in signature_columns or has_legacy_unique:
                connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
                connection.exec_driver_sql('ALTER TABLE assembly_acceptance_signatures RENAME TO assembly_acceptance_signatures_legacy')
                connection.exec_driver_sql(
                    '''
                    CREATE TABLE assembly_acceptance_signatures (
                        id INTEGER NOT NULL,
                        order_id INTEGER NOT NULL,
                        acceptance_batch_id INTEGER,
                        signer_id INTEGER NOT NULL,
                        signer_role VARCHAR(50) NOT NULL,
                        signed_at DATETIME,
                        PRIMARY KEY (id),
                        FOREIGN KEY(order_id) REFERENCES assembly_orders (id) ON DELETE CASCADE,
                        FOREIGN KEY(acceptance_batch_id) REFERENCES assembly_acceptance_batches (id) ON DELETE CASCADE,
                        FOREIGN KEY(signer_id) REFERENCES users (id)
                    )
                    '''
                )
                if 'acceptance_batch_id' in signature_columns:
                    connection.exec_driver_sql(
                        '''
                        INSERT INTO assembly_acceptance_signatures
                            (id, order_id, acceptance_batch_id, signer_id, signer_role, signed_at)
                        SELECT id, order_id, acceptance_batch_id, signer_id, signer_role, signed_at
                        FROM assembly_acceptance_signatures_legacy
                        '''
                    )
                else:
                    connection.exec_driver_sql(
                        '''
                        INSERT INTO assembly_acceptance_signatures
                            (id, order_id, acceptance_batch_id, signer_id, signer_role, signed_at)
                        SELECT id, order_id, NULL, signer_id, signer_role, signed_at
                        FROM assembly_acceptance_signatures_legacy
                        '''
                    )
                connection.exec_driver_sql('DROP TABLE assembly_acceptance_signatures_legacy')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_acceptance_signatures_order_id ON assembly_acceptance_signatures (order_id)')
                connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_acceptance_signatures_acceptance_batch_id ON assembly_acceptance_signatures (acceptance_batch_id)')
                connection.exec_driver_sql('PRAGMA foreign_keys=ON')

    if not inspector.has_table('assembly_order_histories'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_order_histories (
                    id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL,
                    operator_id INTEGER,
                    action VARCHAR(100) NOT NULL,
                    detail TEXT,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(order_id) REFERENCES assembly_orders (id) ON DELETE CASCADE,
                    FOREIGN KEY(operator_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_order_histories_order_id ON assembly_order_histories (order_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_order_histories_operator_id ON assembly_order_histories (operator_id)'
            )
            connection.exec_driver_sql(
                'CREATE INDEX IF NOT EXISTS ix_assembly_order_histories_created_at ON assembly_order_histories (created_at)'
            )

    if not inspector.has_table('assembly_outbound_orders'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_outbound_orders (
                    id INTEGER NOT NULL,
                    outbound_no VARCHAR(100) NOT NULL,
                    item_type VARCHAR(20) NOT NULL DEFAULT 'workpiece',
                    workpiece_id INTEGER,
                    product_id INTEGER,
                    item_code_snapshot VARCHAR(100) NOT NULL,
                    item_name_snapshot VARCHAR(200) NOT NULL,
                    planned_quantity FLOAT NOT NULL DEFAULT 0,
                    outbound_date DATE,
                    initiator_id INTEGER NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'confirming',
                    completed_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    UNIQUE (outbound_no),
                    FOREIGN KEY(workpiece_id) REFERENCES qc_workpieces (id) ON DELETE SET NULL,
                    FOREIGN KEY(product_id) REFERENCES assembly_products (id) ON DELETE SET NULL,
                    FOREIGN KEY(initiator_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_orders_outbound_no ON assembly_outbound_orders (outbound_no)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_orders_item_type ON assembly_outbound_orders (item_type)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_orders_workpiece_id ON assembly_outbound_orders (workpiece_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_orders_product_id ON assembly_outbound_orders (product_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_orders_initiator_id ON assembly_outbound_orders (initiator_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_orders_status ON assembly_outbound_orders (status)')

    if not inspector.has_table('assembly_outbound_batches'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_outbound_batches (
                    id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL,
                    outbound_quantity FLOAT NOT NULL DEFAULT 0,
                    completed_at DATETIME,
                    inventory_posted_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(order_id) REFERENCES assembly_outbound_orders (id) ON DELETE CASCADE
                )
                '''
            )
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_batches_order_id ON assembly_outbound_batches (order_id)')

    if not inspector.has_table('assembly_outbound_signatures'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_outbound_signatures (
                    id INTEGER NOT NULL,
                    outbound_order_id INTEGER NOT NULL,
                    outbound_batch_id INTEGER NOT NULL,
                    signer_id INTEGER NOT NULL,
                    signer_role VARCHAR(50) NOT NULL,
                    signed_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(outbound_order_id) REFERENCES assembly_outbound_orders (id) ON DELETE CASCADE,
                    FOREIGN KEY(outbound_batch_id) REFERENCES assembly_outbound_batches (id) ON DELETE CASCADE,
                    FOREIGN KEY(signer_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_signatures_outbound_order_id ON assembly_outbound_signatures (outbound_order_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_signatures_outbound_batch_id ON assembly_outbound_signatures (outbound_batch_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_signatures_signer_id ON assembly_outbound_signatures (signer_id)')

    if not inspector.has_table('assembly_outbound_histories'):
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                '''
                CREATE TABLE assembly_outbound_histories (
                    id INTEGER NOT NULL,
                    outbound_order_id INTEGER NOT NULL,
                    operator_id INTEGER,
                    action VARCHAR(100) NOT NULL,
                    detail TEXT,
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(outbound_order_id) REFERENCES assembly_outbound_orders (id) ON DELETE CASCADE,
                    FOREIGN KEY(operator_id) REFERENCES users (id)
                )
                '''
            )
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_histories_outbound_order_id ON assembly_outbound_histories (outbound_order_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_histories_operator_id ON assembly_outbound_histories (operator_id)')
            connection.exec_driver_sql('CREATE INDEX IF NOT EXISTS ix_assembly_outbound_histories_created_at ON assembly_outbound_histories (created_at)')


    # Formal-contract generator additions. These columns are intentionally
    # nullable so existing contracts keep their global-template fallback.
    if inspector.has_table('formal_contracts'):
        formal_contract_columns = {
            column['name']
            for column in inspector.get_columns('formal_contracts')
        }
        if 'department_id' not in formal_contract_columns:
            with db.engine.begin() as connection:
                connection.exec_driver_sql(
                    'ALTER TABLE formal_contracts ADD COLUMN department_id INTEGER'
                )
                connection.exec_driver_sql(
                    'CREATE INDEX IF NOT EXISTS ix_formal_contracts_department_id '
                    'ON formal_contracts (department_id)'
                )

    if inspector.has_table('formal_contract_templates'):
        template_columns = {
            column['name']
            for column in inspector.get_columns('formal_contract_templates')
        }
        if 'department_id' not in template_columns:
            with db.engine.begin() as connection:
                connection.exec_driver_sql(
                    'ALTER TABLE formal_contract_templates ADD COLUMN department_id INTEGER'
                )
                connection.exec_driver_sql(
                    'CREATE INDEX IF NOT EXISTS ix_formal_contract_templates_department_id '
                    'ON formal_contract_templates (department_id)'
                )


def create_app(config_name='default'):
    """创建Flask应用实例"""
    app = AlcoenFlask(
        __name__,
        template_folder='../templates',
        static_folder='../static',
    )

    uploads_root = os.path.join(app.static_folder, 'uploads')
    
    # 加载配置
    app.config.from_object(config[config_name])

    @app.url_defaults
    def add_video_asset_version(endpoint, values):
        """Invalidate a cached video immediately when its deployed file changes."""
        if endpoint != 'static':
            return

        filename = str(values.get('filename') or '').replace('\\', '/')
        if filename not in VIDEO_ASSET_FILENAMES or values.get('v'):
            return

        video_path = os.path.join(app.static_folder, *filename.split('/'))
        try:
            values['v'] = str(int(os.path.getmtime(video_path)))
        except OSError:
            # Preserve static URL generation if a deployment temporarily lacks the file.
            pass
    
    # 初始化扩展
    db.init_app(app)
    
    # 注册蓝图
    from app.routes.main import main_bp, portal_bp
    from app.routes.transaction import transaction_bp
    from app.routes.statement import statement_bp
    from app.routes.product import product_bp
    from app.routes.contract import contract_bp
    from app.routes.official_contract import official_contract_bp
    from app.routes.auth import auth_bp
    from app.routes.user import user_bp
    from app.routes.role import role_bp
    from app.routes.department import department_bp
    from app.routes.theme import theme_bp
    from app.routes.settings import settings_bp
    from app.routes.backup import backup_bp
    from app.routes.qc import qc_bp
    app.register_blueprint(portal_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(qc_bp)
    app.register_blueprint(transaction_bp, url_prefix='/transaction')
    app.register_blueprint(statement_bp, url_prefix='/statement')
    app.register_blueprint(product_bp, url_prefix='/product')
    app.register_blueprint(contract_bp, url_prefix='/contract')
    app.register_blueprint(official_contract_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(role_bp)
    app.register_blueprint(department_bp)
    app.register_blueprint(theme_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(backup_bp)
    
    # [v1.5.2] 禁用缓存，确保合同状态更新后立即显示
    @app.after_request
    def disable_caching(response):
        if 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        """Serve uploaded files stored under the static/uploads directory."""
        path_parts = filename.replace('\\', '/').split('/')
        ai_cats_root = path_parts[0] if path_parts else ''
        if ai_cats_root in {'qc', 'research', 'assembly'}:
            from app.models import User
            from app.services.assembly_service import AssemblyService
            from app.services.qc_service import QCService
            from app.services.research_service import ResearchService

            user_id = session.get('user_id')
            user = User.query.get(user_id) if user_id else None
            if not user or not user.is_active:
                abort(403)

            resource = None
            try:
                if ai_cats_root == 'qc' and len(path_parts) >= 3:
                    if path_parts[1] == 'workpieces':
                        resource = QCService.get_workpiece(int(path_parts[2]), user)
                    else:
                        resource = QCService.get_work_order(int(path_parts[1]), user)
                elif ai_cats_root == 'research' and len(path_parts) >= 3:
                    if path_parts[1] == 'projects':
                        resource = ResearchService.get_project(int(path_parts[2]), user)
                    elif path_parts[1] == 'batches':
                        resource = ResearchService.get_batch(int(path_parts[2]), user)
                elif ai_cats_root == 'assembly' and len(path_parts) >= 3:
                    if path_parts[1] == 'products':
                        resource = AssemblyService.get_product(int(path_parts[2]), user)
                    elif path_parts[1] == 'orders':
                        resource = AssemblyService.get_order(int(path_parts[2]), user)
            except (TypeError, ValueError):
                abort(404)

            if resource is None:
                abort(403)
        return send_from_directory(uploads_root, filename)
    
    # 注册模板全局变量
    @app.context_processor
    def inject_user():
        """注入当前用户到模板"""
        from flask import session
        from app.models import User
        
        user = None
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
        
        return dict(current_user=user)
    
    # 注册主题偏好上下文处理器
    @app.context_processor
    def inject_theme():
        """注入用户主题偏好到模板"""
        from flask import session
        from app.models import User
        import os
        
        default_theme = {'bg_type': 'video', 'bg_image': 'bg-main.jpg', 'theme': 'light', 'style': 'glass'}
        
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
            if user:
                theme = user.get_theme_preference()
                # 添加背景图片URL
                if theme.get('bg_type') == 'image' and theme.get('bg_image'):
                    theme['bg_image_url'] = f"static/img/backgrounds/{theme['bg_image']}"
                return dict(theme=theme)
        
        return dict(theme=default_theme)
    
    # 注册模板过滤器
    from datetime import datetime
    
    @app.template_filter('format_date')
    def format_date(value):
        """格式化日期"""
        if value is None:
            return ''
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, '%Y-%m-%d')
            except:
                return value
        return value.strftime('%Y-%m-%d')
    
    @app.template_filter('format_money')
    def format_money(value):
        """格式化金额"""
        if value is None:
            return '0.00'
        return f"{float(value):,.2f}"
    
    # 创建数据库表
    with app.app_context():
        db.create_all()
        _run_lightweight_schema_upgrades()
        from app.services.auth_service import AuthService
        AuthService.ensure_qc_roles()
        from app.services.ai_cats_access_service import AICatsAccessService
        AICatsAccessService.ensure_ready()
        from app.services.official_contract_service import OfficialContractService
        OfficialContractService.ensure_builtin_template()
    
    return app
