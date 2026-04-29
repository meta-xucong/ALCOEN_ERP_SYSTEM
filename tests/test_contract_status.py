"""Status transition tests for contract completion logic."""

from __future__ import annotations

from app.services.contract_service import ContractService


def _create_status_contract(owner_user_id: int):
    """Create a contract used for status checks."""
    contract = ContractService.create_contract(
        {
            "contract_no": f"STATUS-CONTRACT-{owner_user_id}",
            "company_name": "Status Corp",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Sales Owner",
            "created_by_id": owner_user_id,
        },
        [
            {
                "product_code": "STATUS-001",
                "product_name": "Status Product",
                "product_model": "SM1",
                "product_type": "TypeS",
                "quantity": 10,
                "unit": "pcs",
                "price": 10,
                "remark": "",
            }
        ],
    )
    return contract, contract.contract_products[0]


def test_check_completion_status_flow(app, base_data):
    """Delivery/payment/contract statuses should move pending -> partial -> completed."""
    from app.models import Contract

    with app.app_context():
        contract, cp = _create_status_contract(base_data["owner_user_id"])
        contract_id = contract.id

        ContractService.check_completion(contract_id)
        contract = Contract.query.get(contract_id)
        assert contract.delivery_status == "pending"
        assert contract.payment_status == "pending"
        assert contract.status == "pending"

        ContractService.add_transaction(
            contract_id,
            {
                "contract_product_id": cp.id,
                "quantity": 5,
                "unit": "pcs",
                "price_with_tax": 10,
                "handler": "Logistics A",
                "delivery_date": "2026-04-01",
                "invoice_date": "",
                "remark": "",
            },
            is_new=True,
        )
        contract = Contract.query.get(contract_id)
        assert contract.delivery_status == "partial"
        assert contract.payment_status == "pending"
        assert contract.status == "pending"

        ContractService.add_payment_record(
            contract_id,
            {
                "payment_amount": 30,
                "payment_date": "2026-04-02",
                "handler": "Finance A",
                "remark": "",
                "contract_product_id": cp.id,
            },
        )
        contract = Contract.query.get(contract_id)
        assert contract.delivery_status == "partial"
        assert contract.payment_status == "partial"
        assert contract.status == "pending"

        ContractService.add_transaction(
            contract_id,
            {
                "contract_product_id": cp.id,
                "quantity": 5,
                "unit": "pcs",
                "price_with_tax": 10,
                "handler": "Logistics B",
                "delivery_date": "2026-04-03",
                "invoice_date": "",
                "remark": "",
            },
            is_new=True,
        )
        ContractService.add_payment_record(
            contract_id,
            {
                "payment_amount": 70,
                "payment_date": "2026-04-03",
                "handler": "Finance B",
                "remark": "",
                "contract_product_id": cp.id,
            },
        )
        contract = Contract.query.get(contract_id)
        assert contract.delivery_status == "completed"
        assert contract.payment_status == "completed"
        assert contract.status == "completed"


def test_invoice_only_record_does_not_complete_payment_status(app, base_data):
    """Invoice-only records should affect invoice status but not payment completion."""
    from app.models import Contract

    with app.app_context():
        contract, cp = _create_status_contract(base_data["owner_user_id"])
        contract_id = contract.id

        ContractService.add_payment_record(
            contract_id,
            {
                "payment_amount": None,
                "invoice_amount": 100,
                "payment_date": "",
                "invoice_date": "2026-04-05",
                "handler": "Finance Invoice",
                "remark": "invoice only",
                "contract_product_id": cp.id,
            },
        )
        contract = Contract.query.get(contract_id)
        assert contract.payment_status == "pending"
        assert contract.status == "pending"
        assert contract.get_invoice_status_display()["text"] == "已开票"
