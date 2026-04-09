"""User management route tests."""

from __future__ import annotations


def _create_pending_user():
    """Create a pending user for approval/rejection flows."""
    from app.services.auth_service import AuthService

    user, error = AuthService.register_user(
        username="pending_user_001",
        real_name="Pending User",
        role_code="sales_manager",
        department_id=1,
        email="pending_user_001@example.com",
        phone="13800000000",
    )
    assert error is None
    return user


def test_user_list_requires_user_manage_permission(client, login, base_data):
    """Limited user should be blocked from user list."""
    login(base_data["limited_user_id"])
    resp = client.get("/user/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")


def test_approve_pending_user_flow(app, client, login, base_data):
    """Superadmin should be able to approve pending users."""
    from app.models import User

    with app.app_context():
        pending_user = _create_pending_user()
        pending_id = pending_user.id

    login(base_data["superadmin_id"])
    resp = client.post(f"/user/{pending_id}/approve", follow_redirects=False)
    assert resp.status_code == 302
    assert "/user/pending" in resp.headers.get("Location", "")

    with app.app_context():
        approved = User.query.get(pending_id)
        assert approved.is_active is True
        assert approved.approved_by == base_data["superadmin_id"]


def test_reject_pending_user_flow(app, client, login, base_data):
    """Superadmin should be able to reject pending users."""
    from app.models import User

    with app.app_context():
        pending_user = _create_pending_user()
        pending_id = pending_user.id

    login(base_data["superadmin_id"])
    resp = client.post(f"/user/{pending_id}/reject", follow_redirects=False)
    assert resp.status_code == 302
    assert "/user/pending" in resp.headers.get("Location", "")

    with app.app_context():
        rejected = User.query.get(pending_id)
        assert rejected is None
