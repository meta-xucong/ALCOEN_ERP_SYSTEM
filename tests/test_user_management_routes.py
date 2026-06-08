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


def test_edit_user_supports_multiple_departments(app, client, login, base_data):
    """Editing a user should allow assigning multiple departments."""
    from app import db
    from app.models import Department, Role, User

    with app.app_context():
        second_dept = Department(name="Columns")
        pm_role = Role(
            name="Department PM",
            code="department_pm",
            permissions='["contract_view", "contract_edit"]',
            level=50,
        )
        db.session.add_all([second_dept, pm_role])
        db.session.flush()

        user = User(
            username="multi_dept_user",
            password_hash="x",
            real_name="Multi Dept User",
            role_id=pm_role.id,
            department_id=base_data["department_id"],
            is_active=True,
            require_password_change=False,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        second_dept_id = second_dept.id
        pm_role_id = pm_role.id

    login(base_data["superadmin_id"])
    resp = client.post(
        f"/user/{user_id}/edit",
        data={
            "real_name": "Multi Dept User",
            "email": "",
            "phone": "",
            "role_id": str(pm_role_id),
            "department_ids": [str(base_data["department_id"]), str(second_dept_id)],
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        updated_user = User.query.get(user_id)
        assert updated_user.department_id == base_data["department_id"]
        assert updated_user.department_names == ["Sales", "Columns"]
