"""Permission regression tests for contract APIs."""

from __future__ import annotations

from app.services.contract_service import ContractService


def _create_contract(owner_user_id: int):
    """Create one contract for permission tests."""
    contract = ContractService.create_contract(
        {
            "contract_no": f"PERM-CONTRACT-{owner_user_id}",
            "company_name": "Access Corp",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Sales Owner",
            "created_by_id": owner_user_id,
        },
        [
            {
                "product_code": "PERM-001",
                "product_name": "Permission Product",
                "product_model": "PM1",
                "product_type": "TypeP",
                "quantity": 20,
                "unit": "pcs",
                "price": 30,
                "remark": "",
            }
        ],
    )
    return contract.id


def test_contract_api_forbidden_for_unrelated_sales_manager(app, client, login, base_data):
    """A sales manager must not access another sales manager's contract APIs."""
    contract_id: int
    with app.app_context():
        contract_id = _create_contract(base_data["owner_user_id"])

    login(base_data["other_sales_id"])

    stats_resp = client.get(f"/contract/api/stats/{contract_id}")
    products_resp = client.get(f"/contract/api/contract-products/{contract_id}")
    remark_resp = client.post(
        f"/contract/api/append-remark/{contract_id}",
        json={"message": "should be denied"},
    )

    assert stats_resp.status_code == 403
    assert products_resp.status_code == 403
    assert remark_resp.status_code == 403
    assert stats_resp.get_json()["error"] == "forbidden"
    assert products_resp.get_json()["error"] == "forbidden"
    assert remark_resp.get_json()["error"] == "forbidden"


def test_contract_api_allowed_for_owner(app, client, login, base_data):
    """Contract owner should have access to own contract APIs."""
    contract_id: int
    with app.app_context():
        contract_id = _create_contract(base_data["owner_user_id"])

    login(base_data["owner_user_id"])

    stats_resp = client.get(f"/contract/api/stats/{contract_id}")
    products_resp = client.get(f"/contract/api/contract-products/{contract_id}")
    remark_resp = client.post(
        f"/contract/api/append-remark/{contract_id}",
        json={"message": "owner update"},
    )

    assert stats_resp.status_code == 200
    assert products_resp.status_code == 200
    assert remark_resp.status_code == 200
    assert "total_planned_qty" in stats_resp.get_json()
    assert "products" in products_resp.get_json()
    assert remark_resp.get_json()["success"] is True
