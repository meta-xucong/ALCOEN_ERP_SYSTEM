"""Permission tests for transaction routes."""

from __future__ import annotations

from app.services.contract_service import ContractService


def _create_contract_with_transaction(owner_user_id: int):
    """Create one contract and one transaction for API checks."""
    contract = ContractService.create_contract(
        {
            "contract_no": f"TX-CONTRACT-{owner_user_id}",
            "company_name": "Tx Corp",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Sales Owner",
            "created_by_id": owner_user_id,
        },
        [
            {
                "product_code": "TX-001",
                "product_name": "Tx Product",
                "product_model": "TM1",
                "product_type": "TypeT",
                "quantity": 20,
                "unit": "pcs",
                "price": 12,
                "remark": "",
            }
        ],
    )
    cp = contract.contract_products[0]
    ContractService.add_transaction(
        contract.id,
        {
            "contract_product_id": cp.id,
            "quantity": 10,
            "unit": "pcs",
            "price_with_tax": 12,
            "handler": "Tester",
            "delivery_date": "2026-04-01",
            "invoice_date": "",
            "remark": "",
        },
        is_new=True,
    )
    return contract.company_name


def test_products_by_company_api_requires_permission(app, client, login, base_data):
    """User without transaction_view should be redirected away from the API."""
    login(base_data["limited_user_id"])
    resp = client.get("/transaction/api/products-by-company?company_name=Tx Corp")
    assert resp.status_code == 302
    assert resp.headers.get("Location", "").endswith("/")


def test_products_by_company_api_returns_codes_for_superadmin(app, client, login, base_data):
    """Superadmin should get product codes for the specified company."""
    with app.app_context():
        company_name = _create_contract_with_transaction(base_data["owner_user_id"])

    login(base_data["superadmin_id"])
    resp = client.get(f"/transaction/api/products-by-company?company_name={company_name}")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert "codes" in payload
    assert "TX-001" in payload["codes"]
