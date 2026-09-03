"""Regression tests for returning to a filtered contract list."""

from __future__ import annotations

from html import unescape

from flask import url_for
from app.services.contract_service import ContractService


def _create_contract(app, owner_user_id: int) -> int:
    """Create one contract that is visible in the filtered list."""
    with app.app_context():
        contract = ContractService.create_contract(
            {
                "contract_no": "FILTER-RETURN-001",
                "company_name": "Return Company",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": owner_user_id,
            },
            [
                {
                    "product_code": "FILTER-RETURN-PRODUCT",
                    "product_name": "Return Product",
                    "product_model": "M1",
                    "product_type": "TypeA",
                    "quantity": 10,
                    "unit": "pcs",
                    "price": 10,
                    "remark": "",
                }
            ],
        )
        return contract.id


def test_contract_navigation_preserves_filtered_list_url(app, client, login, base_data):
    """List, detail, and edit pages should preserve all active filters on return."""
    contract_id = _create_contract(app, base_data["owner_user_id"])
    login(base_data["superadmin_id"])

    source_url = "/contract/list?company_name=Return+Company&page=1"
    with app.test_request_context():
        expected_edit_url = url_for(
            "contract.edit_contract",
            id=contract_id,
            return_to=source_url,
        )
        expected_detail_url = url_for(
            "contract.view_contract",
            id=contract_id,
            return_to=source_url,
        )

    list_response = client.get(source_url)
    assert list_response.status_code == 200
    list_page = unescape(list_response.get_data(as_text=True))
    assert "FILTER-RETURN-001" in list_page
    assert expected_edit_url in list_page
    assert expected_detail_url in list_page

    edit_response = client.get(
        f"/contract/{contract_id}/edit",
        query_string={"return_to": source_url},
    )
    assert edit_response.status_code == 200
    edit_page = unescape(edit_response.get_data(as_text=True))
    assert f'href="{source_url}"' in edit_page
    assert f'action="{expected_edit_url}"' in edit_page

    detail_response = client.get(
        f"/contract/{contract_id}",
        query_string={"return_to": source_url},
    )
    assert detail_response.status_code == 200
    detail_page = unescape(detail_response.get_data(as_text=True))
    assert f'href="{source_url}"' in detail_page
    assert expected_edit_url in detail_page


def test_contract_navigation_rejects_external_return_url(app, client, login, base_data):
    """A crafted return target must not turn the contract pages into an open redirect."""
    contract_id = _create_contract(app, base_data["owner_user_id"])
    login(base_data["superadmin_id"])

    response = client.get(
        f"/contract/{contract_id}/edit",
        query_string={"return_to": "https://example.com/phishing"},
    )

    assert response.status_code == 200
    page = unescape(response.get_data(as_text=True))
    assert 'href="/contract/list"' in page
    assert "example.com" not in page
