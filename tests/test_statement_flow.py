"""Statement generation and listing regression tests."""

from __future__ import annotations

from app.services.contract_service import ContractService


def _create_contract_with_transaction(owner_user_id: int):
    """Create one contract and one transaction for statement generation."""
    contract = ContractService.create_contract(
        {
            "contract_no": f"ST-{owner_user_id}",
            "company_name": "Statement Corp",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Sales Owner",
            "created_by_id": owner_user_id,
        },
        [
            {
                "product_code": "ST-P1",
                "product_name": "Statement Product",
                "product_model": "SP1",
                "product_type": "TypeS",
                "quantity": 10,
                "unit": "pcs",
                "price": 10,
                "remark": "",
            }
        ],
    )
    cp = contract.contract_products[0]
    ContractService.add_transaction(
        contract.id,
        {
            "contract_product_id": cp.id,
            "quantity": 5,
            "unit": "pcs",
            "price_with_tax": 10,
            "handler": "Logistics",
            "delivery_date": "2026-04-01",
            "invoice_date": "",
            "remark": "tx for statement",
        },
        is_new=True,
    )


def test_statement_generator_empty_filter_does_not_crash(app, client, login, base_data):
    """Submitting generator without filters should return page with warning, not 500."""
    login(base_data["superadmin_id"])
    resp = client.post("/statement/generator", data={}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"<form" in resp.data


def test_statement_generator_creates_statement(app, client, login, base_data):
    """Generator should create a statement and redirect to statement detail."""
    from app.models import Statement

    with app.app_context():
        _create_contract_with_transaction(base_data["owner_user_id"])

    login(base_data["superadmin_id"])
    resp = client.post(
        "/statement/generator",
        data={"company_name": "Statement Corp"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/statement/DZ" in resp.headers.get("Location", "")

    with app.app_context():
        statement = Statement.query.first()
        assert statement is not None
        assert statement.company_name == "Statement Corp"
        assert statement.record_count == 1


def test_statement_list_requires_login(client):
    """Statement list should redirect anonymous users to login."""
    resp = client.get("/statement/list", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")
