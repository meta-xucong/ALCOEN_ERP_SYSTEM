"""Pytest fixtures for ERP integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pytest

from config import config as config_map


def _build_testing_config(db_file: Path):
    """Create a dedicated testing config class for a temporary DB."""

    class TestingConfig(config_map["default"]):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_file.as_posix()}"
        SERVER_NAME = "localhost"

    return TestingConfig


@pytest.fixture()
def app(tmp_path):
    """Create an isolated Flask app and database per test."""
    db_file = tmp_path / "erp_test.db"
    config_map["testing"] = _build_testing_config(db_file)

    from app import create_app, db

    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def db_session(app):
    """Database session bound to the temporary test app."""
    from app import db

    with app.app_context():
        yield db.session
        db.session.rollback()


@pytest.fixture()
def base_data(db_session) -> Dict[str, int]:
    """Seed baseline roles/users/department and return ids."""
    from app.models import Department, Role, User

    dept = Department(name="Sales")
    db_session.add(dept)
    db_session.flush()

    superadmin_role = Role(
        name="Super Admin",
        code="superadmin",
        permissions=json.dumps([]),
        level=999,
    )
    sales_role = Role(
        name="Sales Manager",
        code="sales_manager",
        permissions=json.dumps(["contract_edit", "contract_create", "contract_view"]),
        level=10,
    )
    limited_role = Role(
        name="Limited User",
        code="limited_user",
        permissions=json.dumps([]),
        level=1,
    )
    db_session.add_all([superadmin_role, sales_role, limited_role])
    db_session.flush()

    superadmin = User(
        username="superadmin",
        password_hash="x",
        real_name="Super Admin",
        role_id=superadmin_role.id,
        department_id=dept.id,
        is_active=True,
        is_superadmin=True,
        require_password_change=False,
    )
    owner_user = User(
        username="sales_owner",
        password_hash="x",
        real_name="Sales Owner",
        role_id=sales_role.id,
        department_id=dept.id,
        is_active=True,
        is_superadmin=False,
        require_password_change=False,
    )
    other_sales = User(
        username="sales_other",
        password_hash="x",
        real_name="Sales Other",
        role_id=sales_role.id,
        department_id=dept.id,
        is_active=True,
        is_superadmin=False,
        require_password_change=False,
    )
    limited_user = User(
        username="limited_user",
        password_hash="x",
        real_name="Limited User",
        role_id=limited_role.id,
        department_id=dept.id,
        is_active=True,
        is_superadmin=False,
        require_password_change=False,
    )
    db_session.add_all([superadmin, owner_user, other_sales, limited_user])
    db_session.commit()

    return {
        "department_id": dept.id,
        "sales_role_id": sales_role.id,
        "limited_role_id": limited_role.id,
        "superadmin_id": superadmin.id,
        "owner_user_id": owner_user.id,
        "other_sales_id": other_sales.id,
        "limited_user_id": limited_user.id,
    }


@pytest.fixture()
def login(client):
    """Login helper by assigning user_id in session."""

    def _login(user_id: int) -> None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id

    return _login
