"""Regression tests for contract file delete behavior on edit page."""

from __future__ import annotations

from app import db
from app.models import ContractFile
from app.services.contract_service import ContractService


def _create_contract_with_file(owner_user_id: int) -> tuple[int, int]:
    """Create one contract and one attached contract file for delete tests."""
    contract = ContractService.create_contract(
        {
            "contract_no": f"FILE-DEL-{owner_user_id}",
            "company_name": "ACME",
            "owner": "Sales - Owner",
            "department": "Sales",
            "manager": "Owner",
            "created_by_id": owner_user_id,
        },
        [
            {
                "product_code": "FILE-P-001",
                "product_name": "File Product",
                "product_model": "M1",
                "product_type": "T1",
                "quantity": 1,
                "unit": "pcs",
                "price": 1,
            }
        ],
    )
    contract_file = ContractFile(
        contract_id=contract.id,
        filename="demo.pdf",
        filepath="demo.pdf",
        file_type="pdf",
        file_size=1234,
    )
    db.session.add(contract_file)
    db.session.commit()
    return contract.id, contract_file.id


def test_delete_contract_file_ajax_returns_json_and_removes_record(app, client, login, base_data):
    """Owner should be able to delete contract file via AJAX without redirect."""
    with app.app_context():
        contract_id, file_id = _create_contract_with_file(base_data["owner_user_id"])

    login(base_data["owner_user_id"])
    resp = client.post(
        f"/contract/{contract_id}/file/{file_id}/delete",
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        follow_redirects=False,
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload and payload.get("success") is True
    assert payload.get("file_id") == file_id
    assert resp.headers.get("Location") in (None, "")

    with app.app_context():
        assert ContractFile.query.get(file_id) is None


def test_delete_contract_file_ajax_forbidden_for_unrelated_sales(app, client, login, base_data):
    """Unrelated sales manager should get 403 and file must remain."""
    with app.app_context():
        contract_id, file_id = _create_contract_with_file(base_data["owner_user_id"])

    login(base_data["other_sales_id"])
    resp = client.post(
        f"/contract/{contract_id}/file/{file_id}/delete",
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        follow_redirects=False,
    )

    assert resp.status_code == 403
    payload = resp.get_json()
    assert payload and payload.get("success") is False

    with app.app_context():
        assert ContractFile.query.get(file_id) is not None
