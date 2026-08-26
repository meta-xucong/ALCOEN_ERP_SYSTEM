"""Regression tests for QC workflow and auth verification behavior."""

from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
import pytest
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from app import _ensure_qc_work_order_batch_no_index, db
from app.models import (
    Department,
    QCAcceptanceSignature,
    QC_QUALITY_MATERIAL_ATTACHMENT_TYPE,
    QCInspectionRecord,
    QCUserBinding,
    ResearchAcceptanceSignature,
    ResearchBatch,
    ResearchBatchAttachment,
    ResearchProject,
    QCWorkOrder,
    QCWorkOrderAttachment,
    QCWorkpiece,
    QCWorkpieceAttachment,
    QCWorkpieceStockHistory,
    Role,
    User,
)
from app.services.auth_service import AuthService
from app.services.qc_service import QCService


def _report_file(name: str = "report.png") -> FileStorage:
    """Create an in-memory qualified-report upload."""
    return FileStorage(stream=io.BytesIO(b"report-bytes"), filename=name, content_type="image/png")


def _seed_qc_users() -> tuple[int, int, int]:
    """Create minimal QC roles/users for integration tests."""
    dept = Department(name="QC")
    db.session.add(dept)
    db.session.flush()

    qc_controller_role = Role(
        name="质量控制员",
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
    qc_inspector_role = Role(
        name="质量检测员",
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
    db.session.add_all([qc_controller_role, qc_inspector_role])
    db.session.flush()

    controller = User(
        username="qc_controller_user",
        password_hash=generate_password_hash("Pass123!"),
        real_name="QC Controller",
        role_id=qc_controller_role.id,
        department_id=dept.id,
        email="controller@example.com",
        is_active=True,
        require_password_change=False,
    )
    inspector = User(
        username="qc_inspector_user",
        password_hash=generate_password_hash("Pass123!"),
        real_name="QC Inspector",
        role_id=qc_inspector_role.id,
        department_id=dept.id,
        email="inspector@example.com",
        is_active=True,
        require_password_change=False,
    )
    db.session.add_all([controller, inspector])
    db.session.commit()

    return controller.id, inspector.id, dept.id


def _seed_research_batch(
    *,
    status: str = "research_submitted",
    with_attachment: bool = True,
) -> dict[str, int]:
    """Create a minimal research project/batch pair for route rendering tests."""
    controller_id, inspector_id, _ = _seed_qc_users()

    project = ResearchProject(
        project_code="PRJ-001",
        project_name="色谱柱连接件开发",
        project_category="方法开发",
        research_direction="接口一致性验证",
        creator_id=controller_id,
    )
    db.session.add(project)
    db.session.flush()

    batch = ResearchBatch(
        batch_no="RB-001",
        project_id=project.id,
        project_name_snapshot=project.project_name,
        sample_quantity=6,
        researcher_id=controller_id,
        reviewer_id=inspector_id,
        status=status,
    )
    if status in ["review_completed", "accepted"]:
        batch.review_completed_at = datetime.now()
    if status == "accepted":
        batch.accepted_at = datetime.now()
    db.session.add(batch)
    db.session.flush()

    if with_attachment:
        db.session.add(
            ResearchBatchAttachment(
                batch_id=batch.id,
                attach_type="experiment_plan",
                source_type="project_snapshot",
                title="实验方案 1",
                content="验证方案说明",
                file_path="experiment_plans/demo_plan.pdf",
                file_type="pdf",
                is_required=True,
                sort_order=0,
            )
        )

    if status == "accepted":
        db.session.add_all(
            [
                ResearchAcceptanceSignature(
                    batch_id=batch.id,
                    signer_id=controller_id,
                    signer_role="researcher",
                ),
                ResearchAcceptanceSignature(
                    batch_id=batch.id,
                    signer_id=inspector_id,
                    signer_role="reviewer",
                ),
            ]
        )

    db.session.commit()
    return {
        "controller_id": controller_id,
        "inspector_id": inspector_id,
        "project_id": project.id,
        "batch_id": batch.id,
    }


def test_quality_control_edit_updates_attachments(app, client, login, monkeypatch):
    """Editing QC work order should persist attachment/meta changes."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

        order = QCWorkOrder(
            batch_no="BATCH-OLD-001",
            workpiece_name="旧工件",
            quantity=10,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.flush()

        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="旧图纸",
                    content="",
                    file_path="drawings/old_drawing.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="instruction",
                    title="旧指导书",
                    content="",
                    file_path="instructions/old_instruction.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="旧检测点",
                    content="旧内容",
                    file_path="inspection_points/old_point.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="remark",
                    title=None,
                    content="旧备注",
                    file_path="remarks/old_remark.png",
                    file_type="png",
                    is_required=False,
                    sort_order=0,
                ),
            ]
        )
        db.session.commit()
        order_id = order.id

    login(controller_id)

    monkeypatch.setattr(
        QCService,
        "_save_uploaded_file",
        lambda file, work_order_id, subfolder: f"{subfolder}/updated_{file.filename}",
    )

    response = client.post(
        f"/qc/quality-control/{order_id}/edit",
        data={
            "batch_no": "BATCH-NEW-001",
            "workpiece_name": "新工件",
            "quantity": "25",
            "drawing": (io.BytesIO(b"new-drawing"), "new_drawing.png"),
            "instruction": (io.BytesIO(b"new-instruction"), "new_instruction.png"),
            "inspection_point_title_0": "新检测点",
            "inspection_point_content_0": "新检测说明",
            "inspection_point_file_0": (io.BytesIO(b"new-point"), "new_point.png"),
            "remark_content_0": "新备注",
            "remark_required_0": "1",
            "remark_file_0": (io.BytesIO(b"new-remark"), "new_remark.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert f"/qc/quality-control/{order_id}" in response.headers.get("Location", "")

    with app.app_context():
        updated_order = QCWorkOrder.query.get(order_id)
        assert updated_order is not None
        assert updated_order.batch_no == "BATCH-NEW-001"
        assert updated_order.workpiece_name == "新工件"
        assert updated_order.quantity == 25.0

        drawing = QCWorkOrderAttachment.query.filter_by(
            work_order_id=order_id, attach_type="drawing"
        ).first()
        assert drawing is not None
        assert drawing.file_path == "drawings/updated_new_drawing.png"

        instruction = QCWorkOrderAttachment.query.filter_by(
            work_order_id=order_id, attach_type="instruction"
        ).first()
        assert instruction is None

        inspection_point = QCWorkOrderAttachment.query.filter_by(
            work_order_id=order_id, attach_type="inspection_point"
        ).first()
        assert inspection_point is not None
        assert inspection_point.title == "新作业指导书"
        assert inspection_point.content == "新检测说明"
        assert inspection_point.file_path == "inspection_points/updated_new_point.png"

        remark = QCWorkOrderAttachment.query.filter_by(
            work_order_id=order_id, attach_type="remark"
        ).first()
        assert remark is not None
        assert remark.content == "新备注"
        assert remark.is_required is True
        assert remark.file_path == "remarks/updated_new_remark.png"


def test_verify_code_cancel_returns_to_login(client):
    """Clicking back-to-login from verify page should clear pending state."""
    with client.session_transaction() as sess:
        sess["pending_verify_user_id"] = 999
        sess["pending_verify_fingerprint"] = "fingerprint"
        sess["pending_verify_remember"] = True
        sess["pending_verify_purpose"] = "login"
        sess["pending_verify_subsystem"] = "qc"

    response = client.get("/auth/login?cancel=1", follow_redirects=False)
    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert "pending_verify_user_id" not in sess
        assert "pending_verify_fingerprint" not in sess
        assert "pending_verify_remember" not in sess
        assert "pending_verify_purpose" not in sess
        assert "pending_verify_subsystem" not in sess

    response = client.get("/auth/verify-code", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers.get("Location", "")


def test_regular_user_with_email_receives_verify_challenge(app, client, monkeypatch):
    """Normal active users with email should enter 2FA verification flow."""
    with app.app_context():
        dept = Department(name="Sales")
        db.session.add(dept)
        db.session.flush()

        role = Role(
            name="Sales Manager",
            code="sales_manager",
            permissions='["contract_view"]',
            level=20,
        )
        db.session.add(role)
        db.session.flush()

        user = User(
            username="regular_with_email",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Regular User",
            role_id=role.id,
            department_id=dept.id,
            email="regular@example.com",
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        db.session.add(user)
        db.session.commit()

    monkeypatch.setattr(
        "app.services.email_service.EmailService.create_verification_code",
        lambda **kwargs: ("1234", None),
    )
    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_verify_code_email",
        lambda *args, **kwargs: (True, None),
    )

    response = client.post(
        "/auth/login",
        data={"username": "regular_with_email", "password": "Pass123!"},
        headers={"User-Agent": "UA-REG", "X-Forwarded-For": "9.9.9.9"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/auth/verify-code" in response.headers.get("Location", "")
    with client.session_transaction() as sess:
        assert "pending_verify_user_id" in sess


def test_quality_control_new_handles_sparse_dynamic_indexes(app, client, login, monkeypatch):
    """Creating work order should not lose dynamic items when indexes are sparse."""
    with app.app_context():
        controller_id, _, _ = _seed_qc_users()

    login(controller_id)

    monkeypatch.setattr(
        QCService,
        "_save_uploaded_file",
        lambda file, work_order_id, subfolder: f"{subfolder}/saved_{file.filename}",
    )

    response = client.post(
        "/qc/quality-control/new",
        data={
            "submit_action": "draft",
            "batch_no": "BATCH-SPARSE-001",
            "workpiece_name": "稀疏索引工件",
            "quantity": "8",
            "drawing": (io.BytesIO(b"drawing"), "drawing.png"),
            "instruction": (io.BytesIO(b"instruction"), "instruction.png"),
            "inspection_point_title_0": "检测点A",
            "inspection_point_content_0": "A内容",
            "inspection_point_file_0": (io.BytesIO(b"point-a"), "point_a.png"),
            "inspection_point_title_2": "检测点B",
            "inspection_point_content_2": "B内容",
            "inspection_point_file_2": (io.BytesIO(b"point-b"), "point_b.png"),
            "remark_content_2": "备注B",
            "remark_required_2": "1",
            "remark_file_2": (io.BytesIO(b"remark-b"), "remark_b.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/qc/quality-control/" in response.headers.get("Location", "")

    with app.app_context():
        order = QCWorkOrder.query.filter_by(batch_no="BATCH-SPARSE-001").first()
        assert order is not None

        points = QCWorkOrderAttachment.query.filter_by(
            work_order_id=order.id, attach_type="inspection_point"
        ).order_by(QCWorkOrderAttachment.sort_order.asc()).all()
        assert len(points) == 2
        assert points[0].title == "作业指导书A"
        assert points[1].title == "作业指导书B"

        remarks = QCWorkOrderAttachment.query.filter_by(
            work_order_id=order.id, attach_type="remark"
        ).all()
        assert len(remarks) == 1
        assert remarks[0].content == "备注B"


def test_outsourced_workpiece_materials_flow_updates_inventory_and_history(app, client, login, monkeypatch):
    """Outsourced workpieces should use QC materials, flow through inspection, and post inventory once."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

    login(controller_id)

    monkeypatch.setattr(
        QCService,
        "_save_workpiece_file",
        staticmethod(lambda file, workpiece_id, subfolder: f"{subfolder}/saved_{file.filename}"),
    )

    response = client.post(
        "/qc/workpieces/new",
        data={
            "workpiece_code": "OUT-MAT-001",
            "workpiece_name": "Outsourced Material Part",
            "workpiece_type": "outsourced",
            "material_title_0": "Supplier CoA",
            "material_content_0": "Lot A",
            "material_file_0": (io.BytesIO(b"coa"), "coa.png"),
            "material_title_3": "Incoming Check",
            "material_content_3": "Lot B",
            "material_file_3": (io.BytesIO(b"check"), "check.pdf"),
            "guide_title_0": "Guide A",
            "guide_content_0": "Check dimension",
            "guide_file_0": (io.BytesIO(b"guide"), "guide.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302

    monkeypatch.setattr(
        QCService,
        "_copy_workpiece_file_to_order",
        staticmethod(
            lambda workpiece_id, work_order_id, relative_path, attach_type: (
                f"{attach_type}/copied_{Path(relative_path).name}",
                Path(relative_path).suffix.lstrip(".") or "png",
            )
        ),
    )
    monkeypatch.setattr(
        QCService,
        "_save_uploaded_file",
        staticmethod(lambda file, work_order_id, subfolder: f"{subfolder}/saved_{file.filename}"),
    )

    with app.app_context():
        workpiece = QCWorkpiece.query.filter_by(workpiece_code="OUT-MAT-001").first()
        assert workpiece is not None
        assert workpiece.is_outsourced is True
        assert workpiece.drawing_attachment is None
        assert len(workpiece.quality_material_attachments) == 2
        assert all(
            material.attach_type == QC_QUALITY_MATERIAL_ATTACHMENT_TYPE
            for material in workpiece.quality_material_attachments
        )

        preview = QCService.serialize_workpiece_preview(workpiece)
        assert preview["workpiece_type"] == "outsourced"
        assert preview["primary_material_label"] == "质检材料"
        assert len(preview["quality_materials"]) == 2

        controller = User.query.get(controller_id)
        inspector = User.query.get(inspector_id)
        order = QCService.create_work_order(
            data={
                "batch_no": "OUT-MAT-BATCH-001",
                "workpiece_id": workpiece.id,
                "workpiece_name": workpiece.workpiece_name,
                "workpiece_type": "outsourced",
                "quantity": "12",
            },
            controller_id=controller_id,
            auto_commit=False,
        )
        QCService.apply_workpiece_to_order(order.id, workpiece.id, controller)
        order = QCWorkOrder.query.get(order.id)

        assert order.is_outsourced is True
        assert len(order.quality_material_attachments) == 2
        assert len(order.primary_material_attachments) == 2

        QCService.complete_quality_control(order.id, inspector.id, controller)
        results = []
        for attachment in order.ordered_attachments:
            results.append(
                {
                    "attachment_id": attachment.id,
                    "result": "pass",
                    "remark": "",
                    "report_file": _report_file(f"report_{attachment.id}.png") if attachment.requires_report else None,
                }
            )
        QCService.submit_inspection(order.id, results, inspector)
        QCService.sign_acceptance(
            order.id,
            controller,
            production_quantity=12,
            accepted_quantity=12,
        )
        QCService.sign_acceptance(order.id, inspector)

        accepted_order = QCWorkOrder.query.get(order.id)
        accepted_workpiece = QCWorkpiece.query.get(workpiece.id)
        assert accepted_order.status == "accepted"
        assert accepted_order.inventory_posted_at is not None
        assert accepted_workpiece.stock_quantity == 12.0
        stock_histories = QCWorkpieceStockHistory.query.filter_by(
            workpiece_id=workpiece.id
        ).order_by(QCWorkpieceStockHistory.id.asc()).all()
        assert len(stock_histories) == 1
        assert stock_histories[0].batch_no == "OUT-MAT-BATCH-001"
        assert stock_histories[0].production_quantity == 12.0
        assert stock_histories[0].accepted_quantity == 12.0
        assert stock_histories[0].quantity_delta == 12.0
        assert stock_histories[0].stock_before == 0.0
        assert stock_histories[0].stock_after == 12.0
        assert stock_histories[0].operator_id == inspector.id
        history_actions = [history.action for history in accepted_order.histories]
        assert "创建工件订单" in history_actions
        assert "应用工件库快照" in history_actions
        assert "验收入库" in history_actions

        QCService.rollback_acceptance(order.id, "inspection", "复测", controller)
        rolled_back_order = QCWorkOrder.query.get(order.id)
        rolled_back_workpiece = QCWorkpiece.query.get(workpiece.id)
        assert rolled_back_order.inventory_posted_at is None
        assert rolled_back_workpiece.stock_quantity == 0.0
        rollback_histories = QCWorkpieceStockHistory.query.filter_by(
            workpiece_id=workpiece.id
        ).order_by(QCWorkpieceStockHistory.id.asc()).all()
        assert len(rollback_histories) == 2
        assert rollback_histories[-1].change_type == "acceptance_reverse"
        assert rollback_histories[-1].quantity_delta == -12.0
        assert rollback_histories[-1].stock_before == 12.0
        assert rollback_histories[-1].stock_after == 0.0
        history_actions = [history.action for history in rolled_back_order.histories]
        assert "撤销入库" in history_actions
        assert "验收回退" in history_actions


def test_self_produced_workpiece_supports_multiple_drawings_and_preview(app, client, login, monkeypatch):
    """Workpieces can omit guides while retaining required drawings and workflow access."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

    login(controller_id)

    form = client.get("/qc/workpieces/new")
    form_text = form.get_data(as_text=True)
    assert form.status_code == 200
    assert "暂未添加作业指导书，可按需添加。" in form_text
    assert "作业指导书 <span class=\"text-danger\">*</span>" not in form_text

    monkeypatch.setattr(
        QCService,
        "_save_workpiece_file",
        staticmethod(lambda file, workpiece_id, subfolder: f"{subfolder}/saved_{file.filename}"),
    )
    monkeypatch.setattr(
        QCService,
        "_copy_workpiece_file_to_order",
        staticmethod(
            lambda workpiece_id, work_order_id, relative_path, attach_type: (
                f"{attach_type}/copied_{Path(relative_path).name}",
                Path(relative_path).suffix.lstrip(".") or "png",
            )
        ),
    )

    response = client.post(
        "/qc/workpieces/new",
        data={
            "workpiece_code": "SELF-DRAW-001",
            "workpiece_name": "Self Drawing Part",
            "workpiece_type": "self_produced",
            "drawing_title_0": "Drawing A",
            "drawing_content_0": "Version A",
            "drawing_file_0": (io.BytesIO(b"draw-a"), "drawing-a.png"),
            "drawing_title_2": "Drawing B",
            "drawing_content_2": "Version B",
            "drawing_file_2": (io.BytesIO(b"draw-b"), "drawing-b.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        controller = User.query.get(controller_id)
        workpiece = QCWorkpiece.query.filter_by(workpiece_code="SELF-DRAW-001").first()
        assert workpiece is not None
        assert len(workpiece.drawing_attachments) == 2
        assert not workpiece.guide_attachments
        assert [drawing.display_title for drawing in workpiece.drawing_attachments] == ["Drawing A", "Drawing B"]

        preview = QCService.serialize_workpiece_preview(workpiece)
        assert len(preview["drawings"]) == 2
        assert preview["drawings"][0]["filename"] == "saved_drawing-a.png"

        order = QCService.create_work_order(
            data={
                "batch_no": "SELF-DRAW-BATCH-001",
                "workpiece_id": workpiece.id,
                "workpiece_name": workpiece.workpiece_name,
                "workpiece_type": "self_produced",
                "quantity": "3",
            },
            controller_id=controller_id,
            auto_commit=False,
        )
        QCService.apply_workpiece_to_order(order.id, workpiece.id, controller)
        order = QCWorkOrder.query.get(order.id)
        assert len(order.drawing_attachments) == 2
        assert len(order.primary_material_attachments) == 2
        assert not order.guide_attachments

        QCService.complete_quality_control(order.id, inspector_id, controller)
        assert QCWorkOrder.query.get(order.id).status == "qc_completed"


def test_cancel_acceptance_signature_reopens_accepted_order_and_reverses_inventory(app):
    """Cancelling a signature should restore acceptance state without full workflow rollback."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

        controller = User.query.get(controller_id)
        inspector = User.query.get(inspector_id)
        workpiece = QCWorkpiece(
            workpiece_code="CANCEL-ACCEPT-001",
            workpiece_name="Cancel Acceptance",
            creator_id=controller_id,
            stock_quantity=0,
        )
        db.session.add(workpiece)
        db.session.flush()
        order = QCWorkOrder(
            batch_no="BATCH-CANCEL-ACCEPT",
            workpiece_id=workpiece.id,
            workpiece_name=workpiece.workpiece_name,
            quantity=4,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="inspection_completed",
        )
        db.session.add(order)
        db.session.commit()

        QCService.sign_acceptance(
            order.id,
            controller,
            production_quantity=4,
            accepted_quantity=4,
        )
        QCService.sign_acceptance(order.id, inspector)
        accepted = QCWorkOrder.query.get(order.id)
        assert accepted.status == "accepted"
        assert workpiece.stock_quantity == 4

        with pytest.raises(ValueError):
            QCService.cancel_acceptance_signature(order.id, "qc_inspector", inspector)

        QCService.rollback_acceptance(order.id, "inspection", "误操作", controller)
        reopened = QCWorkOrder.query.get(order.id)
        assert reopened.status == "inspection_pending"
        assert reopened.accepted_at is None
        assert reopened.inventory_posted_at is None
        assert workpiece.stock_quantity == 0
        assert not reopened.signatures
        assert not reopened.acceptance_batches
        assert "验收回退" in [history.action for history in reopened.histories]


def test_qc_inspector_cannot_open_quality_control_module(app, client, login):
    """Inspector should be blocked from QC quality-control pages."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        order = QCWorkOrder(
            batch_no="BATCH-INSPECTOR-BLOCK",
            workpiece_name="Inspector Block",
            quantity=1,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id

    login(inspector_id)
    list_resp = client.get("/qc/quality-control/", follow_redirects=False)
    assert list_resp.status_code == 302
    assert "/qc/quality-inspection/" in list_resp.headers.get("Location", "")

    detail_resp = client.get(f"/qc/quality-control/{order_id}", follow_redirects=False)
    assert detail_resp.status_code == 302
    assert "/qc/quality-inspection/" in detail_resp.headers.get("Location", "")


def test_rejected_records_remain_after_controller_resubmit(app):
    """Failed inspection records should remain until next inspection submission."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

        order = QCWorkOrder(
            batch_no="BATCH-REJECT-KEEP",
            workpiece_name="Reject Keep",
            quantity=5,
            controller_id=controller_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.flush()

        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/d.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="instruction",
                    title="Instruction",
                    content="",
                    file_path="instructions/i.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="P1",
                    content="check",
                    file_path="inspection_points/p.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
            ]
        )
        db.session.commit()

        controller = User.query.get(controller_id)
        inspector = User.query.get(inspector_id)
        QCService.complete_quality_control(order.id, inspector.id, controller)

        attachments = QCWorkOrderAttachment.query.filter_by(work_order_id=order.id).all()
        results = []
        for att in attachments:
            results.append(
                {
                    "attachment_id": att.id,
                    "result": "fail" if att.attach_type == "inspection_point" else "pass",
                    "remark": "failed point" if att.attach_type == "inspection_point" else "",
                    "report_file": _report_file(f"rejected_{att.id}.png"),
                }
            )
        QCService.submit_inspection(order.id, results, inspector)
        record_count_before = len(order.inspection_records)
        assert record_count_before > 0

        QCService.complete_quality_control(order.id, inspector.id, controller)
        refreshed = QCWorkOrder.query.get(order.id)
        assert refreshed.status == "qc_completed"
        assert len(refreshed.inspection_records) == record_count_before


def test_completed_qc_orders_stay_locked_for_managers(app):
    """Full manager access must still respect completed-order locks."""
    with app.app_context():
        dept = Department(name="GM")
        db.session.add(dept)
        db.session.flush()

        general_manager_role = Role(
            name="General Manager",
            code="general_manager",
            permissions='["qc_work_order_view"]',
            level=90,
        )
        gm_assistant_role = Role(
            name="GM Assistant",
            code="gm_assistant",
            permissions='["qc_work_order_view"]',
            level=80,
        )
        qc_controller_role = Role(
            name="QC Controller",
            code="qc_controller",
            permissions='["qc_work_order_edit"]',
            level=55,
        )
        db.session.add_all([general_manager_role, gm_assistant_role, qc_controller_role])
        db.session.flush()

        general_manager = User(
            username="gm_readonly",
            password_hash=generate_password_hash("Pass123!"),
            real_name="General Manager",
            role_id=general_manager_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )

        gm_assistant = User(
            username="gm_assistant_edit",
            password_hash=generate_password_hash("Pass123!"),
            real_name="GM Assistant",
            role_id=gm_assistant_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        controller = User(
            username="controller_edit",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Controller",
            role_id=qc_controller_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        db.session.add_all([general_manager, gm_assistant, controller])
        db.session.flush()

        order = QCWorkOrder(
            batch_no="BATCH-ACCEPTED-EDIT",
            workpiece_name="Accepted",
            quantity=2,
            controller_id=controller.id,
            status="accepted",
        )
        db.session.add(order)
        db.session.commit()

        assert QCService.can_view_work_order(general_manager, order) is True
        assert QCService.can_edit_work_order(general_manager, order) is False
        assert order.can_be_viewed_by(general_manager) is True
        assert order.can_be_edited_by(general_manager) is False

        assert QCService.can_view_work_order(gm_assistant, order) is True
        assert QCService.can_edit_work_order(gm_assistant, order) is False
        assert order.can_be_viewed_by(gm_assistant) is True
        assert order.can_be_edited_by(gm_assistant) is False
        assert QCService.can_delete_work_order(general_manager, order) is False
        assert QCService.can_delete_work_order(gm_assistant, order) is False
        assert order.can_be_deleted_by(general_manager) is False
        assert order.can_be_deleted_by(gm_assistant) is False


def test_qc_delete_permissions_match_role_rules(app):
    """Draft deletion follows roles while progressed orders remain locked."""
    with app.app_context():
        dept = Department(name="QC Delete")
        db.session.add(dept)
        db.session.flush()

        super_role = Role(name="Super", code="superadmin", permissions="[]", level=999)
        gm_role = Role(name="GM", code="general_manager", permissions='["qc_work_order_view","qc_work_order_delete"]', level=90)
        assistant_role = Role(name="Assistant", code="gm_assistant", permissions='["qc_work_order_view","qc_work_order_delete"]', level=80)
        controller_role = Role(name="Controller", code="qc_controller", permissions='["qc_work_order_create","qc_work_order_delete"]', level=55)
        inspector_role = Role(name="Inspector", code="qc_inspector", permissions='["qc_inspection_perform"]', level=45)
        db.session.add_all([super_role, gm_role, assistant_role, controller_role, inspector_role])
        db.session.flush()

        superadmin = User(
            username="qc_delete_super",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Super",
            role_id=super_role.id,
            department_id=dept.id,
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        gm = User(
            username="qc_delete_gm",
            password_hash=generate_password_hash("Pass123!"),
            real_name="GM",
            role_id=gm_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        assistant = User(
            username="qc_delete_assistant",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Assistant",
            role_id=assistant_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        owner = User(
            username="qc_delete_owner",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Owner",
            role_id=controller_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        other_controller = User(
            username="qc_delete_other_controller",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Other Controller",
            role_id=controller_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        inspector = User(
            username="qc_delete_inspector",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Inspector",
            role_id=inspector_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        db.session.add_all([superadmin, gm, assistant, owner, other_controller, inspector])
        db.session.flush()

        order = QCWorkOrder(
            batch_no="BATCH-DELETE-RULES",
            workpiece_name="Delete Rules",
            quantity=1,
            controller_id=owner.id,
            inspector_id=inspector.id,
            status="draft",
        )
        db.session.add(order)
        db.session.commit()

        assert QCService.can_delete_work_order(superadmin, order) is True
        assert QCService.can_delete_work_order(gm, order) is True
        assert QCService.can_delete_work_order(assistant, order) is True
        assert QCService.can_delete_work_order(owner, order) is True
        assert QCService.can_delete_work_order(other_controller, order) is False
        assert QCService.can_delete_work_order(inspector, order) is False


def test_qc_delete_route_honors_role_permissions(app, client, login):
    """Delete route allows managers for drafts but locks progressed orders."""
    with app.app_context():
        dept = Department(name="QC Delete Route")
        db.session.add(dept)
        db.session.flush()

        gm_role = Role(name="GM", code="general_manager", permissions='["qc_work_order_view","qc_work_order_delete"]', level=90)
        controller_role = Role(name="Controller", code="qc_controller", permissions='["qc_work_order_create","qc_work_order_delete"]', level=55)
        inspector_role = Role(name="Inspector", code="qc_inspector", permissions='["qc_inspection_perform"]', level=45)
        db.session.add_all([gm_role, controller_role, inspector_role])
        db.session.flush()

        gm = User(
            username="qc_delete_route_gm",
            password_hash=generate_password_hash("Pass123!"),
            real_name="GM",
            role_id=gm_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        owner = User(
            username="qc_delete_route_owner",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Owner",
            role_id=controller_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        inspector = User(
            username="qc_delete_route_inspector",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Inspector",
            role_id=inspector_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        db.session.add_all([gm, owner, inspector])
        db.session.flush()

        deletable = QCWorkOrder(
            batch_no="BATCH-DELETE-BY-GM",
            workpiece_name="Delete By GM",
            quantity=2,
            controller_id=owner.id,
            inspector_id=inspector.id,
            status="draft",
        )
        blocked = QCWorkOrder(
            batch_no="BATCH-DELETE-BLOCKED",
            workpiece_name="Delete Blocked",
            quantity=2,
            controller_id=owner.id,
            inspector_id=inspector.id,
            status="draft",
        )
        locked = QCWorkOrder(
            batch_no="BATCH-DELETE-LOCKED",
            workpiece_name="Delete Locked",
            quantity=2,
            controller_id=owner.id,
            inspector_id=inspector.id,
            status="qc_completed",
        )
        db.session.add_all([deletable, blocked, locked])
        db.session.commit()
        gm_id = gm.id
        inspector_id = inspector.id
        deletable_id = deletable.id
        blocked_id = blocked.id
        locked_id = locked.id

    login(gm_id)
    gm_response = client.post(f"/qc/quality-control/{deletable_id}/delete", follow_redirects=False)
    assert gm_response.status_code == 302
    with app.app_context():
        assert QCWorkOrder.query.get(deletable_id) is None

    gm_locked_response = client.post(
        f"/qc/quality-control/{locked_id}/delete",
        follow_redirects=False,
    )
    assert gm_locked_response.status_code == 302
    with app.app_context():
        assert QCWorkOrder.query.get(locked_id) is not None

    login(inspector_id)
    inspector_response = client.post(f"/qc/quality-control/{blocked_id}/delete", follow_redirects=False)
    assert inspector_response.status_code == 302
    with app.app_context():
        assert QCWorkOrder.query.get(blocked_id) is not None


def test_gm_assistant_dashboard_links_to_qc_order_list_and_detail(app, client, login):
    """GM assistant should receive full QC workflow access."""
    with app.app_context():
        dept = Department(name="GM Dashboard")
        db.session.add(dept)
        db.session.flush()

        gm_assistant_role = Role(
            name="GM Assistant",
            code="gm_assistant",
            permissions='["qc_work_order_view"]',
            level=80,
        )
        qc_controller_role = Role(
            name="QC Controller",
            code="qc_controller",
            permissions='["qc_work_order_create", "qc_work_order_edit"]',
            level=55,
        )
        db.session.add_all([gm_assistant_role, qc_controller_role])
        db.session.flush()

        gm_assistant = User(
            username="gm_assistant_dashboard",
            password_hash=generate_password_hash("Pass123!"),
            real_name="GM Assistant",
            role_id=gm_assistant_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        controller = User(
            username="controller_dashboard",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Controller",
            role_id=qc_controller_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        db.session.add_all([gm_assistant, controller])
        db.session.flush()

        order = QCWorkOrder(
            batch_no="BATCH-DASHBOARD-001",
            workpiece_name="Dashboard Order",
            quantity=3,
            controller_id=controller.id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.commit()
        gm_assistant_id = gm_assistant.id
        order_id = order.id

    login(gm_assistant_id)

    dashboard = client.get("/qc/production/")
    assert dashboard.status_code == 200
    assert b"/qc/quality-control/" in dashboard.data
    assert f"/qc/quality-control/{order_id}".encode() in dashboard.data

    detail = client.get(f"/qc/quality-control/{order_id}")
    assert detail.status_code == 200
    assert b"/qc/quality-control/" in detail.data
    assert b"/edit" in detail.data
    assert b"/complete" in detail.data


def test_qc_detail_pages_handle_empty_inspection_records(app, client, login):
    """QC detail and acceptance pages should not crash when inspection records are empty."""
    with app.app_context():
        dept = Department(name="QC Empty")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(
            name="SuperAdmin",
            code="superadmin",
            permissions="[]",
            level=999,
        )
        qc_controller_role = Role(
            name="QC Controller",
            code="qc_controller",
            permissions='["qc_work_order_create", "qc_work_order_edit", "qc_acceptance_perform"]',
            level=55,
        )
        qc_inspector_role = Role(
            name="QC Inspector",
            code="qc_inspector",
            permissions='["qc_inspection_perform"]',
            level=45,
        )
        db.session.add_all([superadmin_role, qc_controller_role, qc_inspector_role])
        db.session.flush()

        superadmin = User(
            username="qc_empty_admin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Admin",
            role_id=superadmin_role.id,
            department_id=dept.id,
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        controller = User(
            username="qc_empty_controller",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Controller",
            role_id=qc_controller_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        inspector = User(
            username="qc_empty_inspector",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Inspector",
            role_id=qc_inspector_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        db.session.add_all([superadmin, controller, inspector])
        db.session.flush()

        order = QCWorkOrder(
            batch_no="BATCH-EMPTY-RECORDS",
            workpiece_name="Empty Records",
            quantity=5,
            controller_id=controller.id,
            inspector_id=inspector.id,
            status="inspection_completed",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/sample.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="instruction",
                    title="Instruction",
                    content="",
                    file_path="instructions/sample.png",
                    file_type="png",
                    is_required=True,
                    sort_order=1,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Point 1",
                    content="Need review",
                    file_path="inspection_points/sample.png",
                    file_type="png",
                    is_required=True,
                    sort_order=2,
                ),
            ]
        )
        db.session.commit()
        superadmin_id = superadmin.id
        inspector_id = inspector.id
        order_id = order.id

    login(inspector_id)
    inspection_detail = client.get(f"/qc/quality-inspection/{order_id}")
    assert inspection_detail.status_code == 200

    login(superadmin_id)
    acceptance_detail = client.get(f"/qc/acceptance/{order_id}")
    assert acceptance_detail.status_code == 200
    acceptance_print = client.get(f"/qc/acceptance/{order_id}/print")
    assert acceptance_print.status_code == 200


def test_qc_only_user_hidden_from_erp_list_and_cannot_register_into_erp(app, client, login):
    """QC-only users are hidden from ERP list and cannot be re-registered into ERP."""
    with app.app_context():
        dept = Department(name="ERP")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(
            name="SuperAdmin",
            code="superadmin",
            permissions="[]",
            level=999,
        )
        sales_role = Role(
            name="Sales",
            code="sales_manager",
            permissions='["contract_view"]',
            level=20,
        )
        qc_inspector_role = Role(
            name="QC Inspector",
            code="qc_inspector",
            permissions='["qc_work_order_view"]',
            level=45,
        )
        db.session.add_all([superadmin_role, sales_role, qc_inspector_role])
        db.session.flush()

        superadmin = User(
            username="erp_superadmin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="ERP SA",
            role_id=superadmin_role.id,
            department_id=dept.id,
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
            email="sa_erp@example.com",
        )
        qc_only = User(
            username="same_name_user",
            password_hash=generate_password_hash("QcPass123"),
            real_name="QC Only",
            role_id=qc_inspector_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
            email="qc_only@example.com",
        )
        db.session.add_all([superadmin, qc_only])
        db.session.commit()
        superadmin_id = superadmin.id

    login(superadmin_id)
    response = client.get("/user/", follow_redirects=False)
    assert response.status_code == 200
    assert b"same_name_user" not in response.data

    with app.app_context():
        user, error = AuthService.register_user(
            username="same_name_user",
            real_name="ERP Version",
            role_code="sales_manager",
            department_id=1,
            email="erp_version@example.com",
            phone="13800000000",
        )
        assert user is None
        assert error is not None
        assert "QC" in error


def test_complete_quality_control_requires_active_qc_inspector(app):
    """QC completion should only accept active users with qc_inspector role."""
    with app.app_context():
        controller_id, inspector_id, dept_id = _seed_qc_users()

        sales_role = Role(
            name="Sales",
            code="sales_manager",
            permissions='["contract_view"]',
            level=20,
        )
        db.session.add(sales_role)
        db.session.flush()

        wrong_role_user = User(
            username="wrong_role_for_qc",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Wrong Role",
            role_id=sales_role.id,
            department_id=dept_id,
            is_active=True,
            require_password_change=False,
        )
        inactive_inspector = User(
            username="inactive_inspector_for_qc",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Inactive Inspector",
            role_id=Role.query.filter_by(code="qc_inspector").first().id,
            department_id=dept_id,
            is_active=False,
            require_password_change=False,
        )
        db.session.add_all([wrong_role_user, inactive_inspector])
        db.session.flush()

        order = QCWorkOrder(
            batch_no="BATCH-INSPECTOR-VALIDATION",
            workpiece_name="Inspector Validation",
            quantity=3,
            controller_id=controller_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.flush()

        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/d.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="instruction",
                    title="Instruction",
                    content="",
                    file_path="instructions/i.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Point",
                    content="check",
                    file_path="inspection_points/p.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
            ]
        )
        db.session.commit()

        controller = User.query.get(controller_id)
        valid_inspector = User.query.get(inspector_id)

        with pytest.raises(ValueError, match="供应商"):
            QCService.complete_quality_control(order.id, wrong_role_user.id, controller)

        with pytest.raises(ValueError, match="已激活"):
            QCService.complete_quality_control(order.id, inactive_inspector.id, controller)

        updated = QCService.complete_quality_control(order.id, valid_inspector.id, controller)
        assert updated.status == "qc_completed"
        assert updated.inspector_id == valid_inspector.id


def test_submit_inspection_requires_full_and_unique_results(app):
    """Inspection submission must cover every attachment exactly once."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        controller = User.query.get(controller_id)
        inspector = User.query.get(inspector_id)

        order = QCWorkOrder(
            batch_no="BATCH-INSPECTION-COVERAGE",
            workpiece_name="Inspection Coverage",
            quantity=4,
            controller_id=controller_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.flush()

        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/d.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="instruction",
                    title="Instruction",
                    content="",
                    file_path="instructions/i.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Point",
                    content="check",
                    file_path="inspection_points/p.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
            ]
        )
        db.session.commit()

        QCService.complete_quality_control(order.id, inspector_id, controller)
        attachments = QCWorkOrderAttachment.query.filter_by(work_order_id=order.id).all()

        partial_results = [
            {"attachment_id": attachments[0].id, "result": "pass", "remark": "", "report_file": _report_file("partial_0.png")},
            {"attachment_id": attachments[1].id, "result": "pass", "remark": "", "report_file": _report_file("partial_1.png")},
        ]
        with pytest.raises(ValueError, match="完成所有项目"):
            QCService.submit_inspection(order.id, partial_results, inspector)

        duplicate_results = [
            {"attachment_id": attachments[0].id, "result": "pass", "remark": "", "report_file": _report_file("dup_0.png")},
            {"attachment_id": attachments[1].id, "result": "pass", "remark": "", "report_file": _report_file("dup_1.png")},
            {"attachment_id": attachments[1].id, "result": "fail", "remark": "dup", "report_file": _report_file("dup_2.png")},
            {"attachment_id": attachments[2].id, "result": "pass", "remark": "", "report_file": _report_file("dup_3.png")},
        ]
        with pytest.raises(ValueError, match="重复"):
            QCService.submit_inspection(order.id, duplicate_results, inspector)

        valid_results = [
            {"attachment_id": attachments[0].id, "result": "pass", "remark": "", "report_file": _report_file("valid_0.png")},
            {"attachment_id": attachments[1].id, "result": "pass", "remark": "", "report_file": _report_file("valid_1.png")},
            {"attachment_id": attachments[2].id, "result": "pass", "remark": "", "report_file": _report_file("valid_2.png")},
        ]
        updated = QCService.submit_inspection(order.id, valid_results, inspector)
        assert updated.status == "inspection_completed"


def test_qc_only_user_cannot_login_from_erp_entry(app, client, monkeypatch):
    """QC-only account should be blocked from ERP login entry and allowed in QC entry."""
    with app.app_context():
        dept = Department(name="QC-Only")
        db.session.add(dept)
        db.session.flush()

        qc_role = Role(
            name="QC Inspector",
            code="qc_inspector",
            permissions='["qc_work_order_view","qc_inspection_perform"]',
            level=45,
        )
        db.session.add(qc_role)
        db.session.flush()

        qc_user = User(
            username="qc_only_login_user",
            password_hash=generate_password_hash("Pass123!"),
            real_name="QC Only Login",
            role_id=qc_role.id,
            department_id=dept.id,
            email="qc_only_login@example.com",
            is_active=True,
            require_password_change=False,
        )
        db.session.add(qc_user)
        db.session.flush()

        binding = QCUserBinding(
            user_id=qc_user.id,
            role_id=qc_role.id,
            is_active=True,
        )
        db.session.add(binding)
        db.session.commit()

    monkeypatch.setattr(
        "app.services.email_service.EmailService.is_trusted_device",
        lambda *args, **kwargs: True,
    )

    erp_resp = client.post(
        "/auth/login",
        data={"username": "qc_only_login_user", "password": "Pass123!"},
        headers={"User-Agent": "UA-QC-ONLY", "X-Forwarded-For": "10.10.10.10"},
        follow_redirects=False,
    )
    assert erp_resp.status_code == 302
    assert "/auth/login" in erp_resp.headers.get("Location", "")
    with client.session_transaction() as sess:
        assert "user_id" not in sess

    qc_resp = client.post(
        "/auth/login?sub=qc",
        data={"username": "qc_only_login_user", "password": "Pass123!"},
        headers={"User-Agent": "UA-QC-ONLY", "X-Forwarded-For": "10.10.10.10"},
        follow_redirects=False,
    )
    assert qc_resp.status_code == 302
    assert "/qc/" in qc_resp.headers.get("Location", "")


def test_quality_control_new_without_submit_action_does_not_persist(app, client, login):
    """New QC form should not persist any record without explicit action."""
    with app.app_context():
        controller_id, _, _ = _seed_qc_users()

    login(controller_id)
    response = client.post(
        "/qc/quality-control/new",
        data={
            "batch_no": "BATCH-NO-ACTION",
            "workpiece_name": "No Action",
            "quantity": "5",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200

    with app.app_context():
        order = QCWorkOrder.query.filter_by(batch_no="BATCH-NO-ACTION").first()
        assert order is None


def test_draft_visibility_includes_management(app, client, login):
    """Draft work orders should remain visible to management under its existing full access."""
    with app.app_context():
        dept = Department(name="QC Draft")
        db.session.add(dept)
        db.session.flush()

        super_role = Role(name="Super", code="superadmin", permissions="[]", level=999)
        gm_role = Role(name="GM", code="general_manager", permissions='["contract_view"]', level=90)
        controller_role = Role(name="QC Controller", code="qc_controller", permissions='["qc_work_order_view"]', level=55)
        db.session.add_all([super_role, gm_role, controller_role])
        db.session.flush()

        superadmin = User(
            username="draft_superadmin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Draft SA",
            role_id=super_role.id,
            department_id=dept.id,
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
            email="draft_sa@example.com",
        )
        owner = User(
            username="draft_owner",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Draft Owner",
            role_id=controller_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
            email="draft_owner@example.com",
        )
        gm = User(
            username="draft_gm",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Draft GM",
            role_id=gm_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
            email="draft_gm@example.com",
        )
        db.session.add_all([superadmin, owner, gm])
        db.session.flush()
        gm_id = gm.id

        draft = QCService.create_work_order(
            data={"batch_no": "BATCH-DRAFT-VIS", "workpiece_name": "Draft Visible", "quantity": "1"},
            controller_id=owner.id,
            status="draft",
        )
        db.session.commit()

        assert QCService.can_view_work_order(owner, draft) is True
        assert QCService.can_view_work_order(superadmin, draft) is True
        assert QCService.can_view_work_order(gm, draft) is True
        assert draft.can_be_viewed_by(gm) is True
        assert QCService.can_edit_work_order(gm, draft) is True
        assert [order.id for order in QCService.get_work_order_list(gm).items] == [draft.id]
        assert [order.id for order in QCService.get_recent_work_orders(gm)] == [draft.id]
        draft_id = draft.id

    login(gm_id)
    list_response = client.get('/qc/quality-control/')
    detail_response = client.get(f'/qc/quality-control/{draft_id}')
    assert list_response.status_code == 200
    assert 'BATCH-DRAFT-VIS' in list_response.get_data(as_text=True)
    assert detail_response.status_code == 200
    assert '发起人、管理层和系统管理员可见' in detail_response.get_data(as_text=True)


def test_qc_work_order_batch_no_can_repeat_and_update_to_existing_value(app):
    """Separate work orders may reuse one business batch number."""
    with app.app_context():
        controller_id, _, _ = _seed_qc_users()
        controller = db.session.get(User, controller_id)

        first_order = QCService.create_work_order(
            data={
                'batch_no': 'REPEAT-BATCH-001',
                'workpiece_name': '第一批工件',
                'quantity': '1',
            },
            controller_id=controller_id,
            status='draft',
        )
        second_order = QCService.create_work_order(
            data={
                'batch_no': 'REPEAT-BATCH-002',
                'workpiece_name': '第二批工件',
                'quantity': '2',
            },
            controller_id=controller_id,
            status='draft',
        )
        db.session.commit()

        updated_order = QCService.update_work_order(
            second_order.id,
            {
                'batch_no': first_order.batch_no,
                'workpiece_name': second_order.workpiece_name,
                'quantity': str(second_order.quantity),
            },
            controller,
        )

        matching_orders = QCWorkOrder.query.filter_by(batch_no='REPEAT-BATCH-001').all()
        assert {order.id for order in matching_orders} == {first_order.id, second_order.id}
        assert updated_order.id == second_order.id


def test_batch_number_schema_upgrade_replaces_unique_lookup_index(app):
    """The startup migration must preserve rows while removing the legacy unique index."""
    with app.app_context():
        with db.engine.begin() as connection:
            connection.exec_driver_sql('DROP INDEX IF EXISTS ix_qc_work_orders_batch_no')
            connection.exec_driver_sql(
                'CREATE UNIQUE INDEX ix_qc_work_orders_batch_no ON qc_work_orders (batch_no)'
            )

        _ensure_qc_work_order_batch_no_index()

        with db.engine.connect() as connection:
            index_rows = connection.exec_driver_sql('PRAGMA index_list(qc_work_orders)').fetchall()
            batch_indexes = []
            for index_row in index_rows:
                index_name = index_row[1].replace('"', '""')
                columns = connection.exec_driver_sql(
                    f'PRAGMA index_info("{index_name}")'
                ).fetchall()
                if [column_row[2] for column_row in columns] == ['batch_no']:
                    batch_indexes.append(bool(index_row[2]))
        assert batch_indexes == [False]


def test_batch_number_schema_upgrade_rebuilds_legacy_table_constraint(app):
    """The migration must also handle early SQLite tables with a UNIQUE constraint."""
    with app.app_context():
        raw_connection = db.engine.raw_connection()
        try:
            cursor = raw_connection.cursor()
            cursor.execute('PRAGMA foreign_keys=OFF')
            cursor.execute('DROP TABLE qc_work_orders')
            cursor.execute(
                '''
                CREATE TABLE qc_work_orders (
                    id INTEGER PRIMARY KEY,
                    batch_no VARCHAR(100) UNIQUE NOT NULL,
                    workpiece_name VARCHAR(200) NOT NULL,
                    quantity FLOAT NOT NULL,
                    controller_id INTEGER NOT NULL
                )
                '''
            )
            cursor.execute(
                "INSERT INTO qc_work_orders (batch_no, workpiece_name, quantity, controller_id) "
                "VALUES ('LEGACY-REPEAT-001', '旧版工件', 1, 1)"
            )
            raw_connection.commit()
            cursor.execute('PRAGMA foreign_keys=ON')
        finally:
            raw_connection.close()

        _ensure_qc_work_order_batch_no_index()

        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO qc_work_orders (batch_no, workpiece_name, quantity, controller_id) "
                "VALUES ('LEGACY-REPEAT-001', '新版工件', 2, 1)"
            )
            matching_count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM qc_work_orders WHERE batch_no = 'LEGACY-REPEAT-001'"
            ).scalar_one()
        assert matching_count == 2


def test_qc_order_edit_window_locks_after_submission_and_reopens_after_return(app, client, login):
    """Orders are editable only before submission, then reopen through a formal return state."""
    with app.app_context():
        controller_id, inspector_id, department_id = _seed_qc_users()
        super_role = Role(name='Lock Super', code='superadmin', permissions='[]', level=999)
        db.session.add(super_role)
        db.session.flush()
        superadmin = User(
            username='lock_superadmin',
            password_hash=generate_password_hash('Pass123!'),
            real_name='Lock Superadmin',
            role_id=super_role.id,
            department_id=department_id,
            email='lock_superadmin@example.com',
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        order = QCWorkOrder(
            batch_no='LOCK-WINDOW-001',
            workpiece_name='可编辑窗口工件',
            quantity=1,
            controller_id=controller_id,
            status='qc_pending',
        )
        db.session.add_all([superadmin, order])
        db.session.flush()
        drawing = QCWorkOrderAttachment(
            work_order_id=order.id,
            attach_type='drawing',
            title='必需图纸',
            content='',
            file_path='drawings/lock-window.png',
            file_type='png',
            is_required=True,
            sort_order=0,
        )
        db.session.add(drawing)
        db.session.commit()
        order_id = order.id
        drawing_id = drawing.id
        superadmin_id = superadmin.id

    login(controller_id)
    editable_detail = client.get(f'/qc/quality-control/{order_id}')
    editable_form = client.get(f'/qc/quality-control/{order_id}/edit')
    assert editable_detail.status_code == 200
    assert '编辑订单（提交前）' in editable_detail.get_data(as_text=True)
    assert editable_form.status_code == 200
    assert '当前订单尚未提交至质量检测' in editable_form.get_data(as_text=True)

    with app.app_context():
        controller = db.session.get(User, controller_id)
        superadmin = db.session.get(User, superadmin_id)
        order = db.session.get(QCWorkOrder, order_id)

        QCService.update_work_order(
            order_id,
            {
                'batch_no': order.batch_no,
                'workpiece_name': order.workpiece_name,
                'workpiece_type': order.workpiece_type,
                'quantity': '2',
            },
            controller,
        )
        order = db.session.get(QCWorkOrder, order_id)
        assert order.quantity == 2
        assert any(
            history.action == '编辑工件订单' and '生产数量：1 -> 2' in (history.detail or '')
            for history in order.histories
        )

        QCService.complete_quality_control(order_id, inspector_id, controller)
        order = db.session.get(QCWorkOrder, order_id)
        assert order.status == 'qc_completed'
        assert order.is_editable_before_quality_submission is False
        assert QCService.can_edit_work_order(controller, order) is False
        assert QCService.can_edit_work_order(superadmin, order) is False
        assert QCService.can_delete_work_order(superadmin, order) is False
        assert any(
            history.action == '完成质量控制' and '基础信息已锁定' in (history.detail or '')
            for history in order.histories
        )

        with pytest.raises(ValueError, match='没有权限编辑此订单'):
            QCService.update_work_order(
                order_id,
                {
                    'batch_no': order.batch_no,
                    'workpiece_name': order.workpiece_name,
                    'workpiece_type': order.workpiece_type,
                    'quantity': '3',
                },
                superadmin,
            )
        with pytest.raises(ValueError, match='没有权限编辑此订单'):
            QCService.sync_order_section_files(order_id, None, None, None, superadmin)
        with pytest.raises(ValueError, match='没有权限删除此订单'):
            QCService.delete_work_order(order_id, superadmin)
        with pytest.raises(ValueError, match='没有权限编辑此附件'):
            QCService.update_attachment_meta(drawing_id, title='不应修改', user=superadmin)

    submitted_detail = client.get(f'/qc/quality-control/{order_id}')
    submitted_edit = client.get(f'/qc/quality-control/{order_id}/edit', follow_redirects=False)
    assert submitted_detail.status_code == 200
    assert '编辑订单（提交前）' not in submitted_detail.get_data(as_text=True)
    assert submitted_edit.status_code == 302

    with app.app_context():
        controller = db.session.get(User, controller_id)
        order = db.session.get(QCWorkOrder, order_id)
        order.status = 'rejected'
        db.session.commit()
        assert order.is_editable_before_quality_submission is True
        assert QCService.can_edit_work_order(controller, order) is True

    reopened_detail = client.get(f'/qc/quality-control/{order_id}')
    reopened_edit = client.get(f'/qc/quality-control/{order_id}/edit')
    assert reopened_detail.status_code == 200
    assert '编辑订单（提交前）' in reopened_detail.get_data(as_text=True)
    assert reopened_edit.status_code == 200


def test_qc_admin_menu_contains_required_items_without_department(app, client, login):
    """QC system-management menu should expose required entries and hide department management."""
    with app.app_context():
        dept = Department(name="Admin")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(
            name="Super Admin",
            code="superadmin",
            permissions="[]",
            level=999,
        )
        db.session.add(superadmin_role)
        db.session.flush()

        admin = User(
            username="qc_admin_menu_user",
            password_hash=generate_password_hash("Pass123!"),
            real_name="QC Admin",
            role_id=superadmin_role.id,
            department_id=dept.id,
            email="qc_admin_menu@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    login(admin_id)
    response = client.get("/qc/admin/users", follow_redirects=False)
    assert response.status_code == 200
    assert b"/qc/admin/users" in response.data
    assert b"/qc/admin/pending" in response.data
    assert b"/qc/admin/roles" in response.data
    assert b"/settings/email" in response.data
    assert b"/backup/" in response.data
    assert b"/department" not in response.data


def test_qc_admin_users_only_shows_qc_scope_users(app, client, login):
    """QC user-management list should not include ERP-only accounts."""
    with app.app_context():
        dept = Department(name="Scope")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(
            name="Super Admin",
            code="superadmin",
            permissions="[]",
            level=999,
        )
        qc_controller_role = Role(
            name="QC Controller",
            code="qc_controller",
            permissions='["qc_work_order_view"]',
            level=50,
        )
        sales_role = Role(
            name="Sales Manager",
            code="sales_manager_scope",
            permissions='["contract_view"]',
            level=20,
        )
        db.session.add_all([superadmin_role, qc_controller_role, sales_role])
        db.session.flush()

        admin = User(
            username="qc_admin_scope",
            password_hash=generate_password_hash("Pass123!"),
            real_name="QC Admin Scope",
            role_id=superadmin_role.id,
            department_id=dept.id,
            email="qc_admin_scope@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        qc_user = User(
            username="qc_scope_user",
            password_hash=generate_password_hash("Pass123!"),
            real_name="QC Scope User",
            role_id=qc_controller_role.id,
            department_id=dept.id,
            email="qc_scope_user@example.com",
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        erp_user = User(
            username="erp_only_scope_user",
            password_hash=generate_password_hash("Pass123!"),
            real_name="ERP Only User",
            role_id=sales_role.id,
            department_id=dept.id,
            email="erp_only_scope@example.com",
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        db.session.add_all([admin, qc_user, erp_user])
        db.session.commit()
        admin_id = admin.id

    login(admin_id)
    response = client.get("/qc/admin/users", follow_redirects=False)
    assert response.status_code == 200
    assert b"qc_scope_user" in response.data
    assert b"erp_only_scope_user" not in response.data


def test_qc_manager_navigation_and_admin_visibility(app, client, login):
    """GM and GM assistant both receive full AI CATS administration access."""
    with app.app_context():
        dept = Department(name="QC Managers")
        db.session.add(dept)
        db.session.flush()

        gm_role = Role(
            name="General Manager",
            code="general_manager",
            permissions='["qc_work_order_view","qc_inspection_view","qc_acceptance_perform"]',
            level=90,
        )
        gm_assistant_role = Role(
            name="GM Assistant",
            code="gm_assistant",
            permissions='["qc_work_order_view","qc_inspection_view","qc_acceptance_perform"]',
            level=80,
        )
        db.session.add_all([gm_role, gm_assistant_role])
        db.session.flush()

        gm = User(
            username="qc_manager_nav_gm",
            password_hash=generate_password_hash("Pass123!"),
            real_name="GM",
            role_id=gm_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        gm_assistant = User(
            username="qc_manager_nav_assistant",
            password_hash=generate_password_hash("Pass123!"),
            real_name="GM Assistant",
            role_id=gm_assistant_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        db.session.add_all([gm, gm_assistant])
        db.session.commit()
        gm_id = gm.id
        gm_assistant_id = gm_assistant.id

    login(gm_id)
    gm_dashboard = client.get("/qc/production/", follow_redirects=False)
    assert gm_dashboard.status_code == 200
    assert b"/qc/quality-control/" in gm_dashboard.data
    assert b"/qc/quality-inspection/" in gm_dashboard.data
    assert b"/qc/acceptance/" in gm_dashboard.data
    assert b"/qc/admin/users" in gm_dashboard.data
    assert client.get("/qc/quality-inspection/", follow_redirects=False).status_code == 200
    assert client.get("/qc/acceptance/", follow_redirects=False).status_code == 200
    assert client.get("/qc/admin/users", follow_redirects=False).status_code == 200

    login(gm_assistant_id)
    assistant_dashboard = client.get("/qc/production/", follow_redirects=False)
    assert assistant_dashboard.status_code == 200
    assert b"/qc/quality-control/" in assistant_dashboard.data
    assert b"/qc/quality-inspection/" in assistant_dashboard.data
    assert b"/qc/acceptance/" in assistant_dashboard.data
    assert b"/qc/admin/users" in assistant_dashboard.data
    assert client.get("/qc/quality-inspection/", follow_redirects=False).status_code == 200
    assert client.get("/qc/acceptance/", follow_redirects=False).status_code == 200

    admin_resp = client.get("/qc/admin/users", follow_redirects=False)
    assert admin_resp.status_code == 200


def test_logout_redirects_back_to_system_portal(client):
    """Logout should return users to the system-selection portal instead of ERP login."""
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["subsystem"] = "qc"

    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers.get("Location", "").endswith("/")


def test_inspection_pass_redirects_to_acceptance_with_empty_remarks(app, client, login):
    """Passing inspection with blank remarks should enter acceptance instead of crashing."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        controller = User.query.get(controller_id)

        order = QCWorkOrder(
            batch_no="BATCH-PASS-TO-ACCEPTANCE",
            workpiece_name="Pass To Acceptance",
            quantity=6,
            controller_id=controller_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/d.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="instruction",
                    title="Instruction",
                    content="",
                    file_path="instructions/i.png",
                    file_type="png",
                    is_required=True,
                    sort_order=1,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Point",
                    content="check",
                    file_path="inspection_points/p.png",
                    file_type="png",
                    is_required=True,
                    sort_order=2,
                ),
            ]
        )
        db.session.commit()

        QCService.complete_quality_control(order.id, inspector_id, controller)
        attachments = QCWorkOrderAttachment.query.filter_by(work_order_id=order.id).all()
        order_id = order.id
        attachment_ids = [att.id for att in attachments]

    login(inspector_id)
    payload = {}
    for attachment_id in attachment_ids:
        payload[f"result_{attachment_id}"] = "pass"
        payload[f"remark_{attachment_id}"] = ""
        payload[f"report_file_{attachment_id}"] = (io.BytesIO(b"report"), f"report_{attachment_id}.png")

    response = client.post(
        f"/qc/quality-inspection/{order_id}",
        data=payload,
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert f"/qc/acceptance/{order_id}" in response.headers.get("Location", "")

    with app.app_context():
        refreshed = QCWorkOrder.query.get(order_id)
        assert refreshed.status == "inspection_completed"


def test_inspection_fail_redirects_cleanly_and_returns_workflow(app, client, login):
    """Failing inspection should not 404 and should return the order to QC workflow."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        controller = User.query.get(controller_id)

        order = QCWorkOrder(
            batch_no="BATCH-FAIL-BACK-QC",
            workpiece_name="Fail Back QC",
            quantity=4,
            controller_id=controller_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/d.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="instruction",
                    title="Instruction",
                    content="",
                    file_path="instructions/i.png",
                    file_type="png",
                    is_required=True,
                    sort_order=1,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Point",
                    content="check",
                    file_path="inspection_points/p.png",
                    file_type="png",
                    is_required=True,
                    sort_order=2,
                ),
            ]
        )
        db.session.commit()

        QCService.complete_quality_control(order.id, inspector_id, controller)
        attachments = QCWorkOrderAttachment.query.filter_by(work_order_id=order.id).order_by(
            QCWorkOrderAttachment.id.asc()
        ).all()
        order_id = order.id

    login(inspector_id)
    payload = {}
    for idx, attachment in enumerate(attachments):
        payload[f"result_{attachment.id}"] = "fail" if idx == 0 else "pass"
        payload[f"remark_{attachment.id}"] = ""
        payload[f"report_file_{attachment.id}"] = (io.BytesIO(b"report"), f"report_{attachment.id}.png")

    response = client.post(
        f"/qc/quality-inspection/{order_id}",
        data=payload,
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/qc/quality-inspection/" in response.headers.get("Location", "")

    with app.app_context():
        refreshed = QCWorkOrder.query.get(order_id)
        assert refreshed.status == "rejected"

    login(controller_id)
    qc_detail = client.get(f"/qc/quality-control/{order_id}", follow_redirects=False)
    assert qc_detail.status_code == 200


def test_qc_inspector_sees_acceptance_module_and_list(app, client, login):
    """Inspectors should be able to see and open acceptance pages for their own orders."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

        order = QCWorkOrder(
            batch_no="BATCH-INSPECTOR-ACCEPTANCE",
            workpiece_name="Inspector Acceptance",
            quantity=2,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="inspection_completed",
            inspection_completed_at=db.func.now(),
        )
        db.session.add(order)
        db.session.add(
            QCUserBinding(
                user_id=inspector_id,
                role_id=Role.query.filter_by(code="qc_inspector").first().id,
                is_active=True,
            )
        )
        db.session.commit()
        order_id = order.id

    login(inspector_id)
    dashboard = client.get("/qc/production/", follow_redirects=False)
    assert dashboard.status_code == 200
    assert b"/qc/acceptance/" in dashboard.data

    acceptance_list = client.get("/qc/acceptance/", follow_redirects=False)
    assert acceptance_list.status_code == 200
    assert b"BATCH-INSPECTOR-ACCEPTANCE" in acceptance_list.data

    acceptance_detail = client.get(f"/qc/acceptance/{order_id}", follow_redirects=False)
    assert acceptance_detail.status_code == 200


def test_rejected_qc_detail_highlights_failed_items(app, client, login):
    """Rejected QC detail page should clearly mark failed items and show inspection remarks."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        controller = User.query.get(controller_id)
        inspector = User.query.get(inspector_id)

        order = QCWorkOrder(
            batch_no="BATCH-REJECT-HIGHLIGHT",
            workpiece_name="Reject Highlight",
            quantity=3,
            controller_id=controller_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.flush()

        drawing = QCWorkOrderAttachment(
            work_order_id=order.id,
            attach_type="drawing",
            title="Drawing",
            content="",
            file_path="drawings/d.png",
            file_type="png",
            is_required=True,
            sort_order=0,
        )
        point = QCWorkOrderAttachment(
            work_order_id=order.id,
            attach_type="inspection_point",
            title="Fail Point",
            content="Need fix",
            file_path="inspection_points/p.png",
            file_type="png",
            is_required=True,
            sort_order=1,
        )
        db.session.add_all(
            [
                drawing,
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="instruction",
                    title="Instruction",
                    content="",
                    file_path="instructions/i.png",
                    file_type="png",
                    is_required=True,
                    sort_order=2,
                ),
                point,
            ]
        )
        db.session.commit()

        QCService.complete_quality_control(order.id, inspector_id, controller)
        QCService.submit_inspection(
            order.id,
            [
                {"attachment_id": drawing.id, "result": "pass", "remark": "", "report_file": _report_file("drawing.png")},
                {"attachment_id": point.id, "result": "fail", "remark": "尺寸不符合要求", "report_file": _report_file("point.png")},
                {
                    "attachment_id": QCWorkOrderAttachment.query.filter_by(
                        work_order_id=order.id, attach_type="instruction"
                    ).first().id,
                    "result": "pass",
                    "remark": "",
                    "report_file": _report_file("instruction.png"),
                },
            ],
            inspector,
        )
        order_id = order.id

    login(controller_id)
    response = client.get(f"/qc/quality-control/{order_id}", follow_redirects=False)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "不合格" in text
    assert "尺寸不符合要求" in text
    assert "Fail Point" in text


def test_workpiece_library_snapshot_populates_new_work_order(app, client, login, monkeypatch):
    """Selecting a workpiece should clone its snapshot into the new work order."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        controller = User.query.get(controller_id)

        workpiece = QCWorkpiece(
            workpiece_code="WP-001",
            workpiece_name="快照工件",
            creator_id=controller.id,
        )
        db.session.add(workpiece)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkpieceAttachment(
                    workpiece_id=workpiece.id,
                    attach_type="drawing",
                    title="图纸",
                    content="",
                    file_path="drawings/workpiece_drawing.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkpieceAttachment(
                    workpiece_id=workpiece.id,
                    attach_type="inspection_point",
                    title="作业指导书1",
                    content="指导说明",
                    file_path="inspection_points/workpiece_guide.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkpieceAttachment(
                    workpiece_id=workpiece.id,
                    attach_type="remark",
                    title=None,
                    content="工件备注",
                    file_path="remarks/workpiece_remark.png",
                    file_type="png",
                    is_required=False,
                    sort_order=0,
                ),
            ]
        )
        db.session.commit()
        workpiece_id = workpiece.id

    login(controller_id)
    monkeypatch.setattr(
        QCService,
        "_copy_workpiece_file_to_order",
        lambda workpiece_id, work_order_id, relative_path, attach_type: (
            f"{QCService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others')}/copied_{relative_path.split('/')[-1]}",
            "png",
        ),
    )

    response = client.post(
        "/qc/quality-control/new",
        data={
            "submit_action": "draft",
            "batch_no": "BATCH-WP-001",
            "workpiece_id": str(workpiece_id),
            "quantity": "12",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/qc/quality-control/" in response.headers.get("Location", "")

    with app.app_context():
        order = QCWorkOrder.query.filter_by(batch_no="BATCH-WP-001").first()
        assert order is not None
        assert order.workpiece_id == workpiece_id
        assert order.workpiece_name == "快照工件"

        attachments = QCWorkOrderAttachment.query.filter_by(work_order_id=order.id).all()
        assert {attachment.attach_type for attachment in attachments} == {"drawing", "inspection_point", "remark"}
        guide = next(attachment for attachment in attachments if attachment.attach_type == "inspection_point")
        assert guide.title == "作业指导书1"
        assert guide.content == "指导说明"
        assert guide.file_path == "inspection_points/copied_workpiece_guide.png"


def test_qc_upload_route_serves_only_authorized_workpiece_files(app, client, login):
    """Uploaded QC files require login and access to their parent resource."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        workpiece = QCWorkpiece(
            workpiece_code="WP-UPLOAD-001",
            workpiece_name="受保护附件工件",
            creator_id=controller_id,
        )
        db.session.add(workpiece)
        db.session.commit()
        workpiece_id = workpiece.id

    relative_path = Path(f"qc/workpieces/{workpiece_id}/drawings/route-test.png")
    target_path = Path(app.static_folder) / "uploads" / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(b"route-test-bytes")

    try:
        anonymous_response = client.get(f"/uploads/{relative_path.as_posix()}")
        assert anonymous_response.status_code == 403

        login(inspector_id)
        unauthorized_response = client.get(f"/uploads/{relative_path.as_posix()}")
        assert unauthorized_response.status_code == 403

        login(controller_id)
        response = client.get(f"/uploads/{relative_path.as_posix()}")
        assert response.status_code == 200
        assert response.data == b"route-test-bytes"
    finally:
        try:
            response.close()
        except UnboundLocalError:
            pass
        if target_path.exists():
            try:
                target_path.unlink()
            except PermissionError:
                pass


def test_new_work_order_persists_section_upload_files(app, client, login, monkeypatch):
    """Creating a work order should persist drawing/guide/remark supplemental files."""
    with app.app_context():
        controller_id, _, _ = _seed_qc_users()
        controller = User.query.get(controller_id)

        workpiece = QCWorkpiece(
            workpiece_code="WP-EXTRA-001",
            workpiece_name="With Extras",
            creator_id=controller.id,
        )
        db.session.add(workpiece)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkpieceAttachment(
                    workpiece_id=workpiece.id,
                    attach_type="drawing",
                    title="图纸",
                    content="",
                    file_path="drawings/workpiece_drawing.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkpieceAttachment(
                    workpiece_id=workpiece.id,
                    attach_type="inspection_point",
                    title="作业指导书1",
                    content="Guide text",
                    file_path="inspection_points/workpiece_guide.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
            ]
        )
        db.session.commit()
        workpiece_id = workpiece.id

    login(controller_id)
    monkeypatch.setattr(
        QCService,
        "_copy_workpiece_file_to_order",
        lambda workpiece_id, work_order_id, relative_path, attach_type: (
            f"{QCService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others')}/copied_{relative_path.split('/')[-1]}",
            "png",
        ),
    )
    monkeypatch.setattr(
        QCService,
        "_save_uploaded_file",
        lambda file, work_order_id, subfolder: f"{subfolder}/saved_{file.filename}",
    )

    response = client.post(
        "/qc/quality-control/new",
        data={
            "submit_action": "draft",
            "batch_no": "BATCH-EXTRA-001",
            "workpiece_id": str(workpiece_id),
            "quantity": "5",
            "drawing_note_file": (io.BytesIO(b"drawing-note"), "drawing-note.png"),
            "guide_certificate_file": (io.BytesIO(b"guide-proof"), "guide-proof.pdf"),
            "remark_note_file": (io.BytesIO(b"remark-note"), "remark-note.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        order = QCWorkOrder.query.filter_by(batch_no="BATCH-EXTRA-001").first()
        assert order is not None
        assert order.drawing_note_file_path == "drawing_notes/saved_drawing-note.png"
        assert order.guide_certificate_file_path == "guide_certificates/saved_guide-proof.pdf"
        assert order.remark_note_file_path == "remark_notes/saved_remark-note.jpg"
        assert order.drawing_note_original_name == "drawing-note.png"
        assert order.guide_certificate_original_name == "guide-proof.pdf"
        assert order.remark_note_original_name == "remark-note.jpg"


def test_inspection_page_orders_guides_before_remarks(app, client, login):
    """Inspection page should always render all guides before the remark block."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

        order = QCWorkOrder(
            batch_no="BATCH-ORDERING-001",
            workpiece_name="Ordering",
            quantity=3,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="qc_completed",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/drawing.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Guide Alpha",
                    content="First guide",
                    file_path="inspection_points/guide-a.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="remark",
                    title=None,
                    content="Remark anchor",
                    file_path="remarks/remark.png",
                    file_type="png",
                    is_required=False,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Guide Beta",
                    content="Second guide",
                    file_path="inspection_points/guide-b.png",
                    file_type="png",
                    is_required=True,
                    sort_order=1,
                ),
            ]
        )
        db.session.commit()
        order_id = order.id

    login(inspector_id)
    response = client.get(f"/qc/quality-inspection/{order_id}", follow_redirects=False)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert text.find("Guide Alpha") < text.find("Guide Beta")
    assert text.find("Guide Beta") < text.find("Remark anchor")


def test_acceptance_page_shows_section_upload_files(app, client, login):
    """Acceptance page should show the new section-level supplemental file names."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

        order = QCWorkOrder(
            batch_no="BATCH-ACCEPT-EXTRA",
            workpiece_name="Acceptance Extras",
            quantity=4,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="inspection_completed",
            drawing_note_file_path="drawing_notes/drawing-note.png",
            drawing_note_original_name="drawing-note.png",
            guide_certificate_file_path="guide_certificates/guide-proof.pdf",
            guide_certificate_original_name="guide-proof.pdf",
            remark_note_file_path="remark_notes/remark-note.jpg",
            remark_note_original_name="remark-note.jpg",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(
            QCWorkOrderAttachment(
                work_order_id=order.id,
                attach_type="drawing",
                title="Drawing",
                content="",
                file_path="drawings/drawing.png",
                file_type="png",
                is_required=True,
                sort_order=0,
            )
        )
        db.session.commit()
        order_id = order.id

    login(controller_id)
    response = client.get(f"/qc/acceptance/{order_id}", follow_redirects=False)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "drawing-note.png" in text
    assert "guide-proof.pdf" in text
    assert "remark-note.jpg" in text


def test_quality_control_detail_shows_section_upload_files(app, client, login):
    """QC work-order detail page should show the three supplemental file entries."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

        order = QCWorkOrder(
            batch_no="BATCH-DETAIL-EXTRA",
            workpiece_name="Detail Extras",
            quantity=4,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="qc_pending",
            drawing_note_file_path="drawing_notes/drawing-note.png",
            drawing_note_original_name="drawing-note.png",
            guide_certificate_file_path="guide_certificates/guide-proof.pdf",
            guide_certificate_original_name="guide-proof.pdf",
            remark_note_file_path="remark_notes/remark-note.jpg",
            remark_note_original_name="remark-note.jpg",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/drawing.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Guide 1",
                    content="Guide content",
                    file_path="inspection_points/guide.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="remark",
                    title=None,
                    content="Remark content",
                    file_path="remarks/remark.png",
                    file_type="png",
                    is_required=False,
                    sort_order=0,
                ),
            ]
        )
        db.session.commit()
        order_id = order.id

    login(controller_id)
    response = client.get(f"/qc/quality-control/{order_id}", follow_redirects=False)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "drawing-note.png" in text
    assert "guide-proof.pdf" in text
    assert "remark-note.jpg" in text


def test_inspection_page_shows_upload_section_titles(app, client, login):
    """Inspection page should show the upload-section titles for drawing, guide, and remark."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()

        order = QCWorkOrder(
            batch_no="BATCH-UPLOAD-TITLES",
            workpiece_name="Upload Titles",
            quantity=2,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="qc_completed",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/drawing.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Guide 1",
                    content="Guide content",
                    file_path="inspection_points/guide.png",
                    file_type="png",
                    is_required=True,
                    sort_order=1,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="remark",
                    title=None,
                    content="Remark content",
                    file_path="remarks/remark.png",
                    file_type="png",
                    is_required=False,
                    sort_order=2,
                ),
            ]
        )
        db.session.commit()
        order_id = order.id

    login(inspector_id)
    response = client.get(f"/qc/quality-inspection/{order_id}", follow_redirects=False)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "图纸确认函（可选）" in text
    assert "合格报告" in text
    assert "附加文件" in text


def test_inspection_draft_saves_report_and_final_submit_requires_non_remark_reports(app, monkeypatch):
    """Inspection draft should persist reports, and final submit should require them for non-remark items."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        controller = User.query.get(controller_id)
        inspector = User.query.get(inspector_id)

        order = QCWorkOrder(
            batch_no="BATCH-DRAFT-REPORT",
            workpiece_name="Draft Report",
            quantity=2,
            controller_id=controller_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/d.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Guide 1",
                    content="Guide content",
                    file_path="inspection_points/g.png",
                    file_type="png",
                    is_required=True,
                    sort_order=1,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="remark",
                    title=None,
                    content="可选备注",
                    file_path="",
                    file_type="",
                    is_required=False,
                    sort_order=2,
                ),
            ]
        )
        db.session.commit()

        QCService.complete_quality_control(order.id, inspector_id, controller)
        drawing = QCWorkOrderAttachment.query.filter_by(work_order_id=order.id, attach_type="drawing").first()
        guide = QCWorkOrderAttachment.query.filter_by(
            work_order_id=order.id, attach_type="inspection_point"
        ).first()
        remark = QCWorkOrderAttachment.query.filter_by(work_order_id=order.id, attach_type="remark").first()

        monkeypatch.setattr(
            QCService,
            "_save_uploaded_file",
            lambda file, work_order_id, subfolder: f"{subfolder}/saved_{file.filename}",
        )

        draft_order = QCService.submit_inspection(
            order.id,
            [
                {
                    "attachment_id": drawing.id,
                    "result": "pass",
                    "remark": "先存草稿",
                    "report_file": _report_file("draft_report.png"),
                }
            ],
            inspector,
            final_submit=False,
        )
        assert draft_order.status == "inspection_pending"

        record = QCInspectionRecord.query.filter_by(work_order_id=order.id, attachment_id=drawing.id).first()
        assert record is not None
        assert record.report_file_path == "reports/saved_draft_report.png"

        with pytest.raises(ValueError, match="必须上传合格报告"):
            QCService.submit_inspection(
                order.id,
                [
                    {"attachment_id": drawing.id, "result": "pass", "remark": "", "report_file": None},
                    {"attachment_id": guide.id, "result": "pass", "remark": "", "report_file": None},
                    {"attachment_id": remark.id, "result": "pass", "remark": ""},
                ],
                inspector,
            )


def test_final_inspection_allows_drawing_without_confirmation_file(app, monkeypatch):
    """Drawing confirmation file should be optional on final inspection submit."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        controller = User.query.get(controller_id)
        inspector = User.query.get(inspector_id)

        order = QCWorkOrder(
            batch_no="BATCH-DRAWING-OPTIONAL",
            workpiece_name="Drawing Optional",
            quantity=2,
            controller_id=controller_id,
            status="qc_pending",
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="drawing",
                    title="Drawing",
                    content="",
                    file_path="drawings/d.png",
                    file_type="png",
                    is_required=True,
                    sort_order=0,
                ),
                QCWorkOrderAttachment(
                    work_order_id=order.id,
                    attach_type="inspection_point",
                    title="Guide 1",
                    content="Guide content",
                    file_path="inspection_points/g.png",
                    file_type="png",
                    is_required=True,
                    sort_order=1,
                ),
            ]
        )
        db.session.commit()

        QCService.complete_quality_control(order.id, inspector_id, controller)
        drawing = QCWorkOrderAttachment.query.filter_by(work_order_id=order.id, attach_type="drawing").first()
        guide = QCWorkOrderAttachment.query.filter_by(work_order_id=order.id, attach_type="inspection_point").first()

        monkeypatch.setattr(
            QCService,
            "_save_uploaded_file",
            lambda file, work_order_id, subfolder: f"{subfolder}/saved_{file.filename}",
        )

        submitted = QCService.submit_inspection(
            order.id,
            [
                {"attachment_id": drawing.id, "result": "pass", "remark": "", "report_file": None},
                {
                    "attachment_id": guide.id,
                    "result": "pass",
                    "remark": "",
                    "report_file": _report_file("guide-report.png"),
                },
            ],
            inspector,
        )

        assert submitted.status == "inspection_completed"
        drawing_record = QCInspectionRecord.query.filter_by(
            work_order_id=order.id,
            attachment_id=drawing.id,
        ).first()
        guide_record = QCInspectionRecord.query.filter_by(
            work_order_id=order.id,
            attachment_id=guide.id,
        ).first()
        assert drawing_record is not None
        assert drawing_record.report_file_path in (None, "")
        assert guide_record is not None
        assert guide_record.report_file_path == "reports/saved_guide-report.png"

def test_erp_nav_shows_qc_switch_only_for_dual_system_roles(app, client, login):
    """ERP navbar should expose QC switch only to admin, GM and GM assistant."""
    with app.app_context():
        dept = Department(name="ERP Nav")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(name="Super Admin", code="superadmin", permissions="[]", level=999)
        gm_role = Role(name="General Manager", code="general_manager", permissions='["contract_view"]', level=90)
        assistant_role = Role(name="GM Assistant", code="gm_assistant", permissions='["contract_view"]', level=80)
        sales_role = Role(name="Sales", code="sales_nav", permissions='["contract_view"]', level=20)
        db.session.add_all([superadmin_role, gm_role, assistant_role, sales_role])
        db.session.flush()

        admin = User(
            username="erp_nav_admin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Admin",
            role_id=superadmin_role.id,
            department_id=dept.id,
            email="erp_nav_admin@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        gm = User(
            username="erp_nav_gm",
            password_hash=generate_password_hash("Pass123!"),
            real_name="GM",
            role_id=gm_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        assistant = User(
            username="erp_nav_assistant",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Assistant",
            role_id=assistant_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        sales = User(
            username="erp_nav_sales",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Sales",
            role_id=sales_role.id,
            department_id=dept.id,
            is_active=True,
            require_password_change=False,
        )
        db.session.add_all([admin, gm, assistant, sales])
        db.session.commit()
        ids = {
            "admin": admin.id,
            "gm": gm.id,
            "assistant": assistant.id,
            "sales": sales.id,
        }

    for label in ["admin", "gm", "assistant"]:
        login(ids[label])
        response = client.get("/erp/", follow_redirects=False)
        assert response.status_code == 200
        text = response.get_data(as_text=True)
        assert "AI CATS" in text
        assert "/auth/switch/qc" in text

    login(ids["sales"])
    response = client.get("/erp/", follow_redirects=False)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "AI CATS" not in text


def test_switch_routes_change_subsystem_context(app, client, login):
    """Explicit system-switch routes should land in the correct subsystem."""
    with app.app_context():
        dept = Department(name="Switch Test")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(name="Switch SA", code="superadmin", permissions="[]", level=999)
        db.session.add(superadmin_role)
        db.session.flush()

        admin = User(
            username="switch_route_admin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Switch Admin",
            role_id=superadmin_role.id,
            department_id=dept.id,
            email="switch_admin@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    login(admin_id)
    with client.session_transaction() as sess:
        sess["subsystem"] = "qc"

    erp_resp = client.get("/auth/switch/erp", follow_redirects=False)
    assert erp_resp.status_code == 302
    assert "/erp/" in erp_resp.headers.get("Location", "")
    with client.session_transaction() as sess:
        assert sess.get("subsystem") == "erp"

    qc_resp = client.get("/auth/switch/qc", follow_redirects=False)
    assert qc_resp.status_code == 302
    assert "/qc/" in qc_resp.headers.get("Location", "")
    with client.session_transaction() as sess:
        assert sess.get("subsystem") == "qc"


def test_qc_module_selector_and_top_level_shells(client, login, base_data):
    """AI CATS should open a module selector before entering top-level modules."""
    login(base_data["superadmin_id"])

    selector = client.get("/qc/", follow_redirects=False)
    assert selector.status_code == 200
    selector_text = selector.get_data(as_text=True)
    assert "选择 AI CATS 模块" in selector_text
    assert "配件生产" in selector_text
    assert "/qc/production/" in selector_text
    assert "/qc/assembly/" in selector_text
    assert "/qc/research/" in selector_text
    assert "coming soon" in selector_text
    assert "即将开放" in selector_text

    production = client.get("/qc/production/", follow_redirects=False)
    assert production.status_code == 200
    assert "AI CATS 仪表盘" in production.get_data(as_text=True)

    assembly = client.get("/qc/assembly/", follow_redirects=False)
    assert assembly.status_code == 200
    assert "装配/出厂" in assembly.get_data(as_text=True)

    research = client.get("/qc/research/", follow_redirects=False)
    assert research.status_code == 200
    assert "研究/实验" in research.get_data(as_text=True)


def test_research_module_phase1_routes_load(client, login, base_data):
    """Research module Phase 1 dashboard and list shells should render for superadmin."""
    login(base_data["superadmin_id"])

    dashboard = client.get("/qc/research/", follow_redirects=False)
    assert dashboard.status_code == 200
    dashboard_text = dashboard.get_data(as_text=True)
    assert "AI CATS Research & Experiment" in dashboard_text
    assert "研究项目库" in dashboard_text
    assert "/qc/research/projects/" in dashboard_text
    assert "/qc/research/batches/" in dashboard_text
    assert "/qc/research/reviews/" in dashboard_text
    assert "/qc/research/acceptance/" in dashboard_text

    projects = client.get("/qc/research/projects/", follow_redirects=False)
    assert projects.status_code == 200
    assert "研究项目库" in projects.get_data(as_text=True)

    batches = client.get("/qc/research/batches/", follow_redirects=False)
    assert batches.status_code == 200
    assert "研究发起" in batches.get_data(as_text=True)

    reviews = client.get("/qc/research/reviews/", follow_redirects=False)
    assert reviews.status_code == 200
    assert "指导审批" in reviews.get_data(as_text=True)

    acceptance = client.get("/qc/research/acceptance/", follow_redirects=False)
    assert acceptance.status_code == 200
    assert "共同验收" in acceptance.get_data(as_text=True)


def test_research_batch_detail_shows_selected_project_display(app, client, login):
    """Research batch detail should render the linked project code and name."""
    with app.app_context():
        seeded = _seed_research_batch(status="draft", with_attachment=False)

    login(seeded["controller_id"])
    response = client.get(f"/qc/research/batches/{seeded['batch_id']}", follow_redirects=False)

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "研究项目" in text
    assert "PRJ-001 / 色谱柱连接件开发" in text


def test_research_review_detail_uses_stable_layout_and_project_display(app, client, login):
    """Research review page should render the optimized review layout and project display."""
    with app.app_context():
        seeded = _seed_research_batch(status="research_submitted", with_attachment=True)

    login(seeded["inspector_id"])
    response = client.get(f"/qc/research/reviews/{seeded['batch_id']}", follow_redirects=False)

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "研究项目" in text
    assert "PRJ-001 / 色谱柱连接件开发" in text
    assert text.index("指导建议") < text.index("指导结果")
    assert "review-editor-stack" in text
    assert "review-secondary-grid" in text
    assert "review-status-panel" in text
    assert "review-feedback-panel" in text


def test_research_acceptance_page_allows_actual_participants_to_sign(app, client, login):
    """Research acceptance should still allow the assigned participants to sign their own roles."""
    with app.app_context():
        seeded = _seed_research_batch(status="review_completed", with_attachment=True)

    login(seeded["controller_id"])
    researcher_page = client.get(f"/qc/research/acceptance/{seeded['batch_id']}", follow_redirects=False)
    researcher_text = researcher_page.get_data(as_text=True)
    assert researcher_page.status_code == 200
    assert researcher_text.count("点击确认") == 1
    assert 'name="signer_role" value="researcher"' in researcher_text

    first_sign = client.post(
        f"/qc/research/acceptance/{seeded['batch_id']}/sign",
        data={"signer_role": "researcher"},
        follow_redirects=True,
    )
    first_sign_text = first_sign.get_data(as_text=True)
    assert first_sign.status_code == 200
    assert "共同验收确认已提交，等待另一方确认" in first_sign_text

    with app.app_context():
        batch = ResearchBatch.query.get(seeded["batch_id"])
        signatures = ResearchAcceptanceSignature.query.filter_by(batch_id=seeded["batch_id"]).all()
        assert batch.status == "review_completed"
        assert len(signatures) == 1
        assert signatures[0].signer_role == "researcher"
        assert signatures[0].signer_id == seeded["controller_id"]

    login(seeded["inspector_id"])
    reviewer_page = client.get(f"/qc/research/acceptance/{seeded['batch_id']}", follow_redirects=False)
    reviewer_text = reviewer_page.get_data(as_text=True)
    assert reviewer_page.status_code == 200
    assert reviewer_text.count("点击确认") == 1
    assert 'name="signer_role" value="reviewer"' in reviewer_text

    second_sign = client.post(
        f"/qc/research/acceptance/{seeded['batch_id']}/sign",
        data={"signer_role": "reviewer"},
        follow_redirects=True,
    )
    second_sign_text = second_sign.get_data(as_text=True)
    assert second_sign.status_code == 200
    assert "双方已确认，阶段研发完成" in second_sign_text

    with app.app_context():
        batch = ResearchBatch.query.get(seeded["batch_id"])
        signatures = ResearchAcceptanceSignature.query.filter_by(batch_id=seeded["batch_id"]).all()
        assert batch.status == "accepted"
        assert len(signatures) == 2
        assert {signature.signer_role for signature in signatures} == {"researcher", "reviewer"}
        assert {signature.signer_id for signature in signatures} == {
            seeded["controller_id"],
            seeded["inspector_id"],
        }


def test_research_acceptance_page_allows_manager_to_sign_all_roles(app, client, login, base_data):
    """Research acceptance should allow manager roles to confirm both sides when needed."""
    with app.app_context():
        seeded = _seed_research_batch(status="review_completed", with_attachment=True)
        manager_role = Role(
            name="总经理",
            code="general_manager",
            permissions=json.dumps(["qc_acceptance_perform", "qc_acceptance_rollback"]),
            level=80,
        )
        db.session.add(manager_role)
        db.session.flush()

        manager_user = User(
            username="research_manager",
            password_hash="x",
            real_name="Research Manager",
            role_id=manager_role.id,
            department_id=base_data["department_id"],
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        db.session.add(manager_user)
        db.session.commit()
        manager_id = manager_user.id

    login(manager_id)
    response = client.get(f"/qc/research/acceptance/{seeded['batch_id']}", follow_redirects=False)

    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "研究项目" in text
    assert "PRJ-001 / 色谱柱连接件开发" in text
    assert text.count("点击确认") == 2
    assert 'name="signer_role" value="researcher"' in text
    assert 'name="signer_role" value="reviewer"' in text

    first_sign = client.post(
        f"/qc/research/acceptance/{seeded['batch_id']}/sign",
        data={"signer_role": "researcher"},
        follow_redirects=True,
    )
    first_sign_text = first_sign.get_data(as_text=True)
    assert first_sign.status_code == 200
    assert "共同验收确认已提交，等待另一方确认" in first_sign_text

    with app.app_context():
        batch = ResearchBatch.query.get(seeded["batch_id"])
        signatures = ResearchAcceptanceSignature.query.filter_by(batch_id=seeded["batch_id"]).all()
        assert batch.status == "review_completed"
        assert len(signatures) == 1
        assert signatures[0].signer_role == "researcher"
        assert signatures[0].signer_id == manager_id

    second_sign = client.post(
        f"/qc/research/acceptance/{seeded['batch_id']}/sign",
        data={"signer_role": "reviewer"},
        follow_redirects=True,
    )
    second_sign_text = second_sign.get_data(as_text=True)
    assert second_sign.status_code == 200
    assert "双方已确认，阶段研发完成" in second_sign_text

    with app.app_context():
        batch = ResearchBatch.query.get(seeded["batch_id"])
        signatures = ResearchAcceptanceSignature.query.filter_by(batch_id=seeded["batch_id"]).all()
        assert batch.status == "accepted"
        assert len(signatures) == 2
        assert {signature.signer_role for signature in signatures} == {"researcher", "reviewer"}
        assert {signature.signer_id for signature in signatures} == {manager_id}


def test_ai_cats_module_nav_is_isolated_between_production_and_research(client, login, base_data):
    """Production and research pages should render only their own module navigation items."""
    login(base_data["superadmin_id"])

    production = client.get("/qc/production/", follow_redirects=False)
    assert production.status_code == 200
    production_text = production.get_data(as_text=True)
    assert "当前模块" in production_text
    assert "工件库" in production_text
    assert "质量控制" in production_text
    assert "质量检测" in production_text
    assert "验收模块" in production_text
    assert "ERP 系统" in production_text
    assert "研究项目库" not in production_text
    assert "研究发起" not in production_text
    assert "指导审批" not in production_text
    assert "共同验收" not in production_text

    research = client.get("/qc/research/", follow_redirects=False)
    assert research.status_code == 200
    research_text = research.get_data(as_text=True)
    assert "当前模块" in research_text
    assert "研究项目库" in research_text
    assert "研究发起" in research_text
    assert "指导审批" in research_text
    assert "共同验收" in research_text
    assert "ERP 系统" in research_text
    assert "工件库" not in research_text
    assert "质量控制" not in research_text
    assert "质量检测" not in research_text
    assert "验收模块" not in research_text


def test_portal_cards_switch_systems_for_logged_in_users(app, client):
    """Portal system cards should use explicit switch routes once the user is logged in."""
    with app.app_context():
        dept = Department(name="Portal Switch")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(name="Portal SA", code="superadmin", permissions="[]", level=999)
        db.session.add(superadmin_role)
        db.session.flush()

        user = User(
            username="portal_switch_admin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Portal Switch Admin",
            role_id=superadmin_role.id,
            department_id=dept.id,
            email="portal_switch_admin@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["subsystem"] = "qc"

    portal = client.get("/", follow_redirects=False)
    assert portal.status_code == 200
    text = portal.get_data(as_text=True)
    assert "/auth/switch/erp" in text
    assert "/auth/switch/qc" in text

    erp_resp = client.get("/auth/switch/erp", follow_redirects=False)
    assert erp_resp.status_code == 302
    assert "/erp/" in erp_resp.headers.get("Location", "")



def test_erp_pending_page_hides_qc_only_registrations(app, client, login):
    """ERP pending page should only show ERP registrations, never QC-only applicants."""
    with app.app_context():
        dept = Department(name="Pending ERP")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(name="ERP Pending SA", code="superadmin", permissions="[]", level=999)
        sales_role = Role(name="ERP Pending Sales", code="sales_manager", permissions='["contract_view"]', level=20)
        qc_role = Role(name="ERP Pending QC", code="qc_controller", permissions='["qc_dashboard"]', level=55)
        db.session.add_all([superadmin_role, sales_role, qc_role])
        db.session.flush()

        admin = User(
            username="pending_admin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Pending Admin",
            role_id=superadmin_role.id,
            department_id=dept.id,
            email="pending_admin@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        erp_pending = User(
            username="erp_pending_visible",
            password_hash=generate_password_hash("Pass123!"),
            real_name="ERP Pending",
            role_id=sales_role.id,
            department_id=dept.id,
            email="erp_pending_visible@example.com",
            is_active=False,
            require_password_change=False,
        )
        qc_pending = User(
            username="qc_pending_hidden",
            password_hash=generate_password_hash("Pass123!"),
            real_name="QC Pending",
            role_id=qc_role.id,
            email="qc_pending_hidden@example.com",
            is_active=False,
            require_password_change=False,
        )
        db.session.add_all([admin, erp_pending, qc_pending])
        db.session.flush()
        db.session.add(
            QCUserBinding(
                user_id=qc_pending.id,
                role_id=qc_role.id,
                is_active=False,
            )
        )
        db.session.commit()
        admin_id = admin.id

    login(admin_id)
    response = client.get('/user/pending', follow_redirects=False)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert 'ERP 新用户注册申请' in text
    assert 'QC 角色申请' not in text
    assert 'erp_pending_visible' in text
    assert 'qc_pending_hidden' not in text



def test_erp_role_management_hides_qc_roles(app, client, login):
    """ERP role management should not render QC-only roles."""
    with app.app_context():
        dept = Department(name="Role Scope")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(name="Role Scope SA", code="superadmin", permissions="[]", level=999)
        sales_role = Role(name="Role Scope Sales", code="sales_manager", permissions='["contract_view"]', level=20)
        qc_role = Role(name="Role Scope QC Inspector", code="qc_inspector", permissions='["qc_dashboard"]', level=45)
        db.session.add_all([superadmin_role, sales_role, qc_role])
        db.session.flush()

        admin = User(
            username="role_scope_admin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Role Scope Admin",
            role_id=superadmin_role.id,
            department_id=dept.id,
            email="role_scope_admin@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
        qc_role_id = qc_role.id

    login(admin_id)
    response = client.get('/role/', follow_redirects=False)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert 'Role Scope Sales' in text
    assert 'Role Scope QC Inspector' not in text

    blocked = client.get(f'/role/{qc_role_id}/edit', follow_redirects=False)
    assert blocked.status_code == 302
    assert '/role/' in blocked.headers.get('Location', '')



def test_erp_register_page_excludes_qc_roles_and_blocks_manual_submission(app, client):
    """ERP registration should hide QC roles and reject forged QC role submissions."""
    with app.app_context():
        dept = Department(name="Register Scope")
        db.session.add(dept)
        db.session.flush()

        sales_role = Role(name="Register Scope Sales", code="sales_manager", permissions='["contract_view"]', level=20)
        qc_role = Role(name="Register Scope QC Controller", code="qc_controller", permissions='["qc_dashboard"]', level=55)
        db.session.add_all([sales_role, qc_role])
        db.session.commit()
        dept_id = dept.id
        qc_role_id = qc_role.id

    page = client.get('/auth/register', follow_redirects=False)
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert 'Register Scope Sales' in text
    assert 'Register Scope QC Controller' not in text

    response = client.post(
        '/auth/register',
        data={
            'username': 'erp_forged_qc_role',
            'real_name': 'Forged QC Role',
            'role_id': str(qc_role_id),
            'department_id': str(dept_id),
            'email': 'erp_forged_qc_role@example.com',
            'phone': '13800001111',
        },
        follow_redirects=False,
    )
    assert response.status_code == 200

    with app.app_context():
        assert User.query.filter_by(username='erp_forged_qc_role').first() is None



def test_erp_cannot_manage_qc_only_users_by_direct_url(app, client, login):
    """ERP management routes should reject direct access to QC-only accounts."""
    with app.app_context():
        dept = Department(name="Manage Scope")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(name="Manage Scope SA", code="superadmin", permissions="[]", level=999)
        qc_role = Role(name="Manage Scope QC", code="qc_inspector", permissions='["qc_dashboard"]', level=45)
        db.session.add_all([superadmin_role, qc_role])
        db.session.flush()

        admin = User(
            username="manage_scope_admin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Manage Scope Admin",
            role_id=superadmin_role.id,
            department_id=dept.id,
            email="manage_scope_admin@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        qc_user = User(
            username="manage_scope_qc_only",
            password_hash=generate_password_hash("Pass123!"),
            real_name="Manage Scope QC",
            role_id=qc_role.id,
            email="manage_scope_qc@example.com",
            is_active=True,
            require_password_change=False,
        )
        db.session.add_all([admin, qc_user])
        db.session.flush()
        db.session.add(
            QCUserBinding(
                user_id=qc_user.id,
                role_id=qc_role.id,
                is_active=True,
            )
        )
        db.session.commit()
        admin_id = admin.id
        qc_user_id = qc_user.id

    login(admin_id)
    detail = client.get(f'/user/{qc_user_id}', follow_redirects=False)
    assert detail.status_code == 302
    assert '/user/' in detail.headers.get('Location', '')

    delete_resp = client.post(f'/user/{qc_user_id}/delete', follow_redirects=False)
    assert delete_resp.status_code == 302
    assert '/user/' in delete_resp.headers.get('Location', '')

    with app.app_context():
        assert User.query.get(qc_user_id) is not None



def test_qc_admin_can_approve_qc_only_user_after_erp_scope_split(app, client, login):
    """QC admin routes should still manage QC-only accounts after ERP scoping is tightened."""
    with app.app_context():
        dept = Department(name="QC Admin Scope")
        db.session.add(dept)
        db.session.flush()

        superadmin_role = Role(name="QC Admin Scope SA", code="superadmin", permissions="[]", level=999)
        qc_role = Role(name="QC Admin Scope Controller", code="qc_controller", permissions='["qc_dashboard"]', level=55)
        db.session.add_all([superadmin_role, qc_role])
        db.session.flush()

        admin = User(
            username="qc_admin_scope_admin",
            password_hash=generate_password_hash("Pass123!"),
            real_name="QC Admin Scope Admin",
            role_id=superadmin_role.id,
            department_id=dept.id,
            email="qc_admin_scope_admin@example.com",
            is_active=True,
            is_superadmin=True,
            require_password_change=False,
        )
        pending_qc_user = User(
            username="qc_admin_scope_pending",
            password_hash=generate_password_hash("Pass123!"),
            real_name="QC Pending User",
            role_id=qc_role.id,
            email="qc_admin_scope_pending@example.com",
            is_active=False,
            require_password_change=True,
        )
        db.session.add_all([admin, pending_qc_user])
        db.session.flush()
        binding = QCUserBinding(
            user_id=pending_qc_user.id,
            role_id=qc_role.id,
            is_active=False,
        )
        db.session.add(binding)
        db.session.commit()
        admin_id = admin.id
        pending_user_id = pending_qc_user.id

    login(admin_id)
    response = client.post(f'/qc/admin/pending/user/{pending_user_id}/approve', follow_redirects=False)
    assert response.status_code == 302
    assert '/qc/admin/pending' in response.headers.get('Location', '')

    with app.app_context():
        refreshed_user = User.query.get(pending_user_id)
        refreshed_binding = QCUserBinding.query.filter_by(user_id=pending_user_id).first()
        assert refreshed_user.is_active is True
        assert refreshed_binding is not None
        assert refreshed_binding.is_active is True



def test_qc_only_user_can_update_profile_after_erp_filtering(app, client, login):
    """QC-only users should still be able to update their own profile information."""
    with app.app_context():
        qc_role = Role(name="QC Profile Inspector", code="qc_inspector", permissions='["qc_dashboard"]', level=45)
        db.session.add(qc_role)
        db.session.flush()

        qc_user = User(
            username="qc_profile_user",
            password_hash=generate_password_hash("Pass123!"),
            real_name="QC Profile",
            role_id=qc_role.id,
            email="qc_profile_user@example.com",
            phone="13800002222",
            is_active=True,
            require_password_change=False,
        )
        db.session.add(qc_user)
        db.session.commit()
        qc_user_id = qc_user.id

    login(qc_user_id)
    response = client.post(
        '/user/profile',
        data={
            'real_name': 'QC Profile Updated',
            'email': 'qc_profile_updated@example.com',
            'phone': '13800003333',
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert '/user/profile' in response.headers.get('Location', '')

    with app.app_context():
        refreshed_user = User.query.get(qc_user_id)
        assert refreshed_user.real_name == 'QC Profile Updated'
        assert refreshed_user.email == 'qc_profile_updated@example.com'
        assert refreshed_user.phone == '13800003333'


def test_quality_control_supplier_picker_excludes_manager_roles(app, client, login, base_data):
    """The production work-order supplier picker should only list supplier/inspector users."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        manager_role = Role(
            name="总经理",
            code="general_manager",
            permissions=json.dumps(["qc_acceptance_perform", "qc_acceptance_rollback"]),
            level=80,
        )
        db.session.add(manager_role)
        db.session.flush()
        manager = User(
            username="supplier_picker_manager",
            password_hash="x",
            real_name="不应出现在供应商下拉",
            role_id=manager_role.id,
            department_id=base_data["department_id"],
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        db.session.add(manager)
        db.session.commit()

    login(controller_id)
    response = client.get("/qc/quality-control/new", follow_redirects=False)
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "QC Inspector" in text
    assert "不应出现在供应商下拉" not in text
    assert "supplier_picker_manager" not in text


def test_quality_control_manager_acceptance_requires_one_role_per_click(app, client, login, base_data):
    """Managers can sign both production acceptance roles, but not in one click."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        manager_role = Role(
            name="总经理",
            code="general_manager",
            permissions=json.dumps(["qc_acceptance_perform", "qc_acceptance_rollback"]),
            level=80,
        )
        db.session.add(manager_role)
        db.session.flush()
        manager = User(
            username="qc_acceptance_manager",
            password_hash="x",
            real_name="QC Acceptance Manager",
            role_id=manager_role.id,
            department_id=base_data["department_id"],
            is_active=True,
            is_superadmin=False,
            require_password_change=False,
        )
        order = QCWorkOrder(
            batch_no="QC-MGR-001",
            workpiece_name="Manager Sign Workpiece",
            quantity=1,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="inspection_completed",
        )
        db.session.add_all([manager, order])
        db.session.commit()
        manager_id = manager.id
        order_id = order.id

    login(manager_id)
    page = client.get(f"/qc/acceptance/{order_id}", follow_redirects=False)
    text = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "发起新的验收批次" in text
    assert text.count("点击确认") == 0

    start_batch = client.post(f"/qc/acceptance/{order_id}/batch/new", follow_redirects=True)
    start_text = start_batch.get_data(as_text=True)
    assert start_batch.status_code == 200
    assert "已发起新的验收批次" in start_text
    assert start_text.count('name="signer_role" value="qc_controller"') == 1
    assert start_text.count('name="signer_role" value="qc_inspector"') == 1
    assert "质控人：未确认 / 供应商：未确认" in start_text

    first_sign = client.post(
        f"/qc/acceptance/{order_id}/sign",
        data={
            "signer_role": "qc_controller",
            "production_quantity": "1",
            "accepted_quantity": "1",
        },
        follow_redirects=True,
    )
    first_text = first_sign.get_data(as_text=True)
    assert first_sign.status_code == 200
    assert "验收确认已提交，等待另一方确认" in first_text

    with app.app_context():
        order = QCWorkOrder.query.get(order_id)
        signatures = QCAcceptanceSignature.query.filter_by(work_order_id=order_id).all()
        assert order.status == "inspection_completed"
        assert len(signatures) == 1
        assert signatures[0].signer_role == "qc_controller"

    second_sign = client.post(
        f"/qc/acceptance/{order_id}/sign",
        data={"signer_role": "qc_inspector"},
        follow_redirects=True,
    )
    second_text = second_sign.get_data(as_text=True)
    assert second_sign.status_code == 200
    assert "双方已确认，质检已完成" in second_text

    with app.app_context():
        order = QCWorkOrder.query.get(order_id)
        signatures = QCAcceptanceSignature.query.filter_by(work_order_id=order_id).all()
        assert order.status == "accepted"
        assert len(signatures) == 2
        assert {signature.signer_role for signature in signatures} == {"qc_controller", "qc_inspector"}
        assert {signature.signer_id for signature in signatures} == {manager_id}


def test_quality_control_partial_acceptance_batches_increment_stock(app, client, login):
    """Production acceptance can be split into multiple deliveries and stock follows qualified quantity."""
    with app.app_context():
        controller_id, inspector_id, _ = _seed_qc_users()
        workpiece = QCWorkpiece(
            workpiece_code="PARTIAL-WP",
            workpiece_name="Partial Acceptance Workpiece",
            workpiece_type="self_produced",
            stock_quantity=0,
            creator_id=controller_id,
        )
        db.session.add(workpiece)
        db.session.flush()
        order = QCWorkOrder(
            batch_no="QC-PARTIAL-001",
            workpiece_id=workpiece.id,
            workpiece_name=workpiece.workpiece_name,
            quantity=10,
            controller_id=controller_id,
            inspector_id=inspector_id,
            status="inspection_completed",
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id
        workpiece_id = workpiece.id

    login(controller_id)
    start_first_batch = client.post(f"/qc/acceptance/{order_id}/batch/new", follow_redirects=True)
    assert start_first_batch.status_code == 200

    first_controller = client.post(
        f"/qc/acceptance/{order_id}/sign",
        data={
            "signer_role": "qc_controller",
            "production_quantity": "6",
            "accepted_quantity": "4",
        },
        follow_redirects=True,
    )
    assert first_controller.status_code == 200

    login(inspector_id)
    first_supplier = client.post(
        f"/qc/acceptance/{order_id}/sign",
        data={"signer_role": "qc_inspector"},
        follow_redirects=True,
    )
    assert first_supplier.status_code == 200

    with app.app_context():
        order = QCWorkOrder.query.get(order_id)
        workpiece = QCWorkpiece.query.get(workpiece_id)
        assert order.status == "inspection_completed"
        assert order.actual_delivered_quantity == 4
        assert order.remaining_acceptance_quantity == 6
        assert workpiece.stock_quantity == 4
        assert len(order.acceptance_batches) == 1
        assert order.acceptance_batches[0].inventory_posted_at is not None
        first_history = QCWorkpieceStockHistory.query.filter_by(workpiece_id=workpiece_id).first()
        assert first_history is not None
        assert first_history.batch_no == "QC-PARTIAL-001"
        assert first_history.production_quantity == 6
        assert first_history.accepted_quantity == 4
        assert first_history.quantity_delta == 4
        assert first_history.stock_before == 0
        assert first_history.stock_after == 4
        first_order_history_details = [history.detail or "" for history in order.histories]
        assert any("发起第 1 个验收批次" in detail for detail in first_order_history_details)
        assert any("验收批次 #1" in detail for detail in first_order_history_details)

    login(controller_id)
    start_second_batch = client.post(f"/qc/acceptance/{order_id}/batch/new", follow_redirects=True)
    assert start_second_batch.status_code == 200

    second_controller = client.post(
        f"/qc/acceptance/{order_id}/sign",
        data={
            "signer_role": "qc_controller",
            "production_quantity": "6",
            "accepted_quantity": "6",
        },
        follow_redirects=True,
    )
    assert second_controller.status_code == 200

    login(inspector_id)
    second_supplier = client.post(
        f"/qc/acceptance/{order_id}/sign",
        data={"signer_role": "qc_inspector"},
        follow_redirects=True,
    )
    assert second_supplier.status_code == 200

    with app.app_context():
        order = QCWorkOrder.query.get(order_id)
        workpiece = QCWorkpiece.query.get(workpiece_id)
        signatures = QCAcceptanceSignature.query.filter_by(work_order_id=order_id).all()
        assert order.status == "accepted"
        assert order.actual_delivered_quantity == 10
        assert order.remaining_acceptance_quantity == 0
        assert workpiece.stock_quantity == 10
        assert len(order.acceptance_batches) == 2
        assert len(signatures) == 4
        stock_histories = QCWorkpieceStockHistory.query.filter_by(
            workpiece_id=workpiece_id
        ).order_by(QCWorkpieceStockHistory.id.asc()).all()
        assert len(stock_histories) == 2
        assert stock_histories[1].production_quantity == 6
        assert stock_histories[1].accepted_quantity == 6
        assert stock_histories[1].quantity_delta == 6
        assert stock_histories[1].stock_before == 4
        assert stock_histories[1].stock_after == 10
        order_history_details = [history.detail or "" for history in order.histories]
        assert any("发起第 2 个验收批次" in detail for detail in order_history_details)
        assert any("验收批次 #2" in detail for detail in order_history_details)
