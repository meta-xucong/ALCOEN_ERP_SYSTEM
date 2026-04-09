"""Product route regression tests."""

from __future__ import annotations


def test_product_create_edit_delete_flow(app, client, login, base_data):
    """Product CRUD via routes should complete successfully."""
    from app.models import Product

    login(base_data["superadmin_id"])

    create_resp = client.post(
        "/product/new",
        data={
            "product_code": "PR-001",
            "product_name": "Product A",
            "product_model": "A1",
            "product_type": "TypeA",
            "default_price": "88",
            "remark": "created in test",
        },
        follow_redirects=False,
    )
    assert create_resp.status_code == 302
    assert "/product/" in create_resp.headers.get("Location", "")

    with app.app_context():
        product = Product.query.filter_by(product_code="PR-001").first()
        assert product is not None
        product_id = product.id

    edit_resp = client.post(
        f"/product/{product_id}/edit",
        data={
            "product_code": "PR-001",
            "product_name": "Product A+",
            "product_model": "A2",
            "product_type": "TypeA",
            "default_price": "99",
            "remark": "edited in test",
        },
        follow_redirects=False,
    )
    assert edit_resp.status_code == 302

    with app.app_context():
        edited = Product.query.get(product_id)
        assert edited.product_name == "Product A+"
        assert edited.product_model == "A2"
        assert float(edited.default_price) == 99.0

    delete_resp = client.post(f"/product/{product_id}/delete", follow_redirects=False)
    assert delete_resp.status_code == 302

    with app.app_context():
        deleted = Product.query.filter_by(product_code="PR-001").first()
        assert deleted is None


def test_product_api_endpoints(app, client, login, base_data):
    """Product API endpoints should return expected payloads."""
    from app.services.product_service import ProductService

    with app.app_context():
        product = ProductService.create_product(
            product_code="PR-API-001",
            product_name="Product API",
            product_model="PA1",
            product_type="TypeAPI",
            default_price=12.5,
            remark="",
        )
        product_id = product.id

    login(base_data["superadmin_id"])

    list_resp = client.get("/product/api/list")
    detail_resp = client.get(f"/product/api/{product_id}")
    code_resp = client.get("/product/api/by-code/PR-API-001")
    check_resp = client.get("/product/api/check-code?code=PR-API-001")

    assert list_resp.status_code == 200
    assert detail_resp.status_code == 200
    assert code_resp.status_code == 200
    assert check_resp.status_code == 200

    assert any(p["product_code"] == "PR-API-001" for p in list_resp.get_json()["products"])
    assert detail_resp.get_json()["product_code"] == "PR-API-001"
    assert code_resp.get_json()["product_name"] == "Product API"
    assert check_resp.get_json()["exists"] is True
