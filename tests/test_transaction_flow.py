"""Transaction route regression tests."""

from __future__ import annotations

from datetime import date


def _create_product():
    """Create one product for transaction flow tests."""
    from app.services.product_service import ProductService

    return ProductService.create_product(
        product_code="TXFLOW-001",
        product_name="TxFlow Product",
        product_model="TF1",
        product_type="TypeT",
        default_price=99.0,
        remark="",
    )


def test_new_transaction_route_creates_record(app, client, login, base_data):
    """Posting /transaction/new should persist a transaction row."""
    from app.models import Transaction

    with app.app_context():
        product = _create_product()
        product_id = product.id

    login(base_data["superadmin_id"])
    resp = client.post(
        "/transaction/new",
        data={
            "company_name": "Acme Tx",
            "product_select_mode": "existing",
            "product_id": str(product_id),
            "product_code": "TXFLOW-001",
            "product_name": "TxFlow Product",
            "product_model": "TF1",
            "product_type": "TypeT",
            "quantity": "3",
            "unit": "pcs",
            "price_with_tax": "99",
            "delivery_date": "2026-04-08",
            "invoice_date": "",
            "payment_date": "",
            "contract_no": "T-001",
            "remark": "route create",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/transaction/" in resp.headers.get("Location", "")

    with app.app_context():
        tx = Transaction.query.filter_by(company_name="Acme Tx", product_code="TXFLOW-001").first()
        assert tx is not None
        assert float(tx.quantity) == 3.0
        assert tx.handler == "系统录入"


def test_edit_transaction_route_updates_record(app, client, login, base_data):
    """Posting /transaction/<id>/edit should update transaction fields."""
    from app.services.transaction_service import TransactionService
    from app.models import Transaction

    with app.app_context():
        product = _create_product()
        tx = TransactionService.create_transaction(
            {
                "company_name": "Acme Tx",
                "product_id": product.id,
                "product_code": product.product_code,
                "product_name": product.product_name,
                "product_model": product.product_model,
                "product_type": product.product_type,
                "quantity": 2,
                "unit": "pcs",
                "price_with_tax": 50,
                "handler": "Initial Handler",
                "delivery_date": date(2026, 4, 7),
                "invoice_date": None,
                "contract_no": "T-EDIT-001",
                "remark": "before edit",
            }
        )
        tx_id = tx.id
        product_id = product.id

    login(base_data["superadmin_id"])
    resp = client.post(
        f"/transaction/{tx_id}/edit",
        data={
            "company_name": "Acme Tx Updated",
            "product_select_mode": "manual",
            "product_id": str(product_id),
            "product_code": "TXFLOW-001",
            "product_name": "TxFlow Product Updated",
            "product_model": "TF2",
            "product_type": "TypeT2",
            "quantity": "7",
            "unit": "box",
            "price_with_tax": "120",
            "delivery_date": "2026-04-09",
            "invoice_date": "2026-04-10",
            "payment_date": "",
            "contract_no": "T-EDIT-001",
            "remark": "after edit",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/transaction/" in resp.headers.get("Location", "")

    with app.app_context():
        updated = Transaction.query.get(tx_id)
        assert updated is not None
        assert updated.company_name == "Acme Tx Updated"
        assert float(updated.quantity) == 7.0
        assert updated.unit == "box"
        assert float(updated.price_with_tax) == 120.0
        assert updated.handler == "Initial Handler"
