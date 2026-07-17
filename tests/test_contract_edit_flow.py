"""Integration tests for contract edit flow."""

from __future__ import annotations

import json
from typing import Dict

from app.services.contract_service import ContractService


def _create_contract(owner_user_id: int):
    """Create a baseline contract with one product plan and return (contract, cp)."""
    from app.models import Contract

    contract = ContractService.create_contract(
        {
            "contract_no": f"TEST-CONTRACT-{owner_user_id}",
            "company_name": "Acme Corp",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Sales Owner",
            "created_by_id": owner_user_id,
        },
        [
            {
                "product_code": "CP-001",
                "product_name": "Core Product",
                "product_model": "M1",
                "product_type": "TypeA",
                "quantity": 100,
                "unit": "pcs",
                "price": 10,
                "remark": "",
            }
        ],
    )
    contract = Contract.query.get(contract.id)
    return contract, contract.contract_products[0]


def _base_edit_form(contract, cp) -> Dict[str, str]:
    """Generate required form fields for edit endpoint."""
    return {
        "contract_no": contract.contract_no,
        "company_name": contract.company_name,
        "owner": contract.owner or "",
        "department": contract.department or "",
        "manager": contract.manager or "",
        "product_count": "1",
        "product_0_id": str(cp.id),
        "product_0_code": cp.product_code,
        "product_0_name": cp.product_name or "",
        "product_0_model": cp.product_model or "",
        "product_0_type": cp.product_type or "",
        "product_0_quantity": str(cp.quantity),
        "product_0_unit": cp.unit,
        "product_0_price": str(cp.price),
        "product_0_total": str(cp.total),
        "product_0_remark": cp.remark or "",
    }


def test_edit_contract_preserves_four_decimal_product_price(app, client, login, base_data):
    """Product plan unit prices can be saved to four decimal places."""
    from app.models import Contract, ContractProduct

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        contract_id = contract.id
        cp_id = cp.id
        form_data = _base_edit_form(contract, cp)

    login(base_data["superadmin_id"])
    form_data.update(
        {
            "product_0_quantity": "3",
            "product_0_price": "33.3333",
            "product_0_total": "100.00",
            "transaction_count": "0",
            "payment_count": "0",
        }
    )

    resp = client.post(f"/contract/{contract_id}/edit", data=form_data, follow_redirects=False)
    assert resp.status_code in (302, 303)

    with app.app_context():
        cp = ContractProduct.query.get(cp_id)
        contract = Contract.query.get(contract_id)
        assert round(float(cp.price), 4) == 33.3333
        assert round(float(cp.total), 2) == 100.00
        assert round(float(contract.total_value), 2) == 100.00


