from __future__ import annotations

import io
import json
import os
import zipfile

from werkzeug.security import generate_password_hash

from app import db
from app.models import (
    AssemblyAcceptanceSignature,
    AssemblyOrder,
    AssemblyOutboundBatch,
    AssemblyOutboundOrder,
    AssemblyProduct,
    AssemblyProductAttachment,
    AssemblyProductComponent,
    AssemblyProductStockHistory,
    Department,
    QCWorkpiece,
    QCWorkpieceAttachment,
    QCWorkpieceStockHistory,
    Role,
    User,
)
from app.services.assembly_service import AssemblyService


def test_assembly_module_pages_reject_unassigned_erp_users(client, login, base_data):
    """Ordinary ERP users must not retain retired test-period broad access."""
    login(base_data["owner_user_id"])

    pages = [
        "/qc/assembly/",
        "/qc/assembly/products/",
        "/qc/assembly/products/new",
        "/qc/assembly/launch/",
        "/qc/assembly/launch/new",
        "/qc/assembly/inspection/",
        "/qc/assembly/acceptance/",
        "/qc/assembly/outbound/",
    ]

    for path in pages:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 302


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
    inspection_page = client.get(f"/qc/assembly/inspection/{order_id}")
    inspection_text = inspection_page.get_data(as_text=True)
    assert inspection_page.status_code == 200
    assert "生产登记单确认件（必选）" in inspection_text
    assert 'data-report-label="生产登记单确认件"' in inspection_text

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

    start_batch = client.post(f"/qc/assembly/acceptance/{order_id}/batch/new", follow_redirects=False)
    assert start_batch.status_code == 302

    reviewer_sign = client.post(
        f"/qc/assembly/acceptance/{order_id}/sign",
        data={"signer_role": "qc_inspector", "production_quantity": "3", "accepted_quantity": "3"},
        follow_redirects=False,
    )
    assert reviewer_sign.status_code == 302

    login(controller_id)
    controller_sign = client.post(
        f"/qc/assembly/acceptance/{order_id}/sign",
        data={"signer_role": "qc_controller", "production_quantity": "3", "accepted_quantity": "3"},
        follow_redirects=False,
    )
    assert controller_sign.status_code == 302

    with app.app_context():
        order = AssemblyOrder.query.get(order_id)
        assert order is not None
        assert order.status == "accepted"
        assert order.inventory_posted_at is not None
        product = AssemblyProduct.query.get(product_id)
        assert product is not None
        assert float(product.stock_quantity) == 3.0
        wp1 = QCWorkpiece.query.get(wp1_id)
        wp2 = QCWorkpiece.query.get(wp2_id)
        assert wp1 is not None and wp2 is not None
        assert float(wp1.stock_quantity) == 4.0
        assert float(wp2.stock_quantity) == 5.0
        assert any(history.action == "验收入库" for history in order.histories)
        product_histories = AssemblyProductStockHistory.query.filter_by(product_id=product_id).order_by(
            AssemblyProductStockHistory.id.asc()
        ).all()
        assert len(product_histories) == 1
        assert product_histories[0].change_type == "acceptance_in"
        assert product_histories[0].quantity_delta == 3
        wp1_histories = QCWorkpieceStockHistory.query.filter_by(workpiece_id=wp1_id).order_by(
            QCWorkpieceStockHistory.id.asc()
        ).all()
        wp2_histories = QCWorkpieceStockHistory.query.filter_by(workpiece_id=wp2_id).order_by(
            QCWorkpieceStockHistory.id.asc()
        ).all()
        assert len(wp1_histories) == 1
        assert len(wp2_histories) == 1
        assert wp1_histories[0].change_type == "assembly_consumption"
        assert wp1_histories[0].quantity_delta == -6
        assert wp1_histories[0].stock_before == 10
        assert wp1_histories[0].stock_after == 4
        assert wp2_histories[0].change_type == "assembly_consumption"
        assert wp2_histories[0].quantity_delta == -3


