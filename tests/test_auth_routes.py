"""Authentication route tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

from app import db
from app.models import Role, User, Department, TrustedDevice, QCUserBinding
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


def test_qc_register_page_bootstraps_roles_and_lists_options(app, client):
    """QC register page should recreate missing QC roles and show both role options."""
    resp = client.get("/auth/register/qc")

    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "质量控制人" in text
    assert "供应商" in text

    with app.app_context():
        roles = Role.query.filter(Role.code.in_(["qc_controller", "qc_inspector"])).all()
        assert {role.code for role in roles} == {"qc_controller", "qc_inspector"}


def test_logged_in_erp_user_visiting_qc_register_redirects_to_role_apply(app, client):
    """ERP users without QC access should be redirected to the QC role-apply flow."""
    with app.app_context():
        dept = Department(name="ERP Team")
        db.session.add(dept)
        db.session.flush()

        role = Role(
            name="Sales Manager",
            code="sales_manager_case_qc_register",
            permissions='["contract_view"]',
            level=20,
        )
        db.session.add(role)
        db.session.flush()

        user = User(
            username="erp_only_for_qc_register",
            password_hash=generate_password_hash("Pass123!"),
            real_name="ERP Only",
            role_id=role.id,
            department_id=dept.id,
            email="erp_only_for_qc_register@example.com",
            is_active=True,
            require_password_change=False,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.get("/auth/register/qc", follow_redirects=False)

    assert resp.status_code == 302
    assert "/auth/qc-role-apply" in resp.headers.get("Location", "")


def test_qc_role_apply_page_bootstraps_roles_and_lists_options(app, client):
    """ERP users applying for QC access should always see both QC role options."""
    with app.app_context():
        dept = Department(name="ERP Apply")
        db.session.add(dept)
        db.session.flush()

        role = Role(
            name="Department PM",
            code="department_pm_case_qc_apply",
            permissions='["contract_view"]',
            level=60,
        )
        db.session.add(role)
        db.session.flush()

        user = User(
            username="erp_apply_user",
            password_hash=generate_password_hash("Pass123!"),
            real_name="ERP Apply User",
            role_id=role.id,
            department_id=dept.id,
            email="erp_apply_user@example.com",
            is_active=True,
            require_password_change=False,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    resp = client.get("/auth/qc-role-apply")

    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    assert "质量控制人" in text
    assert "供应商" in text


def test_qc_register_existing_erp_user_is_rejected(app, client):
    """Submitting QC registration with an existing ERP username should be rejected."""
    with app.app_context():
        dept = Department(name="ERP Existing")
        db.session.add(dept)
        db.session.flush()

        erp_role = Role(
            name="Sales Existing",
            code="sales_manager_case_existing_qc",
            permissions='["contract_view"]',
            level=20,
        )
        db.session.add(erp_role)
        db.session.flush()

        user = User(
            username="same_name_qc_apply",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Existing ERP User",
            role_id=erp_role.id,
            department_id=dept.id,
            email="same_name_qc_apply@example.com",
            is_active=True,
            require_password_change=False,
        )
        db.session.add(user)
        db.session.commit()

    client.get("/auth/register/qc")

    with app.app_context():
        qc_role_id = next(
            role.id
            for role in Role.query.filter(Role.code.in_(["qc_controller", "qc_inspector"])).all()
            if role.code == "qc_controller"
        )

    resp = client.post(
        "/auth/register/qc",
        data={
            "username": "same_name_qc_apply",
            "real_name": "Existing ERP User",
            "role_id": str(qc_role_id),
            "email": "ignored@example.com",
            "phone": "13900000000",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert "ERP" in resp.get_data(as_text=True)

    with app.app_context():
        users = User.query.filter_by(username="same_name_qc_apply").all()
        assert len(users) == 1
        binding = QCUserBinding.query.filter_by(user_id=users[0].id).first()
        assert binding is None


def test_qc_register_new_user_creates_pending_user_and_binding(app, client):
    """Submitting QC registration for a new user should create a pending QC-only account."""
    resp = client.post(
        "/auth/register/qc",
        data={
            "username": "fresh_qc_user",
            "real_name": "Fresh QC User",
            "role_id": "999999",
            "email": "fresh_qc_user@example.com",
            "phone": "13911112222",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert "角色不存在或无效" in resp.get_data(as_text=True)

    with app.app_context():
        qc_roles = {role.code: role.id for role in Role.query.filter(Role.code.in_(["qc_controller", "qc_inspector"])).all()}

    resp = client.post(
        "/auth/register/qc",
        data={
            "username": "fresh_qc_user",
            "real_name": "Fresh QC User",
            "role_id": str(qc_roles["qc_inspector"]),
            "email": "fresh_qc_user@example.com",
            "phone": "13911112222",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/auth/pending" in resp.headers.get("Location", "")

    with app.app_context():
        user = User.query.filter_by(username="fresh_qc_user").first()
        assert user is not None
        assert user.role.code == "qc_inspector"
        assert user.is_active is False
        binding = QCUserBinding.query.filter_by(user_id=user.id).first()
        assert binding is not None
        assert binding.role.code == "qc_inspector"


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
