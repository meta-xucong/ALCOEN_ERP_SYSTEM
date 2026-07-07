from __future__ import annotations

import io
import json

from werkzeug.security import generate_password_hash

from app import db
from app.models import (
    AssemblyAcceptanceSignature,
    AssemblyOrder,
    AssemblyProduct,
    AssemblyProductAttachment,
    AssemblyProductComponent,
    Department,
    QCWorkpiece,
    QCWorkpieceAttachment,
    Role,
    User,
)
from app.services.assembly_service import AssemblyService


def test_assembly_module_pages_load_for_temporary_erp_test_access(client, login, base_data):
    """Ordinary ERP users should be able to smoke-test assembly pages during the test period."""
    login(base_data["owner_user_id"])

    pages = [
        ("/qc/assembly/", "装配/出厂"),
        ("/qc/assembly/products/", "产品库"),
        ("/qc/assembly/products/new", "新增产品"),
        ("/qc/assembly/launch/", "发起装配"),
        ("/qc/assembly/launch/new", "新增装配单"),
        ("/qc/assembly/inspection/", "质量检测"),
        ("/qc/assembly/acceptance/", "验收/出厂"),
    ]

    for path, expected_text in pages:
        response = client.get(path)
        assert response.status_code == 200
        page_text = response.get_data(as_text=True)
        assert expected_text in page_text
        assert "\ufffd" not in page_text


def _seed_assembly_users_and_workpieces() -> tuple[int, int, int, int]:
    """Create minimal users plus two stocked workpieces for assembly tests."""
    dept = Department(name="Assembly")
    db.session.add(dept)
    db.session.flush()

    controller_role = Role(
        name="装配负责人",
        code="qc_controller",
        permissions=json.dumps(
            [
                "qc_dashboard",
                "qc_workpiece_view",
                "qc_workpiece_create",
                "qc_workpiece_edit",
                "qc_workpiece_delete",
                "qc_work_order_view",
                "qc_work_order_create",
                "qc_work_order_edit",
                "qc_work_order_delete",
                "qc_inspection_view",
                "qc_acceptance_perform",
                "qc_acceptance_rollback",
            ]
        ),
        level=55,
    )
    inspector_role = Role(
        name="指导验收人员",
        code="qc_inspector",
        permissions=json.dumps(
            [
                "qc_dashboard",
                "qc_inspection_view",
                "qc_inspection_perform",
                "qc_acceptance_perform",
            ]
        ),
        level=45,
    )
    db.session.add_all([controller_role, inspector_role])
    db.session.flush()

    controller = User(
        username="assembly_controller",
        password_hash=generate_password_hash("Pass123!"),
        real_name="Assembly Controller",
        role_id=controller_role.id,
        department_id=dept.id,
        email="assembly_controller@example.com",
        is_active=True,
        require_password_change=False,
    )
    inspector = User(
        username="assembly_inspector",
        password_hash=generate_password_hash("Pass123!"),
        real_name="Assembly Inspector",
        role_id=inspector_role.id,
        department_id=dept.id,
        email="assembly_inspector@example.com",
        is_active=True,
        require_password_change=False,
    )
    db.session.add_all([controller, inspector])
    db.session.flush()

    wp1 = QCWorkpiece(
        workpiece_code="WP-A",
        workpiece_name="接头A",
        workpiece_type="self_produced",
        stock_quantity=10,
        creator_id=controller.id,
    )
    wp2 = QCWorkpiece(
        workpiece_code="WP-B",
        workpiece_name="接头B",
        workpiece_type="self_produced",
        stock_quantity=8,
        creator_id=controller.id,
    )
    db.session.add_all([wp1, wp2])
    db.session.flush()

    db.session.add(
        QCWorkpieceAttachment(
            workpiece_id=wp1.id,
            attach_type="drawing",
            title="图纸1",
            content="示意图",
            file_path="drawings/wp_a.pdf",
            file_type="pdf",
            is_required=True,
            sort_order=0,
        )
    )
    db.session.add(
        QCWorkpieceAttachment(
            workpiece_id=wp2.id,
            attach_type="drawing",
            title="图纸1",
            content="示意图",
            file_path="drawings/wp_b.pdf",
            file_type="pdf",
            is_required=True,
            sort_order=0,
        )
    )
    db.session.commit()
    return controller.id, inspector.id, wp1.id, wp2.id