def test_assembly_product_level_is_locked_by_entry_url(app, client, login, monkeypatch):
    """The product level is fixed by the entry URL and cannot be changed inside the form."""
    with app.app_context():
        controller_id, _, wp1_id, wp2_id = _seed_assembly_users_and_workpieces()

    monkeypatch.setattr(AssemblyService, "_save_product_file", staticmethod(_fake_save_product_file))
    login(controller_id)

    page = client.get("/qc/assembly/products/new?level=1")
    page_text = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "一级产品库" in page_text
    assert 'id="productLevelSelect"' not in page_text

    response = client.post(
        "/qc/assembly/products/new?level=1",
        data={
            "product_code": "PRD-LOCK-001",
            "product_name": "Locked Level Product",
            "product_level": "3",
            "component_workpiece_id_0": str(wp1_id),
            "component_workpiece_code_0": "WP-A",
            "component_workpiece_name_0": "Connector A",
            "component_quantity_0": "1",
            "component_workpiece_id_1": str(wp2_id),
            "component_workpiece_code_1": "WP-B",
            "component_workpiece_name_1": "Connector B",
            "component_quantity_1": "1",
            "assembly_sheet_title_0": "Assembly Sheet",
            "assembly_sheet_content_0": "Follow locked level",
            "assembly_sheet_file_0": (io.BytesIO(b"assembly-sheet"), "assembly_sheet.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        product = AssemblyProduct.query.filter_by(product_code="PRD-LOCK-001").first()
        assert product is not None
        assert product.product_level == 1


def test_assembly_order_edit_saves_without_certificate_upload(app, client, login, monkeypatch):
    """Editing an assembly order should save with only the registration-note section present."""
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
            "product_code": "PRD-EDIT-001",
            "product_name": "Editable Assembly Product",
            "component_workpiece_id_0": str(wp1_id),
            "component_workpiece_code_0": "WP-A",
            "component_workpiece_name_0": "Connector A",
            "component_quantity_0": "1",
            "component_workpiece_id_1": str(wp2_id),
            "component_workpiece_code_1": "WP-B",
            "component_workpiece_name_1": "Connector B",
            "component_quantity_1": "1",
            "assembly_sheet_title_0": "Registration Source",
            "assembly_sheet_content_0": "Use this as production registration",
            "assembly_sheet_file_0": (io.BytesIO(b"assembly-sheet"), "assembly_sheet.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert product_response.status_code == 302

    with app.app_context():
        product = AssemblyProduct.query.filter_by(product_code="PRD-EDIT-001").first()
        product_id = product.id

    create_response = client.post(
        "/qc/assembly/launch/new",
        data={
            "submit_action": "draft",
            "batch_no": "ASSY-EDIT-001",
            "product_id": str(product_id),
            "quantity": "1",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    with app.app_context():
        order = AssemblyOrder.query.filter_by(batch_no="ASSY-EDIT-001").first()
        order_id = order.id

    edit_page = client.get(f"/qc/assembly/launch/{order_id}/edit")
    edit_text = edit_page.get_data(as_text=True)
    assert edit_page.status_code == 200
    assert "生产登记单" in edit_text
    assert "生产合格证" not in edit_text

    edit_response = client.post(
        f"/qc/assembly/launch/{order_id}/edit",
        data={
            "batch_no": "ASSY-EDIT-001",
            "product_id": str(product_id),
            "product_name_snapshot": "Editable Assembly Product",
            "quantity": "2",
            "inspector_id": str(inspector_id),
            "registration_note_file": (io.BytesIO(b"registration-note"), "registration.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert edit_response.status_code == 302
    assert f"/qc/assembly/launch/{order_id}" in edit_response.headers.get("Location", "")

    with app.app_context():
        order = AssemblyOrder.query.get(order_id)
        assert float(order.quantity) == 2.0
        assert order.registration_note_file_path
        assert not order.certificate_note_file_path
        assert all(float(component.total_required_quantity) == 2.0 for component in order.components)


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
    assert "发起新的验收批次" in text

    start_batch = client.post(f"/qc/assembly/acceptance/{order_id}/batch/new", follow_redirects=True)
    assert start_batch.status_code == 200
    text = start_batch.get_data(as_text=True)
    assert 'name="signer_role" value="qc_controller"' in text
    assert 'name="signer_role" value="qc_inspector"' in text

    first_sign = client.post(
        f"/qc/assembly/acceptance/{order_id}/sign",
        data={"signer_role": "qc_controller", "production_quantity": "2", "accepted_quantity": "2"},
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
        data={"signer_role": "qc_inspector", "production_quantity": "2", "accepted_quantity": "2"},
        follow_redirects=True,
    )
    second_text = second_sign.get_data(as_text=True)
    assert second_sign.status_code == 200
    assert "本批次双方已确认" in second_text

    with app.app_context():
        order = AssemblyOrder.query.get(order_id)
        signatures = AssemblyAcceptanceSignature.query.filter_by(order_id=order_id).all()
        assert order.status == "accepted"
        assert len(signatures) == 2
        assert {signature.signer_role for signature in signatures} == {"qc_controller", "qc_inspector"}
        assert {signature.signer_id for signature in signatures} == {manager_id}
        assert any(
            history.action == "发起验收批次" and "发起第 1 个验收批次" in (history.detail or "")
            for history in order.histories
        )
        assert any(
            history.action == "验收入库" and "验收批次 #1" in (history.detail or "")
            for history in order.histories
        )

    print_page = client.get(f"/qc/assembly/acceptance/{order_id}/print", follow_redirects=False)
    coa_page = client.get(f"/qc/assembly/acceptance/{order_id}/coa", follow_redirects=False)
    assert print_page.status_code == 200
    assert "装配验收报告" in print_page.get_data(as_text=True)
    assert coa_page.status_code == 302


def test_assembly_outbound_batches_deduct_stock_and_generate_coa(app, client, login, base_data):
    """Outbound flow should require two users, deduct stock per batch, and generate COA docx."""
    with app.app_context():
        controller_id, inspector_id, wp1_id, _ = _seed_assembly_users_and_workpieces()
        approver_id = base_data["superadmin_id"]
        wp1 = QCWorkpiece.query.get(wp1_id)
        template_dir = os.path.join(app.root_path, "..", "static", "uploads", "qc", "workpieces", str(wp1_id), "coa_templates")
        os.makedirs(template_dir, exist_ok=True)
        template_path = os.path.join(template_dir, "coa_template.docx")
        with open(template_path, "wb") as handle:
            handle.write(AssemblyService._minimal_docx_bytes("模板正文 {{产品名称}} {{出厂数量}}"))
        db.session.add(
            QCWorkpieceAttachment(
                workpiece_id=wp1_id,
                attach_type="coa_template",
                title="COA报告模板",
                file_path="coa_templates/coa_template.docx",
                file_type="docx",
                is_required=False,
                sort_order=0,
            )
        )
        assert wp1 is not None
        db.session.commit()

    login(inspector_id)
    supplier_page = client.get("/qc/assembly/outbound/", follow_redirects=False)
    assert supplier_page.status_code == 302

    login(controller_id)
    create_response = client.post(
        "/qc/assembly/outbound/new",
        data={
            "outbound_no": "OUT-001",
            "item_type": "workpiece",
            "item_id": str(wp1_id),
            "outbound_date": "2026-07-08",
            "planned_quantity": "5",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    with app.app_context():
        order = AssemblyOutboundOrder.query.filter_by(outbound_no="OUT-001").first()
        assert order is not None
        order_id = order.id

    assert client.post(f"/qc/assembly/outbound/{order_id}/batch/new", follow_redirects=False).status_code == 302
    initiator_page = client.get(f"/qc/assembly/outbound/{order_id}", follow_redirects=False)
    initiator_text = initiator_page.get_data(as_text=True)
    assert initiator_page.status_code == 200
    assert 'name="signer_role" value="initiator"' in initiator_text
    assert 'name="signer_role" value="approver"' not in initiator_text

    initiator_sign = client.post(
        f"/qc/assembly/outbound/{order_id}/sign",
        data={"signer_role": "initiator", "outbound_quantity": "2"},
        follow_redirects=False,
    )
    assert initiator_sign.status_code == 302
    same_user_page = client.get(f"/qc/assembly/outbound/{order_id}", follow_redirects=False)
    same_user_text = same_user_page.get_data(as_text=True)
    assert same_user_page.status_code == 200
    assert 'name="signer_role" value="approver"' not in same_user_text

    login(approver_id)
    approver_page = client.get(f"/qc/assembly/outbound/{order_id}", follow_redirects=False)
    approver_text = approver_page.get_data(as_text=True)
    assert approver_page.status_code == 200
    assert 'name="signer_role" value="approver"' in approver_text

    approver_sign = client.post(
        f"/qc/assembly/outbound/{order_id}/sign",
        data={"signer_role": "approver", "outbound_quantity": "2"},
        follow_redirects=False,
    )
    assert approver_sign.status_code == 302

    with app.app_context():
        order = AssemblyOutboundOrder.query.get(order_id)
        first_batch = AssemblyOutboundBatch.query.filter_by(order_id=order_id).first()
        wp1 = QCWorkpiece.query.get(wp1_id)
        assert order.status == "confirming"
        assert float(order.shipped_quantity) == 2.0
        assert float(order.remaining_quantity) == 3.0
        assert float(wp1.stock_quantity) == 8.0
        assert first_batch.completed_at is not None
        first_batch_id = first_batch.id
        workpiece_outbound_histories = QCWorkpieceStockHistory.query.filter_by(workpiece_id=wp1_id).order_by(
            QCWorkpieceStockHistory.id.asc()
        ).all()
        assert len(workpiece_outbound_histories) == 1
        assert workpiece_outbound_histories[0].change_type == "outbound_out"
        assert workpiece_outbound_histories[0].quantity_delta == -2
        assert workpiece_outbound_histories[0].stock_before == 10
        assert workpiece_outbound_histories[0].stock_after == 8

    outbound_detail = client.get(f"/qc/assembly/outbound/{order_id}", follow_redirects=False)
    outbound_detail_text = outbound_detail.get_data(as_text=True)
    assert outbound_detail.status_code == 200
    assert "COA报告" in outbound_detail_text
    assert "打印COA报告" in outbound_detail_text

    coa_response = client.get(f"/qc/assembly/outbound/{order_id}/batch/{first_batch_id}/coa", follow_redirects=False)
    assert coa_response.status_code == 200
    coa_text = coa_response.get_data(as_text=True)
    assert "COA报告" in coa_text
    assert "COA模板内容" in coa_text
    assert "模板正文" in coa_text
    assert "下载" in coa_text
    assert "下载DOC格式文件" not in coa_text

    coa_download = client.get(f"/qc/assembly/outbound/{order_id}/batch/{first_batch_id}/coa/download", follow_redirects=False)
    assert coa_download.status_code == 200
    assert coa_download.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert coa_download.data.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(coa_download.data), "r") as docx:
        document_xml = docx.read("word/document.xml").decode("utf-8")
    assert "计划出厂总数量" in document_xml
    assert "模板正文" in document_xml
    assert "接头A" in document_xml
    assert "签名确认" in document_xml

    login(controller_id)
    assert client.post(f"/qc/assembly/outbound/{order_id}/batch/new", follow_redirects=False).status_code == 302
    assert client.post(
        f"/qc/assembly/outbound/{order_id}/sign",
        data={"signer_role": "initiator", "outbound_quantity": "3"},
        follow_redirects=False,
    ).status_code == 302

    login(approver_id)
    assert client.post(
        f"/qc/assembly/outbound/{order_id}/sign",
        data={"signer_role": "approver", "outbound_quantity": "3"},
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        order = AssemblyOutboundOrder.query.get(order_id)
        wp1 = QCWorkpiece.query.get(wp1_id)
        assert order.status == "completed"
        assert float(order.shipped_quantity) == 5.0
        assert float(order.remaining_quantity) == 0.0
        assert float(wp1.stock_quantity) == 5.0
        assert any(history.action == "出厂扣减库存" for history in order.histories)
        workpiece_outbound_histories = QCWorkpieceStockHistory.query.filter_by(workpiece_id=wp1_id).order_by(
            QCWorkpieceStockHistory.id.asc()
        ).all()
        assert len(workpiece_outbound_histories) == 2
        assert workpiece_outbound_histories[1].change_type == "outbound_out"
        assert workpiece_outbound_histories[1].quantity_delta == -3
        assert workpiece_outbound_histories[1].stock_after == 5
        outbound_history_details = [
            history.detail or ""
            for history in order.histories
            if history.action == "出厂扣减库存"
        ]
        outbound_start_details = [
            history.detail or ""
            for history in order.histories
            if history.action == "发起出厂批次"
        ]
        assert any("发起第 1 个出厂批次" in detail for detail in outbound_start_details)
        assert any("发起第 2 个出厂批次" in detail for detail in outbound_start_details)
        assert any("出厂批次 #1" in detail for detail in outbound_history_details)
        assert any("出厂批次 #2" in detail for detail in outbound_history_details)


def test_assembly_product_outbound_writes_product_stock_history(app, client, login, base_data):
    """Outbound shipping from a product library item should deduct product stock and keep history."""
    with app.app_context():
        controller_id, _, _, _ = _seed_assembly_users_and_workpieces()
        product = AssemblyProduct(
            product_code="PRD-STOCK-001",
            product_name="Stocked Product",
            product_level=1,
            stock_quantity=7,
            creator_id=controller_id,
        )
        db.session.add(product)
        db.session.commit()
        product_id = product.id

    login(controller_id)
    create_response = client.post(
        "/qc/assembly/outbound/new",
        data={
            "outbound_no": "OUT-PROD-001",
            "item_type": "product",
            "item_id": str(product_id),
            "outbound_date": "2026-07-09",
            "planned_quantity": "4",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    with app.app_context():
        order = AssemblyOutboundOrder.query.filter_by(outbound_no="OUT-PROD-001").first()
        order_id = order.id

    assert client.post(f"/qc/assembly/outbound/{order_id}/batch/new", follow_redirects=False).status_code == 302
    assert client.post(
        f"/qc/assembly/outbound/{order_id}/sign",
        data={"signer_role": "initiator", "outbound_quantity": "4"},
        follow_redirects=False,
    ).status_code == 302
    login(base_data["superadmin_id"])
    assert client.post(
        f"/qc/assembly/outbound/{order_id}/sign",
        data={"signer_role": "approver", "outbound_quantity": "4"},
        follow_redirects=False,
    ).status_code == 302

    with app.app_context():
        product = AssemblyProduct.query.get(product_id)
        histories = AssemblyProductStockHistory.query.filter_by(product_id=product_id).all()
        assert float(product.stock_quantity) == 3.0
        assert len(histories) == 1
        assert histories[0].change_type == "outbound_out"
        assert histories[0].quantity_delta == -4
        assert histories[0].stock_before == 7
        assert histories[0].stock_after == 3
