"""Regression tests for QC workflow and auth verification behavior."""

from __future__ import annotations

import io
import json
import pytest
from werkzeug.security import generate_password_hash

from app import db
from app.models import Department, QCUserBinding, QCWorkOrder, QCWorkOrderAttachment, Role, User
from app.services.auth_service import AuthService
from app.services.qc_service import QCService


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
                "qc_work_order_view",
                "qc_work_order_create",
                "qc_work_order_edit",
                "qc_work_order_delete",
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
                "qc_work_order_view",
                "qc_inspection_perform",
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
        assert instruction is not None
        assert instruction.file_path == "instructions/updated_new_instruction.png"

        inspection_point = QCWorkOrderAttachment.query.filter_by(
            work_order_id=order_id, attach_type="inspection_point"
        ).first()
        assert inspection_point is not None
        assert inspection_point.title == "新检测点"
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
        assert points[0].title == "检测点A"
        assert points[1].title == "检测点B"

        remarks = QCWorkOrderAttachment.query.filter_by(
            work_order_id=order.id, attach_type="remark"
        ).all()
        assert len(remarks) == 1
        assert remarks[0].content == "备注B"


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
                }
            )
        QCService.submit_inspection(order.id, results, inspector)
        record_count_before = len(order.inspection_records)
        assert record_count_before > 0

        QCService.complete_quality_control(order.id, inspector.id, controller)
        refreshed = QCWorkOrder.query.get(order.id)
        assert refreshed.status == "qc_completed"
        assert len(refreshed.inspection_records) == record_count_before


def test_qc_managers_are_read_only_for_qc_work_orders(app):
    """GM and GM assistant can view all QC work orders but cannot edit them."""
    with app.app_context():
        dept = Department(name="GM")
        db.session.add(dept)
        db.session.flush()

        general_manager_role = Role(
            name="General Manager",
            code="general_manager",
            permissions='["contract_view"]',
            level=90,
        )
        gm_assistant_role = Role(
            name="GM Assistant",
            code="gm_assistant",
            permissions='["contract_view"]',
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
        assert QCService.can_delete_work_order(general_manager, order) is True
        assert QCService.can_delete_work_order(gm_assistant, order) is True
        assert order.can_be_deleted_by(general_manager) is True
        assert order.can_be_deleted_by(gm_assistant) is True


def test_qc_delete_permissions_match_role_rules(app):
    """QC delete permissions should follow admin/GM/GM assistant/all, controller own-only, inspector none."""
    with app.app_context():
        dept = Department(name="QC Delete")
        db.session.add(dept)
        db.session.flush()

        super_role = Role(name="Super", code="superadmin", permissions="[]", level=999)
        gm_role = Role(name="GM", code="general_manager", permissions='["contract_view"]', level=90)
        assistant_role = Role(name="Assistant", code="gm_assistant", permissions='["contract_view"]', level=80)
        controller_role = Role(name="Controller", code="qc_controller", permissions='["qc_work_order_create"]', level=55)
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
            status="inspection_completed",
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
    """QC delete route should allow managers and owner controller, but block inspector."""
    with app.app_context():
        dept = Department(name="QC Delete Route")
        db.session.add(dept)
        db.session.flush()

        gm_role = Role(name="GM", code="general_manager", permissions='["contract_view"]', level=90)
        controller_role = Role(name="Controller", code="qc_controller", permissions='["qc_work_order_create"]', level=55)
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
            status="qc_completed",
        )
        blocked = QCWorkOrder(
            batch_no="BATCH-DELETE-BLOCKED",
            workpiece_name="Delete Blocked",
            quantity=2,
            controller_id=owner.id,
            inspector_id=inspector.id,
            status="qc_completed",
        )
        db.session.add_all([deletable, blocked])
        db.session.commit()
        gm_id = gm.id
        inspector_id = inspector.id
        deletable_id = deletable.id
        blocked_id = blocked.id

    login(gm_id)
    gm_response = client.post(f"/qc/quality-control/{deletable_id}/delete", follow_redirects=False)
    assert gm_response.status_code == 302
    with app.app_context():
        assert QCWorkOrder.query.get(deletable_id) is None

    login(inspector_id)
    inspector_response = client.post(f"/qc/quality-control/{blocked_id}/delete", follow_redirects=False)
    assert inspector_response.status_code == 302
    with app.app_context():
        assert QCWorkOrder.query.get(blocked_id) is not None


