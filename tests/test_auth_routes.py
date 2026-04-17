"""Authentication route tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

from app import db
from app.models import Role, User, Department, TrustedDevice
from app.services.email_service import EmailService


def test_register_page_loads(client):
    """Register page should load for anonymous users."""
    resp = client.get("/auth/register")
    assert resp.status_code == 200
    assert b"<form" in resp.data


def test_register_creates_pending_user(app, client, base_data):
    """Posting register should create a pending user and redirect to pending page."""
    from app.models import User

    resp = client.post(
        "/auth/register",
        data={
            "username": "new_sales_user",
            "real_name": "New Sales",
            "role_id": str(base_data["sales_role_id"]),
            "department_id": str(base_data["department_id"]),
            "email": "new_sales_user@example.com",
            "phone": "13900000000",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/auth/pending" in resp.headers.get("Location", "")

    with app.app_context():
        user = User.query.filter_by(username="new_sales_user").first()
        assert user is not None
        assert user.is_active is False
        assert user.require_password_change is True


def test_superadmin_always_requires_verify_even_if_trusted_device(app, client, monkeypatch):
    """Superadmin should always go through email verification."""
    with app.app_context():
        dept = Department(name="IT")
        db.session.add(dept)
        db.session.flush()

        role = Role(
            name="Super Admin",
            code="superadmin_case",
            permissions="[]",
            level=999,
        )
        db.session.add(role)
        db.session.flush()

        user = User(
            username="admin_2fa_case",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Admin 2FA",
            role_id=role.id,
            department_id=dept.id,
            email="admin_2fa_case@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        db.session.add(user)
        db.session.flush()

        fp = EmailService.generate_device_fingerprint("UA-TEST", "1.2.3.4")
        td = TrustedDevice(
            user_id=user.id,
            device_fingerprint=fp,
            device_name="Chrome on Windows",
            ip_address="1.2.3.4",
            expires_at=datetime.now() + timedelta(days=30),
        )
        db.session.add(td)
        db.session.commit()

    monkeypatch.setattr(EmailService, "create_verification_code", lambda **kwargs: ("1234", None))
    monkeypatch.setattr(EmailService, "send_verify_code_email", lambda *args, **kwargs: (True, None))

    resp = client.post(
        "/auth/login",
        data={"username": "admin_2fa_case", "password": "Pass123!", "remember": "on"},
        headers={"User-Agent": "UA-TEST", "X-Forwarded-For": "1.2.3.4"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/auth/verify-code" in resp.headers.get("Location", "")
    with client.session_transaction() as sess:
        assert "pending_verify_user_id" in sess
        assert "user_id" not in sess


def test_login_uses_forwarded_ip_for_login_record(app, client):
    """Login record should use real client IP from proxy header."""
    with app.app_context():
        dept = Department(name="Sales")
        db.session.add(dept)
        db.session.flush()

        role = Role(
            name="Sales Manager",
            code="sales_manager_case",
            permissions='["contract_view"]',
            level=20,
        )
        db.session.add(role)
        db.session.flush()

        user = User(
            username="sales_ip_case",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Sales IP",
            role_id=role.id,
            department_id=dept.id,
            email="sales_ip_case@example.com",
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        db.session.add(user)
        db.session.flush()

        fp = EmailService.generate_device_fingerprint("UA-IP-TEST", "8.8.8.8")
        td = TrustedDevice(
            user_id=user.id,
            device_fingerprint=fp,
            device_name="IP Test Device",
            ip_address="8.8.8.8",
            expires_at=datetime.now() + timedelta(days=30),
        )
        db.session.add(td)
        db.session.commit()

    resp = client.post(
        "/auth/login",
        data={"username": "sales_ip_case", "password": "Pass123!"},
        headers={"User-Agent": "UA-IP-TEST", "X-Forwarded-For": "8.8.8.8, 127.0.0.1"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    with app.app_context():
        user = User.query.filter_by(username="sales_ip_case").first()
        assert user is not None
        assert user.last_login_ip == "8.8.8.8"


def test_login_verify_code_send_is_deduplicated_with_recent_code(app, client, monkeypatch):
    """Repeated login attempts in a short window should not send duplicate emails."""
    with app.app_context():
        dept = Department(name="Ops")
        db.session.add(dept)
        db.session.flush()

        role = Role(
            name="Ops User",
            code="ops_user_case",
            permissions='["contract_view"]',
            level=20,
        )
        db.session.add(role)
        db.session.flush()

        user = User(
            username="ops_verify_dedupe",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Ops Verify",
            role_id=role.id,
            department_id=dept.id,
            email="ops_verify_dedupe@example.com",
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        db.session.add(user)
        db.session.commit()

    send_count = {"n": 0}

    def _fake_send(*args, **kwargs):
        send_count["n"] += 1
        return True, None

    monkeypatch.setattr(EmailService, "send_verify_code_email", _fake_send)

    first = client.post(
        "/auth/login",
        data={"username": "ops_verify_dedupe", "password": "Pass123!"},
        headers={"User-Agent": "UA-DEDUPE", "X-Forwarded-For": "11.11.11.11"},
        follow_redirects=False,
    )
    assert first.status_code == 302
    assert "/auth/verify-code" in first.headers.get("Location", "")
    assert send_count["n"] == 1

    with client.session_transaction() as sess:
        sess.pop("pending_verify_user_id", None)
        sess.pop("pending_verify_fingerprint", None)
        sess.pop("pending_verify_remember", None)
        sess.pop("pending_verify_purpose", None)

    second = client.post(
        "/auth/login",
        data={"username": "ops_verify_dedupe", "password": "Pass123!"},
        headers={"User-Agent": "UA-DEDUPE", "X-Forwarded-For": "11.11.11.11"},
        follow_redirects=False,
    )
    assert second.status_code == 302
    assert "/auth/verify-code" in second.headers.get("Location", "")
    assert send_count["n"] == 1
