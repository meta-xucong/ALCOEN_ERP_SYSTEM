"""Admin-oriented route tests (department / role / backup)."""

from __future__ import annotations

import json


def test_department_crud_routes_for_superadmin(app, client, login, base_data):
    """Superadmin can create, edit, and delete departments."""
    from app.models import Department

    login(base_data["superadmin_id"])

    create_resp = client.post("/department/new", data={"name": "Ops"}, follow_redirects=False)
    assert create_resp.status_code == 302
    assert "/department/" in create_resp.headers.get("Location", "")

    with app.app_context():
        dept = Department.query.filter_by(name="Ops").first()
        assert dept is not None
        dept_id = dept.id

    edit_resp = client.post(f"/department/{dept_id}/edit", data={"name": "Ops-2"}, follow_redirects=False)
    assert edit_resp.status_code == 302

    with app.app_context():
        edited = Department.query.get(dept_id)
        assert edited.name == "Ops-2"

    delete_resp = client.post(f"/department/{dept_id}/delete", follow_redirects=False)
    assert delete_resp.status_code == 302

    with app.app_context():
        deleted = Department.query.get(dept_id)
        assert deleted is None


def test_department_users_api_requires_admin(client, login, base_data):
    """Non-admin users should not access department users API."""
    login(base_data["owner_user_id"])
    resp = client.get(f"/department/{base_data['department_id']}/users", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")


def test_role_permission_update_route(app, client, login, base_data):
    """Role edit route should persist selected permissions."""
    from app.models import Role

    login(base_data["superadmin_id"])

    with app.app_context():
        role = Role.query.filter_by(code="limited_user").first()
        role_id = role.id

    resp = client.post(
        f"/role/{role_id}/edit",
        data={"permissions": ["transaction_view", "product_view"]},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/role/" in resp.headers.get("Location", "")

    with app.app_context():
        updated = Role.query.get(role_id)
        perms = json.loads(updated.permissions or "[]")
        assert "transaction_view" in perms
        assert "product_view" in perms


def test_backup_page_requires_admin(client, login, base_data):
    """Backup page should reject normal users."""
    login(base_data["owner_user_id"])
    resp = client.get("/backup/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")


def test_settings_email_access_for_user_manage_non_superadmin(app, client, login, base_data):
    """Users with user_manage permission can access email settings even if not superadmin."""
    from app import db
    from app.models import Role

    with app.app_context():
        role = Role.query.get(base_data["limited_role_id"])
        role.permissions = json.dumps(["user_manage"])
        db.session.commit()

    login(base_data["limited_user_id"])

    settings_resp = client.get("/settings/email", follow_redirects=False)
    assert settings_resp.status_code == 200

    home_resp = client.get("/erp/", follow_redirects=False)
    assert home_resp.status_code == 200
    assert "邮箱管理" in home_resp.get_data(as_text=True)


def test_settings_email_denied_without_user_manage(client, login, base_data):
    """Users without user_manage permission should be redirected."""
    login(base_data["owner_user_id"])
    resp = client.get("/settings/email", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")
