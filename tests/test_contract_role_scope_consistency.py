"""Contract role scope and permission consistency tests."""

from __future__ import annotations

import json

from app import db
from app.models import Contract, Department, Role, User


def _create_role(code: str, permissions: list[str], level: int = 10) -> Role:
    role = Role(
        name=code,
        code=code,
        permissions=json.dumps(permissions),
        level=level,
    )
    db.session.add(role)
    db.session.flush()
    return role


def _create_user(username: str, role: Role, department: Department | None) -> User:
    user = User(
        username=username,
        password_hash="x",
        real_name=username,
        role_id=role.id,
        department_id=department.id if department else None,
        is_active=True,
        is_superadmin=False,
        require_password_change=False,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _create_contract(contract_no: str, creator_id: int, department_name: str) -> Contract:
    contract = Contract(
        contract_no=contract_no,
        company_name="Permission Corp",
        department=department_name,
        manager="owner",
        created_by_id=creator_id,
        total_value=0,
    )
    db.session.add(contract)
    db.session.commit()
    return contract


def test_gm_assistant_can_view_and_edit_any_contract(app, client, login):
    """GM assistant with contract permissions should access contract detail/edit."""
    with app.app_context():
        sales = Department(name="Sales")
        ops = Department(name="Ops")
        db.session.add_all([sales, ops])
        db.session.flush()

        gm_assistant_role = _create_role(
            "gm_assistant",
            ["contract_view", "contract_edit", "contract_create"],
            level=70,
        )
        sales_role = _create_role(
            "sales_manager",
            ["contract_view", "contract_edit", "contract_create"],
            level=20,
        )

        assistant = _create_user("gm_assistant_user", gm_assistant_role, None)
        owner = _create_user("sales_owner_user", sales_role, sales)
        contract = _create_contract("ASSIST-C001", owner.id, "Sales")
        _ = ops
        assistant_id = assistant.id
        contract_id = contract.id

    login(assistant_id)

    detail_resp = client.get(f"/contract/{contract_id}", follow_redirects=True)
    edit_resp = client.get(f"/contract/{contract_id}/edit", follow_redirects=True)

    assert detail_resp.status_code == 200
    assert edit_resp.status_code == 200
    assert b"ASSIST-C001" in detail_resp.data
    assert b"ASSIST-C001" in edit_resp.data


def test_sales_manager_cannot_see_or_open_other_users_contract(app, client, login):
    """Sales manager should neither list nor open contracts owned by others."""
    with app.app_context():
        sales = Department(name="Sales")
        db.session.add(sales)
        db.session.flush()

        sales_role = _create_role(
            "sales_manager",
            ["contract_view", "contract_edit", "contract_create"],
            level=20,
        )
        owner = _create_user("sales_owner_a", sales_role, sales)
        other = _create_user("sales_owner_b", sales_role, sales)
        contract = _create_contract("OWN-C001", owner.id, "Sales")
        other_id = other.id
        contract_id = contract.id

    login(other_id)

    list_resp = client.get("/contract/list")
    detail_resp = client.get(f"/contract/{contract_id}", follow_redirects=True)

    assert list_resp.status_code == 200
    assert detail_resp.status_code == 200
    assert b"OWN-C001" not in list_resp.data
    assert b"OWN-C001" not in detail_resp.data


def test_user_without_contract_view_permission_cannot_access_contract_list(app, client, login):
    """Users lacking contract_view permission should be blocked at route entry."""
    with app.app_context():
        dept = Department(name="Sales")
        db.session.add(dept)
        db.session.flush()

        limited_role = _create_role("limited_user", [], level=1)
        limited_user = _create_user("limited_view_user", limited_role, dept)
        limited_user_id = limited_user.id
        db.session.commit()

    login(limited_user_id)

    resp = client.get("/contract/list", follow_redirects=False)
    assert resp.status_code in (301, 302, 303, 307, 308)
    assert "/contract/list" not in (resp.headers.get("Location") or "")


def test_department_pm_cannot_delete_other_department_contract(app, client, login):
    """Delete route must enforce row-level scope, not only permission code."""
    with app.app_context():
        sales = Department(name="Sales")
        ops = Department(name="Ops")
        db.session.add_all([sales, ops])
        db.session.flush()

        pm_role = _create_role(
            "department_pm",
            ["contract_view", "contract_edit", "contract_create", "contract_delete"],
            level=50,
        )
        sales_role = _create_role(
            "sales_manager",
            ["contract_view", "contract_edit", "contract_create"],
            level=20,
        )

        pm_sales = _create_user("pm_sales", pm_role, sales)
        ops_owner = _create_user("ops_owner", sales_role, ops)
        target_contract = _create_contract("OPS-C001", ops_owner.id, "Ops")

        pm_sales_id = pm_sales.id
        target_contract_id = target_contract.id

    login(pm_sales_id)
    resp = client.post(f"/contract/{target_contract_id}/delete", follow_redirects=True)

    assert resp.status_code == 200
    with app.app_context():
        assert Contract.query.get(target_contract_id) is not None


def test_sales_manager_can_delete_own_contract_without_contract_delete_permission(app, client, login):
    """Contract creator should be able to delete own contract even without contract_delete code."""
    with app.app_context():
        sales = Department(name="Sales")
        db.session.add(sales)
        db.session.flush()

        sales_role = _create_role(
            "sales_manager",
            ["contract_view", "contract_edit", "contract_create"],  # no contract_delete
            level=20,
        )
        owner = _create_user("sales_owner_delete_self", sales_role, sales)
        contract = _create_contract("SELF-DEL-C001", owner.id, "Sales")

        owner_id = owner.id
        contract_id = contract.id

    login(owner_id)
    resp = client.post(f"/contract/{contract_id}/delete", follow_redirects=True)

    assert resp.status_code == 200
    with app.app_context():
        assert Contract.query.get(contract_id) is None


def test_sales_manager_cannot_delete_others_contract_without_contract_delete_permission(app, client, login):
    """Non-owner sales manager should still be blocked from deleting another creator's contract."""
    with app.app_context():
        sales = Department(name="Sales")
        db.session.add(sales)
        db.session.flush()

        sales_role = _create_role(
            "sales_manager",
            ["contract_view", "contract_edit", "contract_create"],  # no contract_delete
            level=20,
        )
        owner = _create_user("sales_owner_delete_other_a", sales_role, sales)
        other = _create_user("sales_owner_delete_other_b", sales_role, sales)
        contract = _create_contract("OTHER-DEL-C001", owner.id, "Sales")

        other_id = other.id
        contract_id = contract.id

    login(other_id)
    resp = client.post(f"/contract/{contract_id}/delete", follow_redirects=True)

    assert resp.status_code == 200
    with app.app_context():
        assert Contract.query.get(contract_id) is not None


def test_contract_scope_matrix_for_all_roles(app):
    """Validate view/edit/basic-edit matrix across all built-in contract roles."""
    with app.app_context():
        sales = Department(name="Sales")
        ops = Department(name="Ops")
        db.session.add_all([sales, ops])
        db.session.flush()

        gm_role = _create_role("general_manager", ["contract_view", "contract_edit"], level=80)
        gma_role = _create_role("gm_assistant", ["contract_view", "contract_edit"], level=70)
        logistics_role = _create_role(
            "logistics_manager",
            ["contract_view", "contract_edit_delivery"],
            level=60,
        )
        pm_role = _create_role("department_pm", ["contract_view", "contract_edit"], level=50)
        sales_role = _create_role("sales_manager", ["contract_view", "contract_edit"], level=20)
        limited_role = _create_role("limited_user", [], level=1)

        gm = _create_user("gm_user", gm_role, None)
        gma = _create_user("gma_user", gma_role, None)
        logistics = _create_user("logistics_user", logistics_role, None)
        pm_sales = _create_user("pm_sales_user", pm_role, sales)
        pm_ops = _create_user("pm_ops_user", pm_role, ops)
        sales_owner = _create_user("sales_owner_matrix", sales_role, sales)
        sales_other = _create_user("sales_other_matrix", sales_role, sales)
        limited = _create_user("limited_matrix", limited_role, sales)

        contract = _create_contract("MATRIX-C001", sales_owner.id, "Sales")

        expected = {
            "gm": (True, True, True),
            "gma": (True, True, True),
            "logistics": (True, True, False),
            "pm_sales": (True, True, True),
            "pm_ops": (False, False, False),
            "sales_owner": (True, True, True),
            "sales_other": (False, False, False),
            "limited": (False, False, False),
        }

        actual = {
            "gm": (
                gm.can_view_contract(contract),
                gm.can_edit_contract(contract),
                gm.can_edit_contract_basic(contract),
            ),
            "gma": (
                gma.can_view_contract(contract),
                gma.can_edit_contract(contract),
                gma.can_edit_contract_basic(contract),
            ),
            "logistics": (
                logistics.can_view_contract(contract),
                logistics.can_edit_contract(contract),
                logistics.can_edit_contract_basic(contract),
            ),
            "pm_sales": (
                pm_sales.can_view_contract(contract),
                pm_sales.can_edit_contract(contract),
                pm_sales.can_edit_contract_basic(contract),
            ),
            "pm_ops": (
                pm_ops.can_view_contract(contract),
                pm_ops.can_edit_contract(contract),
                pm_ops.can_edit_contract_basic(contract),
            ),
            "sales_owner": (
                sales_owner.can_view_contract(contract),
                sales_owner.can_edit_contract(contract),
                sales_owner.can_edit_contract_basic(contract),
            ),
            "sales_other": (
                sales_other.can_view_contract(contract),
                sales_other.can_edit_contract(contract),
                sales_other.can_edit_contract_basic(contract),
            ),
            "limited": (
                limited.can_view_contract(contract),
                limited.can_edit_contract(contract),
                limited.can_edit_contract_basic(contract),
            ),
        }

        assert actual == expected


def test_department_pm_with_multiple_departments_can_access_each_department_contract(app):
    """Department PM assigned to multiple departments should inherit all assigned scopes."""
    with app.app_context():
        sales = Department(name="Sales")
        ops = Department(name="Ops")
        db.session.add_all([sales, ops])
        db.session.flush()

        pm_role = _create_role("department_pm", ["contract_view", "contract_edit"], level=50)
        sales_role = _create_role("sales_manager", ["contract_view", "contract_edit"], level=20)

        pm_user = _create_user("pm_multi_dept", pm_role, sales)
        pm_user.set_departments([sales.id, ops.id])
        owner = _create_user("ops_owner_multi", sales_role, ops)
        contract = _create_contract("OPS-MULTI-C001", owner.id, "Ops")

        assert pm_user.can_access_department("Sales") is True
        assert pm_user.can_access_department("Ops") is True
        assert pm_user.can_view_contract(contract) is True
        assert pm_user.can_edit_contract(contract) is True


def test_multi_department_pm_lists_and_creates_contract_in_selected_department(
    app, client, login
):
    """A multi-department PM can work in either assigned department."""
    with app.app_context():
        sales = Department(name="Sales")
        ops = Department(name="Ops")
        db.session.add_all([sales, ops])
        db.session.flush()

        pm_role = _create_role(
            "department_pm",
            ["contract_view", "contract_edit", "contract_create"],
            level=50,
        )
        pm_user = _create_user("pm_contract_multi", pm_role, sales)
        pm_user.set_departments([sales.id, ops.id])
        _create_contract("SALES-MULTI-C001", pm_user.id, "Sales")
        _create_contract("OPS-MULTI-C001", pm_user.id, "Ops")
        db.session.commit()
        pm_user_id = pm_user.id

    login(pm_user_id)

    list_response = client.get("/contract/list")
    assert list_response.status_code == 200
    assert b"SALES-MULTI-C001" in list_response.data
    assert b"OPS-MULTI-C001" in list_response.data

    form_response = client.get("/contract/new")
    assert form_response.status_code == 200
    assert b'name="department"' in form_response.data
    assert b'value="Sales"' in form_response.data
    assert b'value="Ops"' in form_response.data

    create_response = client.post(
        "/contract/new",
        data={
            "contract_no": "OPS-MULTI-C002",
            "company_name": "Permission Corp",
            "department": "Ops",
            "manager": "pm_contract_multi",
            "product_count": "1",
            "product_0_code": "OPS-P001",
                "product_0_name": "Ops Product",
                "product_0_type": "自产",
                "product_0_quantity": "1",
            "product_0_unit": "pcs",
            "product_0_price": "10",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    with app.app_context():
        created = Contract.query.filter_by(contract_no="OPS-MULTI-C002").one()
        assert created.department == "Ops"