def test_edit_contract_preserves_duplicate_product_plans_and_remarks(app, client, login, base_data):
    """同一产品编码的多条计划应分别保存，连续编辑不能丢失各自行备注。"""
    from app.models import Contract, ContractProduct

    with app.app_context():
        contract = ContractService.create_contract(
            {
                "contract_no": f"TEST-DUPLICATE-REMARK-{base_data['owner_user_id']}",
                "company_name": "Acme Corp",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": base_data["owner_user_id"],
            },
            [
                {
                    "product_code": "DUP-001",
                    "product_name": "同一产品",
                    "product_model": "M1",
                    "product_type": "TypeA",
                    "quantity": 10,
                    "unit": "pcs",
                    "price": 10,
                    "remark": "第一批备注",
                },
                {
                    "product_code": "DUP-001",
                    "product_name": "同一产品",
                    "product_model": "M1",
                    "product_type": "TypeA",
                    "quantity": 20,
                    "unit": "pcs",
                    "price": 10,
                    "remark": "第二批备注",
                },
            ],
        )
        products = ContractProduct.query.filter_by(contract_id=contract.id).order_by(ContractProduct.id).all()
        assert len(products) == 2
        contract_id = contract.id
        first_id, second_id = products[0].id, products[1].id
        contract_no = contract.contract_no
        company_name = contract.company_name
        owner = contract.owner or ""
        department = contract.department or ""
        manager = contract.manager or ""

    login(base_data["superadmin_id"])
    form_data = {
        "contract_no": contract_no,
        "company_name": company_name,
        "owner": owner,
        "department": department,
        "manager": manager,
        "product_count": "2",
        "product_0_id": str(first_id),
        "product_0_code": "DUP-001",
        "product_0_name": "同一产品",
        "product_0_model": "M1",
        "product_0_type": "TypeA",
        "product_0_quantity": "11",
        "product_0_unit": "pcs",
        "product_0_price": "10",
        "product_0_total": "110",
        "product_0_remark": "第一批备注-第一次编辑",
        "product_1_id": str(second_id),
        "product_1_code": "DUP-001",
        "product_1_name": "同一产品",
        "product_1_model": "M1",
        "product_1_type": "TypeA",
        "product_1_quantity": "21",
        "product_1_unit": "pcs",
        "product_1_price": "10",
        "product_1_total": "210",
        "product_1_remark": "第二批备注-第一次编辑",
        "transaction_count": "0",
        "payment_count": "0",
    }

    response = client.post(
        f"/contract/{contract_id}/edit",
        data=form_data,
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    with app.app_context():
        products = ContractProduct.query.filter_by(contract_id=contract_id).order_by(ContractProduct.id).all()
        assert [product.id for product in products] == [first_id, second_id]
        assert [product.remark for product in products] == [
            "第一批备注-第一次编辑",
            "第二批备注-第一次编辑",
        ]

    # 第二次提交模拟再次打开编辑页后保存，备注仍应由各自产品计划保留。
    form_data["product_0_remark"] = "第一批备注-第二次编辑"
    form_data["product_1_remark"] = "第二批备注-第二次编辑"
    response = client.post(
        f"/contract/{contract_id}/edit",
        data=form_data,
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    with app.app_context():
        products = ContractProduct.query.filter_by(contract_id=contract_id).order_by(ContractProduct.id).all()
        assert len(products) == 2
        assert [product.remark for product in products] == [
            "第一批备注-第二次编辑",
            "第二批备注-第二次编辑",
        ]


def test_edit_contract_matches_duplicate_product_plans_without_row_ids(
    app, client, login, base_data
):
    """旧前端未提交行ID时，也要按同编码的未占用记录逐条匹配。"""
    from app.models import ContractProduct

    with app.app_context():
        contract = ContractService.create_contract(
            {
                "contract_no": f"TEST-DUPLICATE-FALLBACK-{base_data['owner_user_id']}",
                "company_name": "Acme Corp",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": base_data["owner_user_id"],
            },
            [
                {
                    "product_code": "DUP-002",
                    "product_name": "同一产品",
                    "quantity": 10,
                    "unit": "pcs",
                    "price": 10,
                    "remark": "旧备注1",
                },
                {
                    "product_code": "DUP-002",
                    "product_name": "同一产品",
                    "quantity": 20,
                    "unit": "pcs",
                    "price": 10,
                    "remark": "旧备注2",
                },
            ],
        )
        products = ContractProduct.query.filter_by(contract_id=contract.id).order_by(ContractProduct.id).all()
        contract_id = contract.id
        contract_no = contract.contract_no

    login(base_data["superadmin_id"])
    response = client.post(
        f"/contract/{contract_id}/edit",
        data={
            "contract_no": contract_no,
            "company_name": "Acme Corp",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Sales Owner",
            "product_count": "2",
            "product_0_code": "DUP-002",
            "product_0_name": "同一产品",
            "product_0_quantity": "12",
            "product_0_unit": "pcs",
            "product_0_price": "10",
            "product_0_total": "120",
            "product_0_remark": "新备注1",
            "product_1_code": "DUP-002",
            "product_1_name": "同一产品",
            "product_1_quantity": "22",
            "product_1_unit": "pcs",
            "product_1_price": "10",
            "product_1_total": "220",
            "product_1_remark": "新备注2",
            "transaction_count": "0",
            "payment_count": "0",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    with app.app_context():
        products = ContractProduct.query.filter_by(contract_id=contract_id).order_by(ContractProduct.id).all()
        assert len(products) == 2
        assert [product.remark for product in products] == ["新备注1", "新备注2"]


def test_edit_contract_calculates_unit_price_from_product_total(app, client, login, base_data):
    """Submitting a row total without unit price derives the unit price."""
    from app.models import ContractProduct

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        contract_id = contract.id
        cp_id = cp.id
        form_data = _base_edit_form(contract, cp)

    login(base_data["superadmin_id"])
    form_data.update(
        {
            "product_0_quantity": "6",
            "product_0_price": "",
            "product_0_total": "100.00",
            "transaction_count": "0",
            "payment_count": "0",
        }
    )

    resp = client.post(f"/contract/{contract_id}/edit", data=form_data, follow_redirects=False)
    assert resp.status_code in (302, 303)

    with app.app_context():
        cp = ContractProduct.query.get(cp_id)
        assert round(float(cp.price), 4) == 16.6667
        assert round(float(cp.total), 2) == 100.00


def test_edit_contract_adds_transaction_and_payment(app, client, login, base_data):
    """Newly added rows must persist after one edit submission."""
    from app.models import Contract, PaymentRecord, Transaction

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        contract_id = contract.id
        cp_id = cp.id
        cp_code = cp.product_code
        form_data = _base_edit_form(contract, cp)

    login(base_data["superadmin_id"])
    form_data.update(
        {
            "transaction_count": "1",
            "transaction_0_contract_product_id": cp_code,
            "transaction_0_quantity": "20",
            "transaction_0_unit": "pcs",
            "transaction_0_price": "10",
            "transaction_0_handler": "Logistics A",
            "transaction_0_delivery_date": "2026-04-01",
            "transaction_0_invoice_date": "",
            "transaction_0_remark": "new delivery",
            "payment_count": "1",
            "payment_0_amount": "120",
            "payment_0_date": "2026-04-02",
            "payment_0_handler": "Finance A",
            "payment_0_remark": "new payment",
            "payment_0_contract_product_id": cp_code,
        }
    )
    resp = client.post(f"/contract/{contract_id}/edit", data=form_data, follow_redirects=False)

    assert resp.status_code == 302
    assert f"/contract/{contract_id}" in resp.headers.get("Location", "")

    with app.app_context():
        updated_contract = Contract.query.get(contract_id)
        assert len(updated_contract.transactions) == 1
        assert len(updated_contract.payment_records) == 1

        tx = Transaction.query.filter_by(contract_id=contract_id).first()
        assert tx is not None
        assert tx.contract_product_id == cp_id
        assert float(tx.quantity) == 20.0

        pay = PaymentRecord.query.filter_by(contract_id=contract_id).first()
        assert pay is not None
        assert pay.contract_product_id == cp_id
        assert float(pay.payment_amount) == 120.0


def test_edit_contract_keeps_existing_rows_when_adding_new(app, client, login, base_data):
    """Existing rows sent in payload must not be dropped while adding new rows."""
    from app.models import Contract, PaymentRecord, Transaction

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        existing_tx = ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 10,
                "unit": "pcs",
                "price_with_tax": 10,
                "handler": "Old Logistics",
                "delivery_date": "2026-04-03",
                "invoice_date": "",
                "remark": "old tx",
            },
            is_new=True,
        )
        existing_pay = ContractService.add_payment_record(
            contract.id,
            {
                "payment_amount": 50,
                "payment_date": "2026-04-03",
                "handler": "Old Finance",
                "remark": "old pay",
                "contract_product_id": cp.id,
            },
        )
        existing_tx_id = existing_tx.id
        existing_pay_id = existing_pay.id
        contract_id = contract.id
        cp_code = cp.product_code
        form_data = _base_edit_form(contract, cp)

    login(base_data["superadmin_id"])
    form_data.update(
            {
                "transaction_count": "2",
                "transaction_0_id": str(existing_tx_id),
                "transaction_0_contract_product_id": cp_code,
            "transaction_0_quantity": "12",
            "transaction_0_unit": "pcs",
            "transaction_0_price": "10",
            "transaction_0_handler": "Old Logistics Updated",
            "transaction_0_delivery_date": "2026-04-03",
            "transaction_0_invoice_date": "",
            "transaction_0_remark": "old tx updated",
            "transaction_1_contract_product_id": cp_code,
            "transaction_1_quantity": "15",
            "transaction_1_unit": "pcs",
            "transaction_1_price": "10",
            "transaction_1_handler": "New Logistics",
            "transaction_1_delivery_date": "2026-04-04",
            "transaction_1_invoice_date": "",
            "transaction_1_remark": "new tx",
                "payment_count": "2",
                "payment_0_id": str(existing_pay_id),
            "payment_0_amount": "80",
            "payment_0_date": "2026-04-03",
            "payment_0_handler": "Old Finance Updated",
            "payment_0_remark": "old pay updated",
            "payment_0_contract_product_id": cp_code,
            "payment_1_amount": "60",
            "payment_1_date": "2026-04-04",
            "payment_1_handler": "New Finance",
            "payment_1_remark": "new pay",
            "payment_1_contract_product_id": cp_code,
        }
    )
    resp = client.post(f"/contract/{contract_id}/edit", data=form_data, follow_redirects=False)

    assert resp.status_code == 302

    with app.app_context():
        updated_contract = Contract.query.get(contract_id)
        tx_ids = {tx.id for tx in updated_contract.transactions}
        pay_ids = {pay.id for pay in updated_contract.payment_records}

        assert len(updated_contract.transactions) == 2
        assert len(updated_contract.payment_records) == 2
        assert existing_tx_id in tx_ids
        assert existing_pay_id in pay_ids


def test_edit_contract_accepts_invoice_only_payment_record(app, client, login, base_data):
    """Invoice-only rows should persist without requiring payment amount/date/product."""
    from app.models import Contract, PaymentRecord

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        contract_id = contract.id
        form_data = _base_edit_form(contract, cp)

    login(base_data["superadmin_id"])
    form_data.update(
        {
            "transaction_count": "0",
            "payment_count": "1",
            "payment_0_amount": "",
            "payment_0_invoice_amount": "88",
            "payment_0_date": "",
            "payment_0_invoice_date": "2026-04-08",
            "payment_0_handler": "Finance Invoice",
            "payment_0_remark": "invoice only",
            "payment_0_contract_product_id": "",
        }
    )
    resp = client.post(f"/contract/{contract_id}/edit", data=form_data, follow_redirects=False)

    assert resp.status_code == 302

    with app.app_context():
        updated_contract = Contract.query.get(contract_id)
        assert len(updated_contract.payment_records) == 1

        payment = PaymentRecord.query.filter_by(contract_id=contract_id).first()
        assert payment is not None
        assert payment.payment_amount is None
        assert float(payment.invoice_amount) == 88.0
        assert payment.payment_date is None
        assert payment.invoice_date.isoformat() == "2026-04-08"
        assert payment.contract_product_id is None


def test_edit_contract_deletes_only_explicitly_marked_existing_rows(app, client, login, base_data):
    """Only rows explicitly removed in the UI should be deleted."""
    from app.models import Contract

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        existing_tx = ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 5,
                "unit": "pcs",
                "price_with_tax": 10,
                "handler": "To Delete",
                "delivery_date": "2026-04-05",
                "invoice_date": "",
                "remark": "",
            },
            is_new=True,
        )
        ContractService.add_payment_record(
            contract.id,
            {
                "payment_amount": 40,
                "payment_date": "2026-04-05",
                "handler": "To Delete",
                "remark": "",
                "contract_product_id": cp.id,
            },
        )
        contract_id = contract.id
        existing_tx_id = existing_tx.id
        form_data = _base_edit_form(contract, cp)

    login(base_data["superadmin_id"])
    form_data.update(
        {
            "transaction_count": "0",
            "payment_count": "0",
            "deleted_transaction_ids": str(existing_tx_id),
        }
    )
    resp = client.post(f"/contract/{contract_id}/edit", data=form_data, follow_redirects=False)

    assert resp.status_code == 302

    with app.app_context():
        updated_contract = Contract.query.get(contract_id)
        assert len(updated_contract.transactions) == 0
        assert len(updated_contract.payment_records) == 0


