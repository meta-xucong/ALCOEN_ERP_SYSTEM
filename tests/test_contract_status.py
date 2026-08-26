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


def test_invoice_status_tracks_cumulative_invoice_amount(app, base_data):
    """A contract remains partially invoiced until all invoice records add up."""
    from app.models import Contract

    with app.app_context():
        contract, cp = _create_status_contract(base_data["owner_user_id"])
        contract_id = contract.id

        ContractService.add_payment_record(
            contract_id,
            {
                "payment_amount": 40,
                "invoice_amount": 40,
                "payment_date": "2026-04-05",
                "invoice_date": "2026-04-05",
                "handler": "Finance Invoice A",
                "remark": "first invoice",
                "contract_product_id": cp.id,
            },
        )
        contract = Contract.query.get(contract_id)
        assert contract.get_invoice_summary() == {
            "status": "partial",
            "target_amount": 100.0,
            "invoiced_amount": 40.0,
        }
        assert contract.get_invoice_status_display()["text"] == "部分开票"

        ContractService.add_payment_record(
            contract_id,
            {
                "payment_amount": 60,
                "invoice_amount": 60,
                "payment_date": "2026-04-06",
                "invoice_date": "2026-04-06",
                "handler": "Finance Invoice B",
                "remark": "second invoice",
                "contract_product_id": cp.id,
            },
        )
        contract = Contract.query.get(contract_id)
        assert contract.get_invoice_summary()["invoiced_amount"] == 100.0
        assert contract.get_invoice_status_display()["text"] == "已开票"


def test_invoice_status_uses_legacy_transaction_amount_when_needed(app, base_data):
    """Historical transaction invoice dates should still report partial invoices accurately."""
    from app.models import Contract

    with app.app_context():
        contract, cp = _create_status_contract(base_data["owner_user_id"])
        ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 4,
                "unit": "pcs",
                "price_with_tax": 10,
                "handler": "Legacy Finance",
                "delivery_date": "2026-04-05",
                "invoice_date": "2026-04-05",
                "remark": "legacy invoice",
            },
            is_new=True,
        )

        contract = Contract.query.get(contract.id)
        assert contract.get_invoice_summary()["invoiced_amount"] == 40.0
        assert contract.get_invoice_status_display()["text"] == "部分开票"


def test_zero_payment_and_invoice_record_marks_contract_as_not_required(app, base_data):
    """A 0/0 payment record explicitly marks giveaway contracts as no payment/invoice required."""
    from app.models import Contract

    with app.app_context():
        contract, cp = _create_status_contract(base_data["owner_user_id"])
        contract_id = contract.id

        ContractService.add_payment_record(
            contract_id,
            {
                "payment_amount": 0,
                "invoice_amount": 0,
                "payment_date": "",
                "invoice_date": "",
                "handler": "Finance Gift",
                "remark": "gift",
                "contract_product_id": cp.id,
            },
        )
        contract = Contract.query.get(contract_id)
        assert contract.payment_status == "completed"
        assert contract.get_payment_status_display()["text"] == "不需要回款"
        assert contract.get_invoice_status_display()["text"] == "不需要开票"
        assert contract.payment_records[0].status_flags == ["不需要回款/开票"]
