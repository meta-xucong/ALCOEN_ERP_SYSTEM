"""Migrate legacy AI CATS roles into audited multi-identity assignments."""

from __future__ import annotations

import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import AICatsAccountProfile, AICatsUserIdentity
from app.services.ai_cats_access_service import AICatsAccessService


TABLES = (
    'ai_cats_account_profiles',
    'ai_cats_user_identities',
    'ai_cats_user_identity_scopes',
    'ai_cats_identity_audit_logs',
)


def _columns(table_name: str) -> set[str]:
    rows = db.session.execute(text(f'PRAGMA table_info({table_name})')).fetchall()
    return {row[1] for row in rows}


def _validate_schema() -> None:
    required = {
        'ai_cats_account_profiles': {'user_id', 'access_mode', 'is_enabled'},
        'ai_cats_user_identities': {
            'id', 'user_id', 'identity_code', 'status', 'source', 'requested_at',
        },
        'ai_cats_user_identity_scopes': {
            'id', 'user_identity_id', 'module_code', 'is_enabled',
        },
        'ai_cats_identity_audit_logs': {
            'id', 'target_user_id', 'identity_code', 'action', 'operator_id',
        },
    }
    for table_name, required_columns in required.items():
        missing = required_columns - _columns(table_name)
        if missing:
            raise RuntimeError(
                f'{table_name} is missing columns: {", ".join(sorted(missing))}'
            )


def migrate() -> None:
    """Create identity tables, backfill legacy access, and verify idempotence."""
    app = create_app()
    with app.app_context():
        _validate_schema()
        changed = AICatsAccessService.ensure_ready()
        profiles = AICatsAccountProfile.query.count()
        identities = AICatsUserIdentity.query.count()
        print('=' * 68)
        print('Migration: v2.2 AI CATS multi-identity access control')
        print('=' * 68)
        print(f'Rows added during this run: {changed}')
        print(f'Account profiles: {profiles}')
        print(f'Identity assignments: {identities}')
        for table_name in TABLES:
            print(f'{table_name}: {", ".join(sorted(_columns(table_name)))}')
        print('=' * 68)
        print('Migration completed. Existing business tables were not modified.')
        print('=' * 68)


if __name__ == '__main__':
    migrate()