def test_gm_assistant_dashboard_links_to_qc_order_list_and_detail(app, client, login):
    """GM assistant should see QC order entry points from the dashboard, but stay read-only."""
    with app.app_context():
        dept = Department(name="GM Dashboard")
        db.session.add(dept)
        db.session.flush()

        gm_assistant_role = Role(
            name="GM Assistant",
            code="gm_assistant",
            permissions='["contract_view"]',
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

    dashboard = client.get("/qc/")
    assert dashboard.status_code == 200
    assert b"/qc/quality-control/" in dashboard.data
    assert f"/qc/quality-control/{order_id}".encode() in dashboard.data

    detail = client.get(f"/qc/quality-control/{order_id}")
    assert detail.status_code == 200
    assert b"/qc/quality-control/" in detail.data
    assert b"/edit" not in detail.data
    assert b"/complete" not in detail.data


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


def test_qc_only_user_hidden_from_erp_list_and_can_upgrade_to_erp(app, client, login):
    """QC-only users are hidden from ERP list and can be re-registered as ERP users."""
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
        assert error is None
        assert user is not None
        assert user.role.code == "sales_manager"
        assert user.real_name == "ERP Version"
        assert user.email == "erp_version@example.com"
        assert user.is_active is False
        assert user.require_password_change is True


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

        with pytest.raises(ValueError, match="质量检测员角色"):
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
            {"attachment_id": attachments[0].id, "result": "pass", "remark": ""},
            {"attachment_id": attachments[1].id, "result": "pass", "remark": ""},
        ]
        with pytest.raises(ValueError, match="完成所有附件"):
            QCService.submit_inspection(order.id, partial_results, inspector)

        duplicate_results = [
            {"attachment_id": attachments[0].id, "result": "pass", "remark": ""},
            {"attachment_id": attachments[1].id, "result": "pass", "remark": ""},
            {"attachment_id": attachments[1].id, "result": "fail", "remark": "dup"},
            {"attachment_id": attachments[2].id, "result": "pass", "remark": ""},
        ]
        with pytest.raises(ValueError, match="重复"):
            QCService.submit_inspection(order.id, duplicate_results, inspector)

        valid_results = [
            {"attachment_id": attachments[0].id, "result": "pass", "remark": ""},
            {"attachment_id": attachments[1].id, "result": "pass", "remark": ""},
            {"attachment_id": attachments[2].id, "result": "pass", "remark": ""},
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


def test_draft_visibility_owner_and_superadmin_only(app):
    """Draft work order should only be visible to owner and superadmin."""
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

        draft = QCService.create_work_order(
            data={"batch_no": "BATCH-DRAFT-VIS", "workpiece_name": "Draft Visible", "quantity": "1"},
            controller_id=owner.id,
            status="draft",
        )
        db.session.commit()

        assert QCService.can_view_work_order(owner, draft) is True
        assert QCService.can_view_work_order(superadmin, draft) is True
        assert QCService.can_view_work_order(gm, draft) is False


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
    """GM can access QC system management, while GM assistant remains read-only without admin entry."""
    with app.app_context():
        dept = Department(name="QC Managers")
        db.session.add(dept)
        db.session.flush()

        gm_role = Role(
            name="General Manager",
            code="general_manager",
            permissions='["contract_view"]',
            level=90,
        )
        gm_assistant_role = Role(
            name="GM Assistant",
            code="gm_assistant",
            permissions='["contract_view"]',
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
    gm_dashboard = client.get("/qc/", follow_redirects=False)
    assert gm_dashboard.status_code == 200
    assert b"/qc/quality-control/" in gm_dashboard.data
    assert b"/qc/quality-inspection/" in gm_dashboard.data
    assert b"/qc/acceptance/" in gm_dashboard.data
    assert b"/qc/admin/users" in gm_dashboard.data
    assert client.get("/qc/quality-inspection/", follow_redirects=False).status_code == 200
    assert client.get("/qc/acceptance/", follow_redirects=False).status_code == 200
    assert client.get("/qc/admin/users", follow_redirects=False).status_code == 200

    login(gm_assistant_id)
    assistant_dashboard = client.get("/qc/", follow_redirects=False)
    assert assistant_dashboard.status_code == 200
    assert b"/qc/quality-control/" in assistant_dashboard.data
    assert b"/qc/quality-inspection/" in assistant_dashboard.data
    assert b"/qc/acceptance/" in assistant_dashboard.data
    assert b"/qc/admin/users" not in assistant_dashboard.data
    assert client.get("/qc/quality-inspection/", follow_redirects=False).status_code == 200
    assert client.get("/qc/acceptance/", follow_redirects=False).status_code == 200

    admin_resp = client.get("/qc/admin/users", follow_redirects=False)
    assert admin_resp.status_code == 302
    assert "/qc/" in admin_resp.headers.get("Location", "")


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

    response = client.post(
        f"/qc/quality-inspection/{order_id}",
        data=payload,
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

    response = client.post(
        f"/qc/quality-inspection/{order_id}",
        data=payload,
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
    dashboard = client.get("/qc/", follow_redirects=False)
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
                {"attachment_id": drawing.id, "result": "pass", "remark": ""},
                {"attachment_id": point.id, "result": "fail", "remark": "尺寸不符合要求"},
                {
                    "attachment_id": QCWorkOrderAttachment.query.filter_by(
                        work_order_id=order.id, attach_type="instruction"
                    ).first().id,
                    "result": "pass",
                    "remark": "",
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
        assert "QC系统" in text
        assert "/auth/switch/qc" in text

    login(ids["sales"])
    response = client.get("/erp/", follow_redirects=False)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "QC系统" not in text


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