def test_edit_contract_rebinds_existing_transaction_to_selected_product(app, client, login, base_data):
    """Existing transaction must persist selected product mapping after edit submit."""
    from app.models import Contract, Transaction

    with app.app_context():
        contract = ContractService.create_contract(
            {
                "contract_no": f"TEST-REBIND-{base_data['owner_user_id']}",
                "company_name": "Acme Corp",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": base_data["owner_user_id"],
            },
            [
                {
                    "product_code": "CP-001",
                    "product_name": "Core Product A",
                    "product_model": "M-A",
                    "product_type": "TypeA",
                    "quantity": 100,
                    "unit": "pcs",
                    "price": 10,
                    "remark": "",
                },
                {
                    "product_code": "CP-002",
                    "product_name": "Core Product B",
                    "product_model": "M-B",
                    "product_type": "TypeB",
                    "quantity": 50,
                    "unit": "box",
                    "price": 20,
                    "remark": "",
                },
            ],
        )
        contract = Contract.query.get(contract.id)
        cp1 = next(cp for cp in contract.contract_products if cp.product_code == "CP-001")
        cp2 = next(cp for cp in contract.contract_products if cp.product_code == "CP-002")
        tx = ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp1.id,
                "quantity": 3,
                "unit": cp1.unit,
                "price_with_tax": cp1.price,
                "handler": "Old Logistics",
                "delivery_date": "2026-04-06",
                "invoice_date": "",
                "remark": "before switch",
            },
            is_new=True,
        )
        contract_id = contract.id
        tx_id = tx.id
        contract_no = contract.contract_no
        company_name = contract.company_name
        owner = contract.owner or ""
        department = contract.department or ""
        manager = contract.manager or ""
        cp1_data = {
            "id": cp1.id,
            "product_code": cp1.product_code,
            "product_name": cp1.product_name or "",
            "product_model": cp1.product_model or "",
            "product_type": cp1.product_type or "",
            "quantity": str(cp1.quantity),
            "unit": cp1.unit,
            "price": str(cp1.price),
            "remark": cp1.remark or "",
        }
        cp2_data = {
            "id": cp2.id,
            "product_code": cp2.product_code,
            "product_name": cp2.product_name or "",
            "product_model": cp2.product_model or "",
            "product_type": cp2.product_type or "",
            "quantity": str(cp2.quantity),
            "unit": cp2.unit,
            "price": str(cp2.price),
            "remark": cp2.remark or "",
        }

    login(base_data["superadmin_id"])
    form_data = {
        "contract_no": contract_no,
        "company_name": company_name,
        "owner": owner,
        "department": department,
        "manager": manager,
        "product_count": "2",
        "product_0_id": str(cp1_data["id"]),
        "product_0_code": cp1_data["product_code"],
        "product_0_name": cp1_data["product_name"],
        "product_0_model": cp1_data["product_model"],
        "product_0_type": cp1_data["product_type"],
        "product_0_quantity": cp1_data["quantity"],
        "product_0_unit": cp1_data["unit"],
        "product_0_price": cp1_data["price"],
        "product_0_remark": cp1_data["remark"],
        "product_1_id": str(cp2_data["id"]),
        "product_1_code": cp2_data["product_code"],
        "product_1_name": cp2_data["product_name"],
        "product_1_model": cp2_data["product_model"],
        "product_1_type": cp2_data["product_type"],
        "product_1_quantity": cp2_data["quantity"],
        "product_1_unit": cp2_data["unit"],
        "product_1_price": cp2_data["price"],
        "product_1_remark": cp2_data["remark"],
        "transaction_count": "1",
        "transaction_0_id": str(tx_id),
        "transaction_0_contract_product_id": cp2_data["product_code"],
        "transaction_0_quantity": "6",
        "transaction_0_unit": cp2_data["unit"],
        "transaction_0_price": cp2_data["price"],
        "transaction_0_handler": "Switched Logistics",
        "transaction_0_delivery_date": "2026-04-06",
        "transaction_0_invoice_date": "",
        "transaction_0_remark": "after switch",
        "payment_count": "0",
    }
    resp = client.post(f"/contract/{contract_id}/edit", data=form_data, follow_redirects=False)

    assert resp.status_code == 302

    with app.app_context():
        updated = Transaction.query.get(tx_id)
        assert updated is not None
        assert updated.contract_product_id == cp2_data["id"]
        assert updated.product_code == cp2_data["product_code"]
        assert updated.product_name == cp2_data["product_name"]
        assert updated.product_model == cp2_data["product_model"]
        assert float(updated.price_with_tax) == float(cp2_data["price"])
        assert updated.unit == cp2_data["unit"]
        assert float(updated.quantity) == 6.0


