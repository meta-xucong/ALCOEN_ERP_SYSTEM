"""High-value route smoke tests."""

from __future__ import annotations

import json

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/erp/",
        "/contract/list",
        "/contract/new",
        "/transaction/",
        "/transaction/new",
        "/product/",
        "/product/new",
        "/statement/generator",
        "/statement/list",
        "/theme/settings",
        "/backup/",
        "/department/",
        "/role/",
        "/user/",
        "/user/pending",
        "/auth/change-password",
        "/qc/",
        "/qc/production/",
        "/qc/assembly/",
        "/qc/research/",
    ],
)
def test_protected_pages_load_for_superadmin(client, login, base_data, path):
    """Superadmin should be able to open protected pages without server errors."""
    login(base_data["superadmin_id"])
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code in (200, 302)


@pytest.mark.parametrize(
    "path",
    [
        "/erp/",
        "/contract/list",
        "/transaction/",
        "/product/",
        "/statement/list",
        "/theme/settings",
        "/backup/",
        "/department/",
        "/role/",
        "/user/",
    ],
)
def test_protected_pages_redirect_without_login(client, path):
    """Anonymous users should be redirected to login for protected pages."""
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")


def test_new_contract_page_contains_autofill_helpers(client, login, base_data):
    """New contract page must include JS helpers used by one-click fill buttons."""
    login(base_data["superadmin_id"])
    resp = client.get("/contract/new", follow_redirects=False)
    assert resp.status_code == 200

    html = resp.get_data(as_text=True)
    assert "function addTransactionRowWithData" in html
    assert "function addPaymentRowWithData" in html


def test_prefilled_payment_rows_do_not_keep_amounts_linked(client, login, base_data):
    """Autofilled/restored payment values must be independently editable."""
    login(base_data["superadmin_id"])
    resp = client.get("/contract/new", follow_redirects=False)
    assert resp.status_code == 200

    html = resp.get_data(as_text=True)
    add_with_data = html.split("function addPaymentRowWithData", 1)[1].split(
        "// [v1.4]", 1
    )[0]
    assert "bindPaymentRowBehavior(row, { autoFollowInvoice: false });" in add_with_data
    assert "const autoFollowLockedOff = options.autoFollowInvoice === false;" in html


def test_logistics_edit_page_contains_autofill_helpers(app, client, login):
    """Logistics edit page should include one-click delivery autofill helpers."""
    from app import db
    from app.models import Contract, ContractProduct, Role, User

    with app.app_context():
        logistics_role = Role(
            name="Logistics Manager",
            code="logistics_manager",
            permissions=json.dumps(["contract_view", "contract_edit_delivery"]),
            level=60,
        )
        db.session.add(logistics_role)
        db.session.flush()

        logistics_user = User(
            username="logistics_autofill",
            password_hash="x",
            real_name="Logistics Autofill",
            role_id=logistics_role.id,
            department_id=None,
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        db.session.add(logistics_user)
        db.session.flush()

        contract = Contract(
            contract_no="AUTOFILL-L001",
            company_name="Autofill Company",
            department="Logistics",
            manager="Logistics Autofill",
            created_by_id=logistics_user.id,
            total_value=1200,
        )
        db.session.add(contract)
        db.session.flush()

        contract_product = ContractProduct(
            contract_id=contract.id,
            product_code="P-001",
            product_name="Autofill Product",
            product_model="M-01",
            product_type="Type-A",
            quantity=12,
            unit="pcs",
            price=100,
            total=1200,
        )
        db.session.add(contract_product)
        db.session.commit()

        logistics_user_id = logistics_user.id
        contract_id = contract.id

    login(logistics_user_id)
    resp = client.get(f"/contract/{contract_id}/logistics-edit", follow_redirects=False)
    assert resp.status_code == 200

    html = resp.get_data(as_text=True)
    assert "function fillAllTransactions" in html
    assert 'onclick="fillAllTransactions()"' in html
