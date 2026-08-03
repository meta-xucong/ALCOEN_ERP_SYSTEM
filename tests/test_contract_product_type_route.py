"""Route tests for contract product type handling."""

from __future__ import annotations


def test_contract_new_rejects_missing_product_type(app, client, login, base_data):
    """The contract form should reject a brand-new product without a type."""
    login(base_data["superadmin_id"])

    response = client.post(
        "/contract/new",
        data={
            "contract_no": "ROUTE-TYPE-MISSING",
            "company_name": "Route Corp",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Sales Owner",
            "product_count": "1",
            "product_0_code": "ROUTE-TYPE-001",
            "product_0_name": "Typed Product",
            "product_0_model": "RT1",
            "product_0_type": "",
            "product_0_quantity": "2",
            "product_0_unit": "pcs",
            "product_0_price": "18",
            "product_0_total": "36",
            "product_0_remark": "",
            "transaction_count": "0",
            "payment_count": "0",
        },
        follow_redirects=False,
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "需要填写产品类型" in body
