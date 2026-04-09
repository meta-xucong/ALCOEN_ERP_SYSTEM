"""Contract service edge case tests."""

from __future__ import annotations

import pytest

from app.services.contract_service import ContractService


def _make_contract(owner_user_id: int):
    contract = ContractService.create_contract(
        {
            "contract_no": f"EDGE-{owner_user_id}",
            "company_name": "Edge Corp",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Sales Owner",
            "created_by_id": owner_user_id,
        },
        [
            {
                "product_code": "EDGE-001",
                "product_name": "Edge Product",
                "product_model": "E1",
                "product_type": "TypeE",
                "quantity": 10,
                "unit": "pcs",
                "price": 11,
                "remark": "",
            }
        ],
    )
    return contract, contract.contract_products[0]


def test_add_payment_record_accepts_product_code_reference(app, base_data):
    """Payment API should resolve contract_product_id from product code."""
    from app.models import PaymentRecord

    with app.app_context():
        contract, cp = _make_contract(base_data["owner_user_id"])
        payment = ContractService.add_payment_record(
            contract.id,
            {
                "payment_amount": 22,
                "payment_date": "2026-04-01",
                "handler": "Finance",
                "remark": "",
                "contract_product_id": cp.product_code,
            },
        )
        fetched = PaymentRecord.query.get(payment.id)
        assert fetched.contract_product_id == cp.id


def test_add_transaction_rejects_over_delivery_quantity(app, base_data):
    """Cannot add a new transaction beyond remaining planned quantity."""
    with app.app_context():
        contract, cp = _make_contract(base_data["owner_user_id"])
        ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 10,
                "unit": "pcs",
                "price_with_tax": 11,
                "handler": "Logistics",
                "delivery_date": "2026-04-01",
                "invoice_date": "",
                "remark": "",
            },
            is_new=True,
        )

        with pytest.raises(ValueError, match="剩余未发数量"):
            ContractService.add_transaction(
                contract.id,
                {
                    "contract_product_id": cp.id,
                    "quantity": 1,
                    "unit": "pcs",
                    "price_with_tax": 11,
                    "handler": "Logistics",
                    "delivery_date": "2026-04-02",
                    "invoice_date": "",
                    "remark": "",
                },
                is_new=True,
            )


def test_add_transaction_requires_handler(app, base_data):
    """Handler is mandatory for transaction records."""
    with app.app_context():
        contract, cp = _make_contract(base_data["owner_user_id"])
        with pytest.raises(ValueError, match="经手人不能为空"):
            ContractService.add_transaction(
                contract.id,
                {
                    "contract_product_id": cp.id,
                    "quantity": 1,
                    "unit": "pcs",
                    "price_with_tax": 11,
                    "handler": "",
                    "delivery_date": "2026-04-02",
                    "invoice_date": "",
                    "remark": "",
                },
                is_new=True,
            )