def _fake_save_product_file(file, product_id: int, attach_type: str) -> tuple[str, str]:
    suffix = file.filename.rsplit(".", 1)[-1].lower()
    return f"{attach_type}/{product_id}_{file.filename}", suffix


def _fake_save_order_file(file, order_id: int, attach_type: str) -> tuple[str, str]:
    suffix = file.filename.rsplit(".", 1)[-1].lower()
    return f"{attach_type}/{order_id}_{file.filename}", suffix


def _fake_copy_product_file_to_order(product_id: int, order_id: int, relative_path: str, attach_type: str) -> tuple[str, str]:
    filename = relative_path.split("/")[-1]
    suffix = filename.rsplit(".", 1)[-1].lower()
    return f"{attach_type}/{order_id}_copied_{filename}", suffix


def test_assembly_inventory_guard_and_acceptance_deduction(app, client, login, monkeypatch):
    """Assembly flow should block insufficient stock and deduct on final acceptance."""
    with app.app_context():
        controller_id, inspector_id, wp1_id, wp2_id = _seed_assembly_users_and_workpieces()

    monkeypatch.setattr(AssemblyService, "_save_product_file", staticmethod(_fake_save_product_file))
    monkeypatch.setattr(AssemblyService, "_save_order_file", staticmethod(_fake_save_order_file))
    monkeypatch.setattr(
        AssemblyService,
        "_copy_product_file_to_order",
        staticmethod(_fake_copy_product_file_to_order),
    )

    login(controller_id)

    product_response = client.post(
        "/qc/assembly/products/new",
        data={
            "product_code": "PRD-001",
            "product_name": "柱组件A",
            "component_workpiece_id_0": str(wp1_id),
            "component_workpiece_code_0": "WP-A",
            "component_workpiece_name_0": "接头A",
            "component_quantity_0": "2",
            "component_workpiece_id_1": str(wp2_id),
            "component_workpiece_code_1": "WP-B",
            "component_workpiece_name_1": "接头B",
            "component_quantity_1": "1",
            "assembly_sheet_title_0": "装配步骤1",
            "assembly_sheet_content_0": "按顺序组装",
            "assembly_sheet_file_0": (io.BytesIO(b"assembly-sheet"), "assembly_sheet.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert product_response.status_code == 302

    with app.app_context():
        product = AssemblyProduct.query.filter_by(product_code="PRD-001").first()
        assert product is not None
        assert len(product.components) == 2
        assert len(product.assembly_sheet_attachments) == 1
        product_id = product.id

    shortage_response = client.post(
        "/qc/assembly/launch/new",
        data={
            "submit_action": "submit",
            "batch_no": "ASSY-OVER",
            "product_id": str(product_id),
            "quantity": "9",
            "inspector_id": str(inspector_id),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    shortage_text = shortage_response.get_data(as_text=True)
    assert "库存不足" in shortage_text

    valid_response = client.post(
        "/qc/assembly/launch/new",
        data={
            "submit_action": "submit",
            "batch_no": "ASSY-001",
            "product_id": str(product_id),
            "quantity": "3",
            "inspector_id": str(inspector_id),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert valid_response.status_code == 302

    with app.app_context():
        order = AssemblyOrder.query.filter_by(batch_no="ASSY-001").first()
        assert order is not None
        assert order.status == "assembly_completed"
        assert len(order.components) == 2
        order_id = order.id
        attachment_ids = [attachment.id for attachment in order.attachments]

    login(inspector_id)
    inspection_payload = {"submit_action": "submit"}
    for attachment_id in attachment_ids:
        inspection_payload[f"result_{attachment_id}"] = "pass"
        inspection_payload[f"remark_{attachment_id}"] = "通过"
        inspection_payload[f"report_file_{attachment_id}"] = (io.BytesIO(b"report"), f"report_{attachment_id}.pdf")

    inspection_response = client.post(
        f"/qc/assembly/inspection/{order_id}",
        data=inspection_payload,
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert inspection_response.status_code == 302

    with app.app_context():
        order = AssemblyOrder.query.get(order_id)
        assert order is not None
        assert order.status == "inspection_completed"

    reviewer_sign = client.post(f"/qc/assembly/acceptance/{order_id}/sign", follow_redirects=False)
    assert reviewer_sign.status_code == 302

    login(controller_id)
    controller_sign = client.post(f"/qc/assembly/acceptance/{order_id}/sign", follow_redirects=False)
    assert controller_sign.status_code == 302

    with app.app_context():
        order = AssemblyOrder.query.get(order_id)
        assert order is not None
        assert order.status == "accepted"
        assert order.inventory_posted_at is not None
        wp1 = QCWorkpiece.query.get(wp1_id)
        wp2 = QCWorkpiece.query.get(wp2_id)
        assert wp1 is not None and wp2 is not None
        assert float(wp1.stock_quantity) == 4.0
        assert float(wp2.stock_quantity) == 5.0
        assert any(history.action == "工件库存扣减" for history in order.histories)


def test_assembly_manager_acceptance_requires_one_role_per_click(app, client, login, base_data):
    """Managers can confirm both sides, but each click should sign only one role."""
    with app.app_context():
        controller_id, inspector_id, _, _ = _seed_assembly_users_and_workpieces()
        manager_role = Role(
            name="Assembly Manager",
            code="general_manager",
            permissions=json.dumps(["qc_acceptance_perform", "qc_acceptance_rollback"]),
            level=80,
        )
        db.session.add(manager_role)
        db.session.flush()
        manager = User(
            username="assembly_manager",
            password_hash="x",
            real_name="Assembly Manager",
            role_id=manager_role.id,
            department_id=base_data["department_id"],
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        order = AssemblyOrder(
            batch_no="ASSY-MGR-001",
            product_name_snapshot="Very Long Assembly Product Name For UI Truncation",
            quantity=2,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="inspection_completed",
        )
        db.session.add_all([manager, order])
        db.session.commit()
        manager_id = manager.id
        order_id = order.id

    login(manager_id)
    page = client.get(f"/qc/assembly/acceptance/{order_id}", follow_redirects=False)
    text = page.get_data(as_text=True)
    assert page.status_code == 200
    assert text.count("点击确认") == 2
    assert 'name="signer_role" value="qc_controller"' in text
    assert 'name="signer_role" value="qc_inspector"' in text

    first_sign = client.post(
        f"/qc/assembly/acceptance/{order_id}/sign",
        data={"signer_role": "qc_controller"},
        follow_redirects=True,
    )
    first_text = first_sign.get_data(as_text=True)
    assert first_sign.status_code == 200
    assert "验收确认已提交，等待另一方确认" in first_text

    with app.app_context():
        order = AssemblyOrder.query.get(order_id)
        signatures = AssemblyAcceptanceSignature.query.filter_by(order_id=order_id).all()
        assert order.status == "inspection_completed"
        assert len(signatures) == 1
        assert signatures[0].signer_role == "qc_controller"

    second_sign = client.post(
        f"/qc/assembly/acceptance/{order_id}/sign",
        data={"signer_role": "qc_inspector"},
        follow_redirects=True,
    )
    second_text = second_sign.get_data(as_text=True)
    assert second_sign.status_code == 200
    assert "双方已确认，质检已完成" in second_text

    with app.app_context():
        order = AssemblyOrder.query.get(order_id)
        signatures = AssemblyAcceptanceSignature.query.filter_by(order_id=order_id).all()
        assert order.status == "accepted"
        assert len(signatures) == 2
        assert {signature.signer_role for signature in signatures} == {"qc_controller", "qc_inspector"}
        assert {signature.signer_id for signature in signatures} == {manager_id}

    print_page = client.get(f"/qc/assembly/acceptance/{order_id}/print", follow_redirects=False)
    coa_page = client.get(f"/qc/assembly/acceptance/{order_id}/coa", follow_redirects=False)
    assert print_page.status_code == 200
    assert "装配/出厂报告" in print_page.get_data(as_text=True)
    assert coa_page.status_code == 200
    assert "COA 报告打印位已预留" in coa_page.get_data(as_text=True)
