"""Regression tests for contract list pagination filters."""

from __future__ import annotations

from datetime import datetime, timedelta

from app import db
from app.services.contract_service import ContractService


def _seed_paginated_payment_status_contracts(app, owner_user_id: int) -> None:
    """Create enough contracts to exercise page 2 with multi-status filters."""
    base_time = datetime(2026, 1, 1, 12, 0, 0)

    with app.app_context():
        for idx in range(21):
            contract = ContractService.create_contract(
                {
                    "contract_no": f"PAY-PAG-{idx:03d}",
                    "company_name": "Pagination Corp",
                    "owner": "Sales - Owner",
                    "department": "Sales",
                    "manager": "Sales Owner",
                    "created_by_id": owner_user_id,
                },
                [
                    {
                        "product_code": f"PP-{idx:03d}",
                        "product_name": f"Product {idx:03d}",
                        "product_model": "M1",
                        "product_type": "TypeA",
                        "quantity": 10,
                        "unit": "pcs",
                        "price": 10,
                        "remark": "",
                    }
                ],
            )
            contract.payment_status = "completed" if idx % 2 == 0 else "pending"
            contract.created_at = base_time + timedelta(minutes=idx)

        db.session.commit()


def test_contract_list_accepts_csv_multi_value_filters_on_page_two(app, client, login, base_data):
    """分页链接带 CSV 形式的多选状态时，第二页仍应保持筛选结果。"""
    _seed_paginated_payment_status_contracts(app, base_data["owner_user_id"])

    login(base_data["superadmin_id"])
    repeated_resp = client.get(
        "/contract/list?page=2&payment_status=completed&payment_status=pending"
    )
    csv_resp = client.get("/contract/list?page=2&payment_status=completed,pending")

    assert repeated_resp.status_code == 200
    assert csv_resp.status_code == 200
    assert "PAY-PAG-000" in repeated_resp.get_data(as_text=True)
    assert "PAY-PAG-000" in csv_resp.get_data(as_text=True)
