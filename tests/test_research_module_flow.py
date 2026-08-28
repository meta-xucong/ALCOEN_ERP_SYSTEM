"""End-to-end tests for the AI CATS research module."""

from __future__ import annotations

import io
import json

from werkzeug.security import generate_password_hash

from app import db
from app.models import Department, ResearchBatch, ResearchProject, Role, User
from app.services.research_service import ResearchService


def _seed_research_users() -> tuple[int, int]:
    """Create minimal QC-based users for the research workflow."""
    dept = Department(name="Research QA")
    db.session.add(dept)
    db.session.flush()

    controller_role = Role(
        name="研发人员",
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
        username="research_controller",
        password_hash=generate_password_hash("Pass123!"),
        real_name="Research Controller",
        role_id=controller_role.id,
        department_id=dept.id,
        email="research_controller@example.com",
        is_active=True,
        require_password_change=False,
    )
    inspector = User(
        username="research_reviewer",
        password_hash=generate_password_hash("Pass123!"),
        real_name="Research Reviewer",
        role_id=inspector_role.id,
        department_id=dept.id,
        email="research_reviewer@example.com",
        is_active=True,
        require_password_change=False,
    )
    db.session.add_all([controller, inspector])
    db.session.commit()
    return controller.id, inspector.id


def _fake_save_project_file(file, project_id: int, attach_type: str) -> tuple[str, str]:
    """Return deterministic project attachment paths for tests."""
    suffix = file.filename.rsplit(".", 1)[-1].lower()
    return f"{attach_type}/{project_id}_{file.filename}", suffix


def _fake_save_batch_file(file, batch_id: int, attach_type: str) -> tuple[str, str]:
    """Return deterministic batch attachment paths for tests."""
    suffix = file.filename.rsplit(".", 1)[-1].lower()
    return f"{attach_type}/{batch_id}_{file.filename}", suffix


def _fake_copy_project_file_to_batch(project_id: int, batch_id: int, relative_path: str, attach_type: str) -> tuple[str, str]:
    """Return deterministic copied attachment paths for tests."""
    filename = relative_path.split("/")[-1]
    suffix = filename.rsplit(".", 1)[-1].lower()
    return f"{attach_type}/{batch_id}_copied_{filename}", suffix