def test_edit_contract_updates_existing_product_plan_and_transaction_together(app, client, login, base_data):
    """Editing product plan row and existing transaction in one submit should both persist."""
    from app.models import Contract, ContractProduct, Transaction

    with app.app_context():
        contract = ContractService.create_contract(
            {
                "contract_no": f"TEST-SYNC-{base_data['owner_user_id']}",
                "company_name": "Acme Corp",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": base_data["owner_user_id"],
            },
            [
                {
                    "product_code": "SYNC-001",
                    "product_name": "Sync Product",
                    "product_model": "S-1",
                    "product_type": "TypeS",
                    "quantity": 20,
                    "unit": "pcs",
                    "price": 50,
                    "remark": "",
                }
            ],
        )
        contract = Contract.query.get(contract.id)
        cp = contract.contract_products[0]
        tx = ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 2,
                "unit": cp.unit,
                "price_with_tax": cp.price,
                "handler": "Origin Handler",
                "delivery_date": "2026-04-07",
                "invoice_date": "",
                "remark": "before edit",
            },
            is_new=True,
        )
        contract_id = contract.id
        cp_id = cp.id
        tx_id = tx.id

    login(base_data["superadmin_id"])
    form_data = {
        "contract_no": contract.contract_no,
        "company_name": contract.company_name,
        "owner": contract.owner or "",
        "department": contract.department or "",
        "manager": contract.manager or "",
        "product_count": "1",
        "product_0_id": str(cp_id),
        "product_0_code": "SYNC-001",
        "product_0_name": "Sync Product Updated",
        "product_0_model": "S-2",
        "product_0_type": "TypeS",
        "product_0_quantity": "30",
        "product_0_unit": "box",
        "product_0_price": "60",
        "product_0_remark": "product edited",
        "transaction_count": "1",
        "transaction_0_id": str(tx_id),
        "transaction_0_contract_product_id": "SYNC-001",
        "transaction_0_quantity": "5",
        "transaction_0_unit": "box",
        "transaction_0_price": "60",
        "transaction_0_handler": "Updated Handler",
        "transaction_0_delivery_date": "2026-04-08",
        "transaction_0_invoice_date": "",
        "transaction_0_remark": "tx edited",
        "payment_count": "0",
    }
    resp = client.post(f"/contract/{contract_id}/edit", data=form_data, follow_redirects=False)

    assert resp.status_code == 302

    with app.app_context():
        updated_cp = ContractProduct.query.get(cp_id)
        updated_tx = Transaction.query.get(tx_id)
        assert updated_cp is not None
        assert updated_tx is not None
        assert updated_cp.product_name == "Sync Product Updated"
        assert updated_cp.product_model == "S-2"
        assert float(updated_cp.quantity) == 30.0
        assert updated_cp.unit == "box"
        assert float(updated_cp.price) == 60.0
        assert float(updated_tx.quantity) == 5.0
        assert updated_tx.unit == "box"
        assert float(updated_tx.price_with_tax) == 60.0
        assert updated_tx.handler == "Updated Handler"


