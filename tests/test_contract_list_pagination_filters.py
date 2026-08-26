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


def test_invoice_status_filters_use_cumulative_invoice_amount(app, client, login, base_data):
    """开票筛选应与累计金额状态标签保持一致。"""
    with app.app_context():
        partial_contract = ContractService.create_contract(
            {
                "contract_no": "INVOICE-PARTIAL",
                "company_name": "Invoice Filter Corp",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": base_data["owner_user_id"],
            },
            [{
                "product_code": "IP-001",
                "product_name": "Partial Product",
                "product_model": "M1",
                "product_type": "TypeA",
                "quantity": 10,
                "unit": "pcs",
                "price": 10,
                "remark": "",
            }],
        )
        full_contract = ContractService.create_contract(
            {
                "contract_no": "INVOICE-FULL",
                "company_name": "Invoice Filter Corp",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": base_data["owner_user_id"],
            },
            [{
                "product_code": "IF-001",
                "product_name": "Full Product",
                "product_model": "M1",
                "product_type": "TypeA",
                "quantity": 10,
                "unit": "pcs",
                "price": 10,
                "remark": "",
            }],
        )
        not_invoiced_contract = ContractService.create_contract(
            {
                "contract_no": "INVOICE-NONE",
                "company_name": "Invoice Filter Corp",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": base_data["owner_user_id"],
            },
            [{
                "product_code": "IN-001",
                "product_name": "No Invoice Product",
                "product_model": "M1",
                "product_type": "TypeA",
                "quantity": 10,
                "unit": "pcs",
                "price": 10,
                "remark": "",
            }],
        )

        ContractService.add_payment_record(
            partial_contract.id,
            {
                "payment_amount": 50,
                "invoice_amount": 50,
                "payment_date": "2026-04-05",
                "invoice_date": "2026-04-05",
                "handler": "Finance",
                "remark": "partial",
                "contract_product_id": partial_contract.contract_products[0].id,
            },
        )
        ContractService.add_payment_record(
            full_contract.id,
            {
                "payment_amount": 100,
                "invoice_amount": 100,
                "payment_date": "2026-04-05",
                "invoice_date": "2026-04-05",
                "handler": "Finance",
                "remark": "full",
                "contract_product_id": full_contract.contract_products[0].id,
            },
        )

        partial_ids = {
            contract.id
            for contract in ContractService.get_contract_list(
                per_page=20,
                invoice_statuses=["partial"],
            ).items
        }
        invoiced_ids = {
            contract.id
            for contract in ContractService.get_contract_list(
                per_page=20,
                invoice_statuses=["invoiced"],
            ).items
        }
        not_invoiced_ids = {
            contract.id
            for contract in ContractService.get_contract_list(
                per_page=20,
                invoice_statuses=["not_invoiced"],
            ).items
        }

        assert partial_contract.id in partial_ids
        assert full_contract.id in invoiced_ids
        assert not_invoiced_contract.id in not_invoiced_ids
        assert partial_contract.id not in invoiced_ids
        assert partial_contract.id not in not_invoiced_ids

    login(base_data["superadmin_id"])
    response = client.get("/contract/list?invoice_status=partial")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "INVOICE-PARTIAL" in page
    assert "部分开票" in page
    assert "INVOICE-FULL" not in page