def test_research_module_end_to_end_workflow(app, client, login, monkeypatch):
    """Research module should complete project -> batch -> review -> acceptance."""
    with app.app_context():
        controller_id, inspector_id = _seed_research_users()

    monkeypatch.setattr(ResearchService, "_save_project_file", staticmethod(_fake_save_project_file))
    monkeypatch.setattr(ResearchService, "_save_batch_file", staticmethod(_fake_save_batch_file))
    monkeypatch.setattr(
        ResearchService,
        "_copy_project_file_to_batch",
        staticmethod(_fake_copy_project_file_to_batch),
    )

    login(controller_id)

    project_response = client.post(
        "/qc/research/projects/new",
        data={
            "project_code": "RS-001",
            "project_name": "色谱柱填料研究",
            "project_category": "方法开发",
            "research_direction": "填料稳定性优化",
            "initiation_title_0": "客户背景",
            "initiation_content_0": "需要优化稳定性",
            "initiation_file_0": (io.BytesIO(b"initiation"), "initiation.png"),
            "research_title_0": "参考谱图",
            "research_content_0": "前期测试数据",
            "research_file_0": (io.BytesIO(b"research"), "research.pdf"),
            "plan_title_0": "方案A",
            "plan_content_0": "分三组变量验证",
            "plan_file_0": (io.BytesIO(b"plan"), "plan.png"),
            "validation_title_0": "验证指标1",
            "validation_content_0": "峰型稳定性",
            "risk_title_0": "风险提示1",
            "risk_content_0": "样品量有限",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert project_response.status_code == 302
    assert "/qc/research/projects/" in project_response.headers.get("Location", "")

    with app.app_context():
        project = ResearchProject.query.filter_by(project_code="RS-001").first()
        assert project is not None
        assert len(project.initiation_materials) == 1
        assert len(project.research_materials) == 1
        assert len(project.experiment_plans) == 1
        assert len(project.validation_items) == 1
        assert len(project.risk_notes) == 1
        project_id = project.id

    batch_response = client.post(
        "/qc/research/batches/new",
        data={
            "submit_action": "submit",
            "batch_no": "RB-001",
            "project_id": str(project_id),
            "sample_quantity": "12.5",
            "reviewer_id": str(inspector_id),
            "phase_result_file": (io.BytesIO(b"phase-result"), "phase_result.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert batch_response.status_code == 302
    assert "/qc/research/batches/" in batch_response.headers.get("Location", "")

    with app.app_context():
        batch = ResearchBatch.query.filter_by(batch_no="RB-001").first()
        assert batch is not None
        assert batch.status == "research_submitted"
        assert batch.reviewer_id == inspector_id
        assert len(batch.attachments) == 5
        assert batch.phase_result_file_path.endswith("phase_result.png")
        assert any(history.action == "提交指导审批" for history in batch.histories)
        batch_id = batch.id
        attachment_ids = [attachment.id for attachment in batch.attachments]

    login(inspector_id)

    review_page = client.get(f"/qc/research/reviews/{batch_id}", follow_redirects=False)
    assert review_page.status_code == 200
    assert "指导审批" in review_page.get_data(as_text=True)

    review_payload = {"submit_action": "submit"}
    for attachment_id in attachment_ids:
        review_payload[f"result_{attachment_id}"] = "approved"
        review_payload[f"suggestion_{attachment_id}"] = "可以继续推进"

    review_response = client.post(
        f"/qc/research/reviews/{batch_id}",
        data=review_payload,
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert review_response.status_code == 302
    assert f"/qc/research/acceptance/{batch_id}" in review_response.headers.get("Location", "")

    with app.app_context():
        batch = ResearchBatch.query.get(batch_id)
        assert batch is not None
        assert batch.status == "review_completed"
        assert batch.review_completed_at is not None

    reviewer_sign = client.post(
        f"/qc/research/acceptance/{batch_id}/sign",
        follow_redirects=False,
    )
    assert reviewer_sign.status_code == 302

    with app.app_context():
        batch = ResearchBatch.query.get(batch_id)
        assert batch is not None
        assert batch.status == "review_completed"
        assert len(batch.signatures) == 1

    login(controller_id)

    researcher_sign = client.post(
        f"/qc/research/acceptance/{batch_id}/sign",
        follow_redirects=False,
    )
    assert researcher_sign.status_code == 302

    acceptance_page = client.get(f"/qc/research/acceptance/{batch_id}", follow_redirects=False)
    assert acceptance_page.status_code == 200
    assert "阶段研发完成" in acceptance_page.get_data(as_text=True)

    with app.app_context():
        batch = ResearchBatch.query.get(batch_id)
        assert batch is not None
        assert batch.status == "accepted"
        assert batch.accepted_at is not None
        assert len(batch.signatures) == 2
        assert any(history.action == "阶段研发完成" for history in batch.histories)


def test_research_project_core_materials_are_optional(app, client, login):
    """Projects can be created and edited without initiation, research, or plan files."""
    with app.app_context():
        controller_id, _ = _seed_research_users()

    login(controller_id)
    new_page = client.get("/qc/research/projects/new")
    new_page_html = new_page.get_data(as_text=True)
    assert new_page.status_code == 200
    assert '立项资料 <span class="text-danger">*</span>' not in new_page_html
    assert '研究资料 <span class="text-danger">*</span>' not in new_page_html
    assert '实验方案 <span class="text-danger">*</span>' not in new_page_html

    create_response = client.post(
        "/qc/research/projects/new",
        data={
            "project_code": "RS-OPTIONAL-001",
            "project_name": "无资料研究项目",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert create_response.status_code == 302

    with app.app_context():
        project = ResearchProject.query.filter_by(project_code="RS-OPTIONAL-001").first()
        assert project is not None
        assert project.attachments == []
        project_id = project.id

    edit_response = client.post(
        f"/qc/research/projects/{project_id}/edit",
        data={
            "project_code": "RS-OPTIONAL-001",
            "project_name": "无资料研究项目（已编辑）",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert edit_response.status_code == 302

    with app.app_context():
        project = db.session.get(ResearchProject, project_id)
        assert project.project_name == "无资料研究项目（已编辑）"
        assert project.attachments == []