def test_logistics_edit_submit_with_autofill_payload_completes_delivery_status(app, client, login, base_data):
    """Logistics submit should close delivery status when payload fills the remaining quantity."""
    from app import db
    from app.models import Contract, PaymentRecord, Role, Transaction, User

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        existing_tx = ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 30,
                "unit": cp.unit,
                "price_with_tax": cp.price,
                "handler": "Logistics Partial",
                "delivery_date": "2026-04-09",
                "invoice_date": "",
                "remark": "existing partial",
            },
            is_new=True,
        )
        contract = Contract.query.get(contract.id)
        assert contract.delivery_status == "partial"

        logistics_role = Role.query.filter_by(code="logistics_manager").first()
        if logistics_role is None:
            logistics_role = Role(
                name="Logistics Manager",
                code="logistics_manager",
                permissions=json.dumps(["contract_view", "contract_edit_delivery"]),
                level=60,
            )
            db.session.add(logistics_role)
            db.session.flush()

        logistics_user = User(
            username="logistics_fill_submit",
            password_hash="x",
            real_name="Logistics Fill",
            role_id=logistics_role.id,
            department_id=None,
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        db.session.add(logistics_user)
        db.session.commit()

        contract_id = contract.id
        existing_tx_id = existing_tx.id
        cp_code = cp.product_code
        cp_quantity = float(cp.quantity)
        cp_unit = cp.unit
        cp_price = float(cp.price)
        remaining_qty = cp_quantity - float(existing_tx.quantity)
        logistics_user_id = logistics_user.id

    login(logistics_user_id)
    resp = client.post(
        f"/contract/{contract_id}/logistics-edit",
        data={
            "transaction_count": "2",
            "transaction_0_id": str(existing_tx_id),
            "transaction_0_contract_product_id": cp_code,
            "transaction_0_quantity": "30",
            "transaction_0_unit": cp_unit,
            "transaction_0_price": str(cp_price),
            "transaction_0_handler": "Logistics Partial",
            "transaction_0_delivery_date": "2026-04-09",
            "transaction_0_remark": "existing partial",
            "transaction_1_contract_product_id": cp_code,
            "transaction_1_quantity": str(remaining_qty),
            "transaction_1_unit": cp_unit,
            "transaction_1_price": str(cp_price),
            "transaction_1_handler": "Logistics Fill",
            "transaction_1_delivery_date": "2026-04-10",
            "transaction_1_remark": "autofill remainder",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert f"/contract/{contract_id}" in resp.headers.get("Location", "")

    with app.app_context():
        updated_contract = Contract.query.get(contract_id)
        assert updated_contract is not None
        assert updated_contract.delivery_status == "completed"
        assert updated_contract.payment_status == "pending"
        assert updated_contract.status == "pending"

        transactions = Transaction.query.filter_by(contract_id=contract_id).all()
        assert len(transactions) == 2
        delivered_total = round(sum(float(tx.quantity) for tx in transactions), 2)
        assert delivered_total == round(cp_quantity, 2)
        assert PaymentRecord.query.filter_by(contract_id=contract_id).count() == 0


def test_logistics_edit_does_not_delete_history_when_existing_id_is_missing(
    app, client, login, base_data
):
    """A malformed payload must not turn a missing row ID into data loss."""
    from app import db
    from app.models import Contract, Role, Transaction, User

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        existing_tx = ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 30,
                "unit": "pcs",
                "price_with_tax": cp.price,
                "handler": "Original Logistics",
                "delivery_date": "2026-04-12",
                "invoice_date": "",
                "remark": "original history",
            },
            is_new=True,
        )

        logistics_role = Role.query.filter_by(code="logistics_manager").first()
        if logistics_role is None:
            logistics_role = Role(
                name="Logistics Manager",
                code="logistics_manager",
                permissions=json.dumps(["contract_view", "contract_edit_delivery"]),
                level=60,
            )
            db.session.add(logistics_role)
            db.session.flush()

        logistics_user = User(
            username="logistics_missing_id",
            password_hash="x",
            real_name="Logistics Missing ID",
            role_id=logistics_role.id,
            department_id=None,
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        db.session.add(logistics_user)
        db.session.commit()

        contract_id = contract.id
        existing_tx_id = existing_tx.id
        cp_code = cp.product_code
        cp_unit = cp.unit
        cp_price = float(cp.price)
        logistics_user_id = logistics_user.id

    login(logistics_user_id)
    response = client.post(
        f"/contract/{contract_id}/logistics-edit",
        data={
            "transaction_count": "1",
            "transaction_0_contract_product_id": cp_code,
            "transaction_0_quantity": "70",
            "transaction_0_unit": cp_unit,
            "transaction_0_price": str(cp_price),
            "transaction_0_handler": "New Logistics",
            "transaction_0_delivery_date": "2026-04-13",
            "transaction_0_remark": "new history",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        updated_contract = Contract.query.get(contract_id)
        transactions = Transaction.query.filter_by(
            contract_id=contract_id
        ).order_by(Transaction.id.asc()).all()

        assert updated_contract.delivery_status == "completed"
        assert len(transactions) == 2
        assert transactions[0].id == existing_tx_id
        assert transactions[0].remark == "original history"
        assert float(transactions[0].quantity) == 30.0
        assert transactions[1].remark == "new history"
        assert float(transactions[1].quantity) == 70.0


def test_edit_contract_preserves_same_day_delivery_history_and_recalculates_status(
    app, client, login, base_data
):
    """Adding a same-day shipment must keep the old row and complete delivery."""
    from app.models import Contract, Transaction

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        existing_tx = ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 40,
                "unit": "pcs",
                "price_with_tax": 10,
                "handler": "Original Handler",
                "delivery_date": "2026-04-11",
                "invoice_date": "",
                "remark": "original delivery",
            },
            is_new=True,
        )
        contract_id = contract.id
        existing_tx_id = existing_tx.id
        form_data = _base_edit_form(contract, cp)

    login(base_data["superadmin_id"])
    form_data.update(
        {
            "transaction_count": "2",
            "transaction_0_id": str(existing_tx_id),
            "transaction_0_contract_product_id": cp.product_code,
            "transaction_0_quantity": "40",
            "transaction_0_unit": "pcs",
            "transaction_0_price": "10",
            "transaction_0_handler": "Original Handler",
            "transaction_0_delivery_date": "2026-04-11",
            "transaction_0_invoice_date": "",
            "transaction_0_remark": "original delivery",
            "transaction_1_contract_product_id": cp.product_code,
            "transaction_1_quantity": "60",
            "transaction_1_unit": "pcs",
            "transaction_1_price": "10",
            "transaction_1_handler": "New Handler",
            "transaction_1_delivery_date": "2026-04-11",
            "transaction_1_invoice_date": "",
            "transaction_1_remark": "new delivery",
            "payment_count": "0",
        }
    )

    response = client.post(
        f"/contract/{contract_id}/edit",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        updated_contract = Contract.query.get(contract_id)
        transactions = Transaction.query.filter_by(
            contract_id=contract_id
        ).order_by(Transaction.id.asc()).all()

        assert updated_contract.delivery_status == "completed"
        assert len(transactions) == 2
        assert transactions[0].id == existing_tx_id
        assert float(transactions[0].quantity) == 40.0
        assert transactions[0].remark == "original delivery"
        assert float(transactions[1].quantity) == 60.0
        assert transactions[1].remark == "new delivery"


def test_edit_contract_preserves_invoice_date_when_legacy_payload_omits_field(
    app, client, login, base_data
):
    """Old clients that omit invoice_date must not erase the saved value."""
    from app.models import Transaction

    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        transaction = ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 10,
                "unit": "pcs",
                "price_with_tax": 10,
                "handler": "Original Handler",
                "delivery_date": "2026-04-14",
                "invoice_date": "2026-04-15",
                "remark": "invoice date retained",
            },
            is_new=True,
        )
        contract_id = contract.id
        cp_id = cp.id
        transaction_id = transaction.id
        form_data = _base_edit_form(contract, cp)

    login(base_data["superadmin_id"])
    form_data.update(
        {
            "transaction_count": "1",
            "transaction_0_id": str(transaction_id),
            "transaction_0_contract_product_id": cp.product_code,
            "transaction_0_quantity": "10",
            "transaction_0_unit": "pcs",
            "transaction_0_price": "10",
            "transaction_0_handler": "Updated Handler",
            "transaction_0_delivery_date": "2026-04-14",
            # Intentionally omit transaction_0_invoice_date.
            "transaction_0_remark": "updated",
            "payment_count": "0",
        }
    )

    response = client.post(
        f"/contract/{contract_id}/edit",
        data=form_data,
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        transaction = Transaction.query.get(transaction_id)
        assert transaction.invoice_date.isoformat() == "2026-04-15"


def test_edit_contract_keeps_duplicate_product_transaction_and_payment_links_separate(
    app, client, login, base_data
):
    """Explicit row references keep duplicate product plans from sharing records."""
    from app.models import Contract, ContractProduct, PaymentRecord, Transaction

    with app.app_context():
        contract = ContractService.create_contract(
            {
                "contract_no": f"TEST-DUPLICATE-LINK-{base_data['owner_user_id']}",
                "company_name": "Acme Corp",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": base_data["owner_user_id"],
            },
            [
                {
                    "product_code": "DUP-LINK",
                    "product_name": "Shared Code",
                    "quantity": 10,
                    "unit": "pcs",
                    "price": 10,
                    "remark": "first plan",
                },
                {
                    "product_code": "DUP-LINK",
                    "product_name": "Shared Code",
                    "quantity": 20,
                    "unit": "pcs",
                    "price": 10,
                    "remark": "second plan",
                },
            ],
        )
        products = ContractProduct.query.filter_by(
            contract_id=contract.id
        ).order_by(ContractProduct.id.asc()).all()
        transaction = ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": products[1].id,
                "quantity": 5,
                "unit": "pcs",
                "price_with_tax": 10,
                "handler": "Original Handler",
                "delivery_date": "2026-04-16",
                "invoice_date": "",
                "remark": "second plan shipment",
            },
            is_new=True,
        )
        payment = ContractService.add_payment_record(
            contract.id,
            {
                "contract_product_id": products[1].id,
                "payment_amount": 50,
                "invoice_amount": 0,
                "payment_date": "2026-04-17",
                "handler": "Original Finance",
                "remark": "second plan payment",
            },
        )
        contract_id = contract.id
        first_id, second_id = products[0].id, products[1].id
        transaction_id, payment_id = transaction.id, payment.id

    login(base_data["superadmin_id"])
    response = client.post(
        f"/contract/{contract_id}/edit",
        data={
            "contract_no": f"TEST-DUPLICATE-LINK-{base_data['owner_user_id']}",
            "company_name": "Acme Corp",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Sales Owner",
            "product_count": "2",
            "product_0_id": str(first_id),
            "product_0_code": "DUP-LINK",
            "product_0_name": "Shared Code",
            "product_0_quantity": "10",
            "product_0_unit": "pcs",
            "product_0_price": "10",
            "product_0_total": "100",
            "product_0_remark": "first plan",
            "product_1_id": str(second_id),
            "product_1_code": "DUP-LINK",
            "product_1_name": "Shared Code",
            "product_1_quantity": "20",
            "product_1_unit": "pcs",
            "product_1_price": "10",
            "product_1_total": "200",
            "product_1_remark": "second plan",
            "transaction_count": "2",
            "transaction_0_id": str(transaction_id),
            "transaction_0_contract_product_id": "DUP-LINK",
            "transaction_0_contract_product_ref": "row:1",
            "transaction_0_quantity": "5",
            "transaction_0_unit": "pcs",
            "transaction_0_price": "10",
            "transaction_0_handler": "Updated Handler",
            "transaction_0_delivery_date": "2026-04-16",
            "transaction_0_invoice_date": "",
            "transaction_0_remark": "second plan shipment",
            "transaction_1_contract_product_id": "DUP-LINK",
            "transaction_1_contract_product_ref": "row:0",
            "transaction_1_quantity": "10",
            "transaction_1_unit": "pcs",
            "transaction_1_price": "10",
            "transaction_1_handler": "First Handler",
            "transaction_1_delivery_date": "2026-04-18",
            "transaction_1_invoice_date": "",
            "transaction_1_remark": "first plan shipment",
            "payment_count": "1",
            "payment_0_id": str(payment_id),
            "payment_0_amount": "50",
            "payment_0_invoice_amount": "0",
            "payment_0_date": "2026-04-17",
            "payment_0_invoice_date": "",
            "payment_0_handler": "Updated Finance",
            "payment_0_remark": "second plan payment",
            "payment_0_contract_product_id": "DUP-LINK",
            "payment_0_contract_product_ref": "row:1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        transaction = Transaction.query.get(transaction_id)
        new_transaction = Transaction.query.filter(
            Transaction.contract_id == contract_id,
            Transaction.id != transaction_id,
        ).first()
        payment = PaymentRecord.query.get(payment_id)

        assert transaction.contract_product_id == second_id
        assert new_transaction.contract_product_id == first_id
        assert payment.contract_product_id == second_id


def test_contract_edit_page_rehydrates_invoice_date_and_product_reference_fields(
    app, client, login, base_data
):
    """The edit page must render every field needed for a lossless round trip."""
    with app.app_context():
        contract, cp = _create_contract(base_data["owner_user_id"])
        ContractService.add_transaction(
            contract.id,
            {
                "contract_product_id": cp.id,
                "quantity": 5,
                "unit": "pcs",
                "price_with_tax": 10,
                "handler": "Template Check",
                "delivery_date": "2026-04-19",
                "invoice_date": "2026-04-20",
                "remark": "template check",
            },
            is_new=True,
        )
        contract_id = contract.id
        cp_id = cp.id

    login(base_data["superadmin_id"])
    response = client.get(f"/contract/{contract_id}/edit")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'name="transaction_{index}_invoice_date"' in body
    assert 'name="transaction_{index}_contract_product_ref"' in body
    assert 'invoice_date:' in body
    assert '2026-04-20' in body
    assert 'contract_product_id:' in body
    assert str(cp_id) in body
