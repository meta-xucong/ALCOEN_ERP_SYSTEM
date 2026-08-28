"""Research module service layer."""

from __future__ import annotations

import os
import secrets
import shutil
from datetime import datetime
from typing import Optional

from flask import current_app
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from app import db
from app.models import (
    QC_MANAGER_ROLE_CODES,
    RESEARCH_ATTACHMENT_TITLE_PREFIX,
    ResearchAcceptanceSignature,
    ResearchBatch,
    ResearchBatchAttachment,
    ResearchBatchHistory,
    ResearchProject,
    ResearchProjectAttachment,
    ResearchReviewRecord,
    User,
)


class ResearchService:
    """Service helpers for the AI CATS research module."""

    RESEARCH_CREATOR_ROLE_CODE = 'qc_controller'
    RESEARCH_REVIEWER_ROLE_CODE = 'qc_inspector'
    RESEARCH_MANAGER_ROLE_CODES = QC_MANAGER_ROLE_CODES
    RESEARCH_PROJECT_PERMISSION_CODES = (
        'qc_workpiece_view',
        'qc_workpiece_create',
        'qc_workpiece_edit',
        'qc_workpiece_delete',
    )
    RESEARCH_BATCH_PERMISSION_CODES = (
        'qc_work_order_view',
        'qc_work_order_create',
        'qc_work_order_edit',
        'qc_work_order_delete',
    )
    RESEARCH_REVIEW_PERMISSION_CODES = (
        'qc_inspection_view',
        'qc_inspection_perform',
    )
    RESEARCH_ACCEPTANCE_PERMISSION_CODES = (
        'qc_acceptance_perform',
        'qc_acceptance_rollback',
    )
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'pdf'}
    ATTACHMENT_TYPES = (
        'initiation_material',
        'research_material',
        'experiment_plan',
        'validation_item',
        'risk_note',
    )
    _ATTACH_SUBFOLDER_MAP = {
        'initiation_material': 'initiation_materials',
        'research_material': 'research_materials',
        'experiment_plan': 'experiment_plans',
        'validation_item': 'validation_items',
        'risk_note': 'risk_notes',
        'feedback': 'feedback_files',
        'initiation_note': 'initiation_notes',
        'phase_result': 'phase_results',
        'supplementary_note': 'supplementary_notes',
    }

    _SECTION_UPLOAD_FIELDS = {
        'initiation': (
            'initiation_note_file_path',
            'initiation_note_file_type',
            'initiation_note_original_name',
            'initiation_note',
        ),
        'result': (
            'phase_result_file_path',
            'phase_result_file_type',
            'phase_result_original_name',
            'phase_result',
        ),
        'supplement': (
            'supplementary_note_file_path',
            'supplementary_note_file_type',
            'supplementary_note_original_name',
            'supplementary_note',
        ),
    }

    @staticmethod
    def _to_float(value, default: float = 0.0) -> float:
        """Safely parse a float-like input."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _allowed_file(filename: str) -> bool:
        """Return whether the upload extension is supported."""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ResearchService.ALLOWED_EXTENSIONS

    @staticmethod
    def _get_file_extension(filename: str) -> str:
        """Return the lowercase file extension."""
        if '.' in filename:
            return filename.rsplit('.', 1)[1].lower()
        return ''

    @staticmethod
    def _has_any_permission(user: User, permission_codes: tuple[str, ...]) -> bool:
        """Return whether the user has any permission from the provided set."""
        return any(user.has_ai_cats_permission(code) for code in permission_codes)

    @staticmethod
    def project_upload_root(project_id: int) -> str:
        """Return the filesystem root for research project uploads."""
        return os.path.join(current_app.root_path, '..', 'static', 'uploads', 'research', 'projects', str(project_id))

    @staticmethod
    def batch_upload_root(batch_id: int) -> str:
        """Return the filesystem root for research batch uploads."""
        return os.path.join(current_app.root_path, '..', 'static', 'uploads', 'research', 'batches', str(batch_id))

    @staticmethod
    def _project_query_for_user(user: User):
        """Return the scoped research-project query for the current user."""
        query = ResearchProject.query
        if user.is_superadmin or user.ai_cats_is_manager:
            return query
        if user.has_ai_cats_identity('researcher', 'research'):
            return query.filter(ResearchProject.creator_id == user.id)
        return query.filter(False)

    @staticmethod
    def _batch_query_for_user(user: User):
        """Return the scoped research-batch query for the current user."""
        query = ResearchBatch.query
        if user.is_superadmin or user.ai_cats_is_manager:
            return query
        if user.has_ai_cats_identity('researcher', 'research'):
            return query.filter(ResearchBatch.researcher_id == user.id)
        if user.has_ai_cats_identity('research_reviewer', 'research'):
            return query.filter(ResearchBatch.reviewer_id == user.id)
        return query.filter(False)

    @staticmethod
    def add_batch_history(
        batch: ResearchBatch,
        action: str,
        detail: str | None = None,
        user: User | None = None,
    ) -> ResearchBatchHistory:
        """Append an immutable history entry for one research batch."""
        history = ResearchBatchHistory(
            batch_id=batch.id,
            operator_id=user.id if user else None,
            action=action,
            detail=detail,
        )
        db.session.add(history)
        return history

    @staticmethod
    def _save_file_to_root(upload_root: str, file, subfolder: str) -> str:
        """Save an uploaded file and return its relative path below the upload root."""
        os.makedirs(os.path.join(upload_root, subfolder), exist_ok=True)
        safe_name = secure_filename(file.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
        target_path = os.path.join(upload_root, subfolder, filename)
        file.save(target_path)
        return f"{subfolder}/{filename}"

    @staticmethod
    def _save_project_file(file, project_id: int, attach_type: str) -> tuple[str, str]:
        """Persist one research-project attachment file."""
        if not file or not file.filename:
            raise ValueError('请选择要上传的文件')
        if not ResearchService._allowed_file(file.filename):
            raise ValueError('不支持的文件格式，请上传图片或 PDF')
        relative_path = ResearchService._save_file_to_root(
            ResearchService.project_upload_root(project_id),
            file,
            ResearchService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others'),
        )
        return relative_path, ResearchService._get_file_extension(file.filename)

    @staticmethod
    def _save_batch_file(file, batch_id: int, attach_type: str) -> tuple[str, str]:
        """Persist one research-batch file."""
        if not file or not file.filename:
            raise ValueError('请选择要上传的文件')
        if not ResearchService._allowed_file(file.filename):
            raise ValueError('不支持的文件格式，请上传图片或 PDF')
        relative_path = ResearchService._save_file_to_root(
            ResearchService.batch_upload_root(batch_id),
            file,
            ResearchService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others'),
        )
        return relative_path, ResearchService._get_file_extension(file.filename)

    @staticmethod
    def _remove_project_file(project_id: int, relative_path: str) -> None:
        """Delete one stored research-project file when it exists."""
        if not relative_path:
            return
        filepath = os.path.join(ResearchService.project_upload_root(project_id), relative_path)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    @staticmethod
    def _remove_batch_file(batch_id: int, relative_path: str) -> None:
        """Delete one stored research-batch file when it exists."""
        if not relative_path:
            return
        filepath = os.path.join(ResearchService.batch_upload_root(batch_id), relative_path)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    @staticmethod
    def _copy_project_file_to_batch(
        project_id: int,
        batch_id: int,
        relative_path: str,
        attach_type: str,
    ) -> tuple[str, str]:
        """Copy one project attachment into the batch snapshot folder."""
        if not relative_path:
            return '', ''

        source_path = os.path.join(ResearchService.project_upload_root(project_id), relative_path)
        if not os.path.exists(source_path):
            raise ValueError(f'研究项目附件文件不存在：{os.path.basename(relative_path)}')

        source_name = os.path.basename(relative_path)
        safe_name = secure_filename(source_name)
        ext = ResearchService._get_file_extension(source_name) or 'bin'
        subfolder = ResearchService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others')
        target_root = ResearchService.batch_upload_root(batch_id)
        target_dir = os.path.join(target_root, subfolder)
        os.makedirs(target_dir, exist_ok=True)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
        target_path = os.path.join(target_dir, filename)
        shutil.copy2(source_path, target_path)
        return f"{subfolder}/{filename}", ext

    @staticmethod
    def _replace_batch_section_file(batch: ResearchBatch, section_key: str, file) -> None:
        """Replace one section-level upload on the research batch."""
        if not file or not file.filename:
            return
        path_field, type_field, name_field, attach_type = ResearchService._SECTION_UPLOAD_FIELDS[section_key]
        old_path = getattr(batch, path_field)
        relative_path, file_type = ResearchService._save_batch_file(file, batch.id, attach_type)
        setattr(batch, path_field, relative_path)
        setattr(batch, type_field, file_type)
        setattr(batch, name_field, file.filename)
        if old_path and old_path != relative_path:
            ResearchService._remove_batch_file(batch.id, old_path)

    @staticmethod
    def _delete_batch_section_files(batch: ResearchBatch) -> None:
        """Delete all section-level files stored on the batch."""
        for path_field, _, _, _ in ResearchService._SECTION_UPLOAD_FIELDS.values():
            relative_path = getattr(batch, path_field)
            if relative_path:
                ResearchService._remove_batch_file(batch.id, relative_path)

    @staticmethod
    def can_access_project_library(user: User) -> bool:
        """Return whether the user can open the research project library."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return ResearchService._has_any_permission(user, ResearchService.RESEARCH_PROJECT_PERMISSION_CODES)
        if user.has_ai_cats_identity('researcher', 'research'):
            return ResearchService._has_any_permission(user, ResearchService.RESEARCH_PROJECT_PERMISSION_CODES)
        return False

    @staticmethod
    def can_create_project(user: User) -> bool:
        """Return whether the user can create research projects."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_create')
        return (
            user.has_ai_cats_identity('researcher', 'research')
            and user.has_ai_cats_permission('qc_workpiece_create')
        )

    @staticmethod
    def can_edit_project(user: User, project: ResearchProject) -> bool:
        """Return whether the user can edit one research project."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_edit')
        return (
            user.has_ai_cats_identity('researcher', 'research')
            and project.creator_id == user.id
            and user.has_ai_cats_permission('qc_workpiece_edit')
        )

    @staticmethod
    def can_delete_project(user: User, project: ResearchProject) -> bool:
        """Return whether the user can delete one research project."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_delete')
        return (
            user.has_ai_cats_identity('researcher', 'research')
            and project.creator_id == user.id
            and user.has_ai_cats_permission('qc_workpiece_delete')
        )

    @staticmethod
    def can_access_batch_launch(user: User) -> bool:
        """Return whether the user can open the research launch module."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return ResearchService._has_any_permission(user, ResearchService.RESEARCH_BATCH_PERMISSION_CODES)
        return (
            user.has_ai_cats_identity('researcher', 'research')
            and ResearchService._has_any_permission(user, ResearchService.RESEARCH_BATCH_PERMISSION_CODES)
        )

    @staticmethod
    def can_create_batch(user: User) -> bool:
        """Return whether the user can create research batches."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_work_order_create')
        return (
            user.has_ai_cats_identity('researcher', 'research')
            and user.has_ai_cats_permission('qc_work_order_create')
        )

    @staticmethod
    def can_edit_batch(user: User, batch: ResearchBatch) -> bool:
        """Return whether the user can edit one research batch."""
        if user.is_superadmin:
            return True
        if batch.status not in ['draft', 'research_pending', 'returned']:
            return False
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_work_order_edit')
        return (
            user.has_ai_cats_identity('researcher', 'research')
            and batch.researcher_id == user.id
            and user.has_ai_cats_permission('qc_work_order_edit')
        )

    @staticmethod
    def can_view_batch(user: User, batch: ResearchBatch) -> bool:
        """Return whether the user can view one research batch."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return True
        if user.has_ai_cats_identity('researcher', 'research') and batch.researcher_id == user.id:
            return True
        if user.has_ai_cats_identity('research_reviewer', 'research') and batch.reviewer_id == user.id:
            return True
        return False

    @staticmethod
    def can_access_review(user: User) -> bool:
        """Return whether the user can open the review module."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return ResearchService._has_any_permission(user, ResearchService.RESEARCH_REVIEW_PERMISSION_CODES)
        if user.has_ai_cats_identity('research_reviewer', 'research'):
            return ResearchService._has_any_permission(user, ResearchService.RESEARCH_REVIEW_PERMISSION_CODES)
        if user.has_ai_cats_identity('researcher', 'research'):
            return user.has_ai_cats_permission('qc_inspection_view')
        return False

    @staticmethod
    def can_review_batch(user: User, batch: ResearchBatch) -> bool:
        """Return whether the user can submit review results for a batch."""
        if user.is_superadmin:
            return True
        if batch.status not in ['research_submitted', 'review_completed']:
            return False
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_inspection_perform')
        return (
            user.has_ai_cats_identity('research_reviewer', 'research')
            and batch.reviewer_id == user.id
            and user.has_ai_cats_permission('qc_inspection_perform')
        )

    @staticmethod
    def can_access_acceptance(user: User) -> bool:
        """Return whether the user can open the acceptance module."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return ResearchService._has_any_permission(user, ResearchService.RESEARCH_ACCEPTANCE_PERMISSION_CODES)
        if user.has_ai_cats_identity('researcher', 'research'):
            return ResearchService._has_any_permission(user, ResearchService.RESEARCH_ACCEPTANCE_PERMISSION_CODES)
        if user.has_ai_cats_identity('research_reviewer', 'research'):
            return user.has_ai_cats_permission('qc_acceptance_perform')
        return False

    @staticmethod
    def eligible_acceptance_signer_roles(user: User, batch: ResearchBatch) -> list[str]:
        """Return every acceptance signer role the current user can act as."""
        if batch.status != 'review_completed':
            return []

        if user.is_superadmin:
            return ['researcher', 'reviewer']
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_perform'):
            return ['researcher', 'reviewer']
        if not user.has_ai_cats_permission('qc_acceptance_perform'):
            return []

        signer_roles: list[str] = []
        if batch.researcher_id == user.id:
            signer_roles.append('researcher')
        if batch.reviewer_id == user.id:
            signer_roles.append('reviewer')
        return signer_roles

    @staticmethod
    def can_accept_batch(user: User, batch: ResearchBatch, signer_role: Optional[str] = None) -> bool:
        """Return whether the current participant can sign research acceptance."""
        eligible_roles = ResearchService.eligible_acceptance_signer_roles(user, batch)
        if signer_role:
            return signer_role in eligible_roles
        return bool(eligible_roles)

    @staticmethod
    def can_cancel_acceptance_signature(user: User, batch: ResearchBatch, signer_role: str) -> bool:
        """Return whether the user can cancel one research acceptance signature."""
        if batch.status not in ['review_completed', 'accepted']:
            return False
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_rollback'):
            return signer_role in ['researcher', 'reviewer']
        if signer_role == 'researcher' and batch.researcher_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_perform')
        if signer_role == 'reviewer' and batch.reviewer_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_perform')
        return False

    @staticmethod
    def can_rollback_batch(user: User, batch: ResearchBatch) -> bool:
        """Return whether the user can roll a research batch back."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_rollback'):
            return batch.status in ['review_completed', 'accepted']
        if user.has_ai_cats_identity('researcher', 'research') and batch.researcher_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_rollback') and batch.status in ['review_completed', 'accepted']
        return False

    @staticmethod
    def get_dashboard_stats(user: User) -> dict[str, int]:
        """Return summary counters for the research dashboard."""
        query = ResearchService._batch_query_for_user(user)
        return {
            'total_batches': query.count(),
            'research_pending': query.filter(ResearchBatch.status.in_(['draft', 'research_pending'])).count(),
            'review_pending': query.filter(ResearchBatch.status == 'research_submitted').count(),
            'acceptance_pending': query.filter(ResearchBatch.status == 'review_completed').count(),
            'completed': query.filter(ResearchBatch.status == 'accepted').count(),
            'returned': query.filter(ResearchBatch.status == 'returned').count(),
        }

    @staticmethod
    def get_recent_batches(user: User, limit: int = 5) -> list[ResearchBatch]:
        """Return recent research batches for the dashboard."""
        return (
            ResearchService._batch_query_for_user(user)
            .order_by(ResearchBatch.updated_at.desc(), ResearchBatch.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_project_list(user: User, keyword: Optional[str] = None, page: int = 1, per_page: int | None = None):
        """Paginate research project templates."""
        query = ResearchService._project_query_for_user(user)
        if keyword:
            like_keyword = f'%{keyword.strip()}%'
            query = query.filter(
                or_(
                    ResearchProject.project_code.ilike(like_keyword),
                    ResearchProject.project_name.ilike(like_keyword),
                    ResearchProject.project_category.ilike(like_keyword),
                )
            )
        return query.order_by(ResearchProject.updated_at.desc(), ResearchProject.id.desc()).paginate(
            page=page,
            per_page=per_page or current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_batch_list(
        user: User,
        keyword: Optional[str] = None,
        page: int = 1,
        statuses: list[str] | tuple[str, ...] | None = None,
        per_page: int | None = None,
    ):
        """Paginate research batches for the requested workflow stage."""
        query = ResearchService._batch_query_for_user(user)
        if statuses:
            query = query.filter(ResearchBatch.status.in_(list(statuses)))
        if keyword:
            like_keyword = f'%{keyword.strip()}%'
            query = query.filter(
                or_(
                    ResearchBatch.batch_no.ilike(like_keyword),
                    ResearchBatch.project_name_snapshot.ilike(like_keyword),
                )
            )
        return query.order_by(ResearchBatch.updated_at.desc(), ResearchBatch.id.desc()).paginate(
            page=page,
            per_page=per_page or current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_project_choices(user: User) -> list[ResearchProject]:
        """Return selectable research projects for the batch form."""
        if not ResearchService.can_access_project_library(user):
            return []
        return (
            ResearchService._project_query_for_user(user)
            .order_by(ResearchProject.project_code.asc(), ResearchProject.id.asc())
            .all()
        )

    @staticmethod
    def get_project(project_id: int, user: User) -> Optional[ResearchProject]:
        """Return a visible research project or ``None``."""
        project = ResearchProject.query.get(project_id)
        if not project:
            return None
        if not ResearchService.can_access_project_library(user):
            return None
        if user.ai_cats_is_manager:
            return project
        if user.has_ai_cats_identity('researcher', 'research') and project.creator_id == user.id:
            return project
        return None

    @staticmethod
    def get_batch(batch_id: int, user: User) -> Optional[ResearchBatch]:
        """Return a visible research batch or ``None``."""
        batch = ResearchBatch.query.get(batch_id)
        if not batch:
            return None
        return batch if ResearchService.can_view_batch(user, batch) else None

    @staticmethod
    def create_project(data: dict, creator_id: int, auto_commit: bool = True) -> ResearchProject:
        """Create a new research project template."""
        project_code = (data.get('project_code') or '').strip()
        project_name = (data.get('project_name') or '').strip()
        project_category = (data.get('project_category') or '').strip() or None
        research_direction = (data.get('research_direction') or '').strip() or None

        if not project_code:
            raise ValueError('项目编号不能为空')
        if not project_name:
            raise ValueError('项目名称不能为空')

        existing = ResearchProject.query.filter_by(project_code=project_code).first()
        if existing:
            raise ValueError(f"项目编号 '{project_code}' 已存在")

        project = ResearchProject(
            project_code=project_code,
            project_name=project_name,
            project_category=project_category,
            research_direction=research_direction,
            creator_id=creator_id,
        )
        db.session.add(project)
        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return project

    @staticmethod
    def update_project(project_id: int, data: dict, user: User) -> ResearchProject:
        """Update one research project template."""
        project = ResearchProject.query.get(project_id)
        if not project:
            raise ValueError('研究项目不存在')
        if not ResearchService.can_edit_project(user, project):
            raise ValueError('没有权限编辑该研究项目')

        project_code = (data.get('project_code') or '').strip()
        project_name = (data.get('project_name') or '').strip()
        project_category = (data.get('project_category') or '').strip() or None
        research_direction = (data.get('research_direction') or '').strip() or None

        if not project_code:
            raise ValueError('项目编号不能为空')
        if not project_name:
            raise ValueError('项目名称不能为空')

        if project_code != project.project_code:
            existing = ResearchProject.query.filter_by(project_code=project_code).first()
            if existing:
                raise ValueError(f"项目编号 '{project_code}' 已存在")

        project.project_code = project_code
        project.project_name = project_name
        project.project_category = project_category
        project.research_direction = research_direction
        db.session.commit()
        return project

    @staticmethod
    def sync_project_attachments(project_id: int, attachment_map: dict[str, list[dict]], user: User) -> ResearchProject:
        """Replace submitted project attachments by section."""
        project = ResearchProject.query.get(project_id)
        if not project:
            raise ValueError('研究项目不存在')
        if not ResearchService.can_edit_project(user, project):
            raise ValueError('没有权限编辑该研究项目')

        attachment_map = attachment_map or {}
        for attach_type, items in attachment_map.items():
            if attach_type not in ResearchService.ATTACHMENT_TYPES or not items:
                continue

            existing_attachments = ResearchProjectAttachment.query.filter_by(
                project_id=project.id,
                attach_type=attach_type,
            ).all()
            for attachment in existing_attachments:
                if attachment.file_path:
                    ResearchService._remove_project_file(project.id, attachment.file_path)
                db.session.delete(attachment)
            db.session.flush()

            for index, item in enumerate(items):
                file = item.get('file')
                title = (item.get('title') or '').strip() or None
                content = (item.get('content') or '').strip() or None
                has_file = bool(file and file.filename)
                if not (title or content or has_file):
                    continue
                relative_path = ''
                file_type = ''
                if has_file:
                    relative_path, file_type = ResearchService._save_project_file(file, project.id, attach_type)
                db.session.add(
                    ResearchProjectAttachment(
                        project_id=project.id,
                        attach_type=attach_type,
                        title=title,
                        content=content,
                        file_path=relative_path,
                        file_type=file_type,
                        is_required=False,
                        sort_order=index,
                    )
                )

        db.session.commit()
        return project

    @staticmethod
    def _serialize_project_attachment(attachment: ResearchProjectAttachment) -> dict:
        """Serialize one project attachment preview row."""
        return {
            'title': attachment.display_title,
            'content': attachment.content or '',
            'filename': os.path.basename(attachment.file_path) if attachment.file_path else '',
            'url': attachment.file_url,
            'is_image': attachment.is_image,
        }

    @staticmethod
    def serialize_project_preview(project: ResearchProject) -> dict:
        """Return a JSON-safe project preview payload for the batch form."""
        return {
            'id': project.id,
            'project_code': project.project_code,
            'project_name': project.project_name,
            'project_category': project.project_category or '',
            'research_direction': project.research_direction or '',
            'initiation_materials': [
                ResearchService._serialize_project_attachment(attachment)
                for attachment in project.initiation_materials
            ],
            'research_materials': [
                ResearchService._serialize_project_attachment(attachment)
                for attachment in project.research_materials
            ],
            'experiment_plans': [
                ResearchService._serialize_project_attachment(attachment)
                for attachment in project.experiment_plans
            ],
            'validation_items': [
                ResearchService._serialize_project_attachment(attachment)
                for attachment in project.validation_items
            ],
            'risk_notes': [
                ResearchService._serialize_project_attachment(attachment)
                for attachment in project.risk_notes
            ],
        }

    @staticmethod
    def create_batch(
        data: dict,
        researcher_id: int,
        status: str = 'draft',
        allow_partial: bool = False,
        auto_commit: bool = True,
    ) -> ResearchBatch:
        """Create a new research batch."""
        batch_no = (data.get('batch_no') or '').strip()
        project_name_snapshot = (data.get('project_name_snapshot') or '').strip()
        sample_quantity = ResearchService._to_float(data.get('sample_quantity'), 0.0)

        if not batch_no:
            raise ValueError('研究批次号不能为空')
        if not data.get('project_id'):
            raise ValueError('请选择研究项目')
        if not project_name_snapshot:
            raise ValueError('研究项目名称不能为空')
        if sample_quantity < 0:
            raise ValueError('样品数量不能为负数')
        if not allow_partial and sample_quantity <= 0:
            raise ValueError('样品数量必须大于 0')

        existing = ResearchBatch.query.filter_by(batch_no=batch_no).first()
        if existing:
            raise ValueError(f"研究批次号 '{batch_no}' 已存在")

        batch = ResearchBatch(
            batch_no=batch_no,
            project_id=data.get('project_id'),
            project_name_snapshot=project_name_snapshot,
            sample_quantity=sample_quantity,
            researcher_id=researcher_id,
            reviewer_id=data.get('reviewer_id'),
            status=status,
        )
        db.session.add(batch)
        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return batch

    @staticmethod
    def update_batch(batch_id: int, data: dict, user: User, allow_partial: bool = False) -> ResearchBatch:
        """Update one research batch."""
        batch = ResearchBatch.query.get(batch_id)
        if not batch:
            raise ValueError('研究批次不存在')
        if not ResearchService.can_edit_batch(user, batch):
            raise ValueError('没有权限编辑该研究批次')

        batch_no = (data.get('batch_no') or '').strip()
        project_name_snapshot = (data.get('project_name_snapshot') or '').strip()
        sample_quantity = ResearchService._to_float(data.get('sample_quantity'), 0.0)

        if not batch_no:
            raise ValueError('研究批次号不能为空')
        if not data.get('project_id'):
            raise ValueError('请选择研究项目')
        if not project_name_snapshot:
            raise ValueError('项目名称不能为空')
        if sample_quantity < 0:
            raise ValueError('样品数量不能为负数')
        if not allow_partial and sample_quantity <= 0:
            raise ValueError('样品数量必须大于 0')

        if batch_no != batch.batch_no:
            existing = ResearchBatch.query.filter_by(batch_no=batch_no).first()
            if existing:
                raise ValueError(f"研究批次号 '{batch_no}' 已存在")

        batch.batch_no = batch_no
        batch.project_id = data.get('project_id')
        batch.project_name_snapshot = project_name_snapshot
        batch.sample_quantity = sample_quantity
        batch.reviewer_id = data.get('reviewer_id')
        db.session.commit()
        return batch

    @staticmethod
    def _reset_batch_snapshot(batch: ResearchBatch) -> None:
        """Clear copied project snapshot data, review results, and signatures."""
        for record in list(batch.review_records):
            if record.feedback_file_path:
                ResearchService._remove_batch_file(batch.id, record.feedback_file_path)
            db.session.delete(record)

        for attachment in list(batch.attachments):
            if attachment.file_path:
                ResearchService._remove_batch_file(batch.id, attachment.file_path)
            db.session.delete(attachment)

        for signature in list(batch.signatures):
            db.session.delete(signature)

        batch.review_completed_at = None
        batch.accepted_at = None
        batch.returned_at = None
        batch.return_reason = None

    @staticmethod
    def apply_project_to_batch(batch_id: int, project_id: int, user: User) -> ResearchBatch:
        """Clone project attachments into one batch snapshot."""
        batch = ResearchBatch.query.get(batch_id)
        project = ResearchProject.query.get(project_id)
        if not batch or not project:
            raise ValueError('研究批次或研究项目不存在')
        if not ResearchService.can_edit_batch(user, batch):
            raise ValueError('没有权限同步该研究批次')
        if not ResearchService.can_access_project_library(user):
            raise ValueError('没有权限读取研究项目模板')

        ResearchService._reset_batch_snapshot(batch)
        batch.project_id = project.id
        batch.project_name_snapshot = project.project_name

        for attachment in project.attachments:
            file_path = ''
            file_type = ''
            if attachment.file_path:
                file_path, file_type = ResearchService._copy_project_file_to_batch(
                    project_id=project.id,
                    batch_id=batch.id,
                    relative_path=attachment.file_path,
                    attach_type=attachment.attach_type,
                )
            db.session.add(
                ResearchBatchAttachment(
                    batch_id=batch.id,
                    attach_type=attachment.attach_type,
                    source_type='project_snapshot',
                    title=attachment.title,
                    content=attachment.content,
                    file_path=file_path,
                    file_type=file_type,
                    is_required=attachment.is_required,
                    sort_order=attachment.sort_order,
                )
            )

        db.session.commit()
        return batch

    @staticmethod
    def sync_batch_section_files(
        batch_id: int,
        initiation_note_file,
        phase_result_file,
        supplementary_note_file,
        user: User,
        auto_commit: bool = True,
    ) -> ResearchBatch:
        """Persist section-level supplemental files for a research batch."""
        batch = ResearchBatch.query.get(batch_id)
        if not batch:
            raise ValueError('研究批次不存在')
        if not ResearchService.can_edit_batch(user, batch):
            raise ValueError('没有权限编辑该研究批次')

        ResearchService._replace_batch_section_file(batch, 'initiation', initiation_note_file)
        ResearchService._replace_batch_section_file(batch, 'result', phase_result_file)
        ResearchService._replace_batch_section_file(batch, 'supplement', supplementary_note_file)

        if auto_commit:
            db.session.commit()
        return batch

    @staticmethod
    def submit_batch_for_review(batch_id: int, reviewer_id: int, user: User) -> ResearchBatch:
        """Submit one research batch into the review stage."""
        batch = ResearchBatch.query.get(batch_id)
        if not batch:
            raise ValueError('研究批次不存在')
        if not ResearchService.can_edit_batch(user, batch):
            raise ValueError('没有权限提交该研究批次')

        reviewer = User.query.get(reviewer_id)
        if (
            not reviewer
            or not reviewer.is_active
            or not reviewer.has_ai_cats_identity('research_reviewer', 'research')
        ):
            raise ValueError('请选择有效的指导/验收人员')
        if reviewer.id == batch.researcher_id:
            raise ValueError('研究人员与指导/验收人员必须由不同用户担任')
        if not batch.attachments:
            raise ValueError('请先选择研究项目并生成项目资料快照')

        batch.reviewer_id = reviewer_id
        batch.status = 'research_submitted'
        batch.research_submitted_at = datetime.now()
        batch.review_completed_at = None
        batch.accepted_at = None
        batch.returned_at = None
        batch.return_reason = None
        ResearchService.add_batch_history(
            batch,
            '提交指导审批',
            f'已提交给 {reviewer.real_name or reviewer.username} 进行指导审批',
            user,
        )
        db.session.commit()
        return batch

    @staticmethod
    def review_record_map(batch: ResearchBatch) -> dict[int, ResearchReviewRecord]:
        """Build an attachment-to-review mapping for templates."""
        return {record.attachment_id: record for record in batch.review_records}

    @staticmethod
    def submit_review(batch_id: int, results: list[dict], user: User, final_submit: bool = True) -> ResearchBatch:
        """Save or submit guidance review results."""
        batch = ResearchBatch.query.get(batch_id)
        if not batch:
            raise ValueError('研究批次不存在')
        if not ResearchService.can_review_batch(user, batch):
            raise ValueError('没有权限执行指导审批')

        attachments = ResearchBatchAttachment.query.filter_by(batch_id=batch.id).order_by(
            ResearchBatchAttachment.sort_order.asc(),
            ResearchBatchAttachment.id.asc(),
        ).all()
        attachment_ids = {attachment.id for attachment in attachments}
        existing_records = {
            record.attachment_id: record
            for record in ResearchReviewRecord.query.filter_by(batch_id=batch.id).all()
        }

        if final_submit and not results:
            raise ValueError('请填写指导审批结果')

        submitted_ids: list[int] = []
        for item in results:
            attachment_id = item.get('attachment_id')
            if attachment_id not in attachment_ids:
                raise ValueError('无效的研究附件 ID')
            submitted_ids.append(attachment_id)

        if len(submitted_ids) != len(set(submitted_ids)):
            raise ValueError('存在重复的审批结果，请重新提交')

        touched_records: dict[int, ResearchReviewRecord] = {}
        for item in results:
            attachment_id = item.get('attachment_id')
            result = (item.get('result') or '').strip()
            suggestion = (item.get('suggestion') or '').strip() or None
            feedback_file = item.get('feedback_file')
            record = existing_records.get(attachment_id)

            if not record:
                record = ResearchReviewRecord(
                    batch_id=batch.id,
                    reviewer_id=user.id,
                    attachment_id=attachment_id,
                    result='draft',
                )
                db.session.add(record)

            if result:
                if result not in ['approved', 'revise', 'draft']:
                    raise ValueError('审批结果只能为通过、需补充或草稿')
                record.result = result
            record.reviewer_id = user.id
            record.suggestion = suggestion

            if feedback_file and feedback_file.filename:
                old_feedback_path = record.feedback_file_path
                feedback_path, feedback_type = ResearchService._save_batch_file(feedback_file, batch.id, 'feedback')
                record.feedback_file_path = feedback_path
                record.feedback_file_type = feedback_type
                record.feedback_original_name = feedback_file.filename
                if old_feedback_path and old_feedback_path != feedback_path:
                    ResearchService._remove_batch_file(batch.id, old_feedback_path)

            touched_records[attachment_id] = record

        if final_submit:
            unresolved: list[str] = []
            revise_records: list[ResearchReviewRecord] = []

            for attachment in attachments:
                record = touched_records.get(attachment.id) or existing_records.get(attachment.id)
                if not record or record.result not in ['approved', 'revise']:
                    unresolved.append(attachment.display_title)
                    continue
                if record.result == 'revise':
                    revise_records.append(record)

            if unresolved:
                raise ValueError('请完成所有研究资料的审批结果后再提交')

            for signature in list(batch.signatures):
                db.session.delete(signature)
            batch.accepted_at = None

            if revise_records:
                batch.status = 'returned'
                batch.returned_at = datetime.now()
                batch.review_completed_at = None
                batch.return_reason = '；'.join(
                    record.suggestion or record.attachment.display_title
                    for record in revise_records
                )
                ResearchService.add_batch_history(
                    batch,
                    '提交指导审批',
                    '指导审批要求补充资料，已退回研发人员',
                    user,
                )
            else:
                batch.status = 'review_completed'
                batch.review_completed_at = datetime.now()
                batch.returned_at = None
                batch.return_reason = None
                ResearchService.add_batch_history(
                    batch,
                    '提交指导审批',
                    '指导审批已完成，进入共同验收阶段',
                    user,
                )
        else:
            ResearchService.add_batch_history(
                batch,
                '保存指导审批草稿',
                f'已保存 {len(touched_records)} 项审批记录',
                user,
            )

        db.session.commit()
        return batch

    @staticmethod
    def sign_acceptance(batch_id: int, user: User, signer_role: Optional[str] = None) -> dict:
        """Sign research acceptance for the current participant."""
        batch = ResearchBatch.query.get(batch_id)
        if not batch:
            raise ValueError('研究批次不存在')
        eligible_roles = ResearchService.eligible_acceptance_signer_roles(user, batch)
        if signer_role:
            signer_role = signer_role.strip()
            if signer_role not in ['researcher', 'reviewer']:
                raise ValueError('无效的确认角色')
            if signer_role not in eligible_roles:
                raise ValueError('没有权限执行共同验收')
        else:
            if not eligible_roles:
                raise ValueError('没有权限执行共同验收')
            if len(eligible_roles) != 1:
                raise ValueError('请指定确认角色')
            signer_role = eligible_roles[0]

        existing = ResearchAcceptanceSignature.query.filter_by(
            batch_id=batch.id,
            signer_role=signer_role,
        ).first()
        if existing:
            raise ValueError('您已完成共同验收确认，无需重复操作')

        signature = ResearchAcceptanceSignature(
            batch_id=batch.id,
            signer_id=user.id,
            signer_role=signer_role,
        )
        db.session.add(signature)
        db.session.flush()
        ResearchService.add_batch_history(
            batch,
            '共同验收确认',
            '研发人员已确认' if signer_role == 'researcher' else '指导/验收人员已确认',
            user,
        )

        signatures = ResearchAcceptanceSignature.query.filter_by(batch_id=batch.id).all()
        roles_signed = {item.signer_role for item in signatures}
        if 'researcher' in roles_signed and 'reviewer' in roles_signed:
            batch.status = 'accepted'
            batch.accepted_at = datetime.now()
            ResearchService.add_batch_history(batch, '阶段研发完成', '双方已完成共同验收确认', user)
            db.session.commit()
            return {'completed': True, 'message': '双方已确认，阶段研发完成'}

        db.session.commit()
        return {'completed': False, 'message': '共同验收确认已提交，等待另一方确认'}

    @staticmethod
    def cancel_acceptance_signature(batch_id: int, signer_role: str, user: User) -> ResearchBatch:
        """Cancel one acceptance signature without rolling the batch back."""
        batch = ResearchBatch.query.get(batch_id)
        if not batch:
            raise ValueError('研究批次不存在')
        if signer_role not in ['researcher', 'reviewer']:
            raise ValueError('无效的确认角色')
        if not ResearchService.can_cancel_acceptance_signature(user, batch, signer_role):
            raise ValueError('没有权限取消该共同验收确认')

        signature = ResearchAcceptanceSignature.query.filter_by(
            batch_id=batch.id,
            signer_role=signer_role,
        ).first()
        if not signature:
            raise ValueError('该角色尚未完成共同验收确认')

        if batch.status == 'accepted':
            batch.status = 'review_completed'
            batch.accepted_at = None

        db.session.delete(signature)
        ResearchService.add_batch_history(
            batch,
            '取消共同验收确认',
            '研发人员确认已取消' if signer_role == 'researcher' else '指导/验收人员确认已取消',
            user,
        )
        db.session.commit()
        return batch

    @staticmethod
    def rollback_batch(batch_id: int, target: str, reason: str, user: User) -> ResearchBatch:
        """Roll a research batch back to launch or review."""
        batch = ResearchBatch.query.get(batch_id)
        if not batch:
            raise ValueError('研究批次不存在')
        if not ResearchService.can_rollback_batch(user, batch):
            raise ValueError('没有权限执行回退操作')
        if target not in ['research', 'review']:
            raise ValueError('无效的回退目标')
        if not reason or not reason.strip():
            raise ValueError('请填写回退原因')

        ResearchAcceptanceSignature.query.filter_by(batch_id=batch.id).delete()
        batch.accepted_at = None
        batch.review_completed_at = None
        batch.returned_at = datetime.now()
        batch.return_reason = reason.strip()
        batch.status = 'research_pending' if target == 'research' else 'research_submitted'
        ResearchService.add_batch_history(
            batch,
            '共同验收回退',
            f"回退至{'研究发起' if target == 'research' else '指导审批'}：{reason.strip()}",
            user,
        )
        db.session.commit()
        return batch

    @staticmethod
    def delete_project(project_id: int, user: User) -> bool:
        """Delete one research project and all stored files."""
        project = ResearchProject.query.get(project_id)
        if not project:
            raise ValueError('研究项目不存在')
        if not ResearchService.can_delete_project(user, project):
            raise ValueError('没有权限删除该研究项目')
        if project.batches:
            raise ValueError('该研究项目已被研究批次引用，暂不可删除')

        for attachment in project.attachments:
            if attachment.file_path:
                ResearchService._remove_project_file(project.id, attachment.file_path)
        db.session.delete(project)
        db.session.commit()
        return True

    @staticmethod
    def delete_batch(batch_id: int, user: User) -> bool:
        """Delete one research batch and its stored files."""
        batch = ResearchBatch.query.get(batch_id)
        if not batch:
            raise ValueError('研究批次不存在')
        if not ResearchService.can_edit_batch(user, batch):
            raise ValueError('没有权限删除该研究批次')

        ResearchService._delete_batch_section_files(batch)
        for attachment in batch.attachments:
            if attachment.file_path:
                ResearchService._remove_batch_file(batch.id, attachment.file_path)
        for record in batch.review_records:
            if record.feedback_file_path:
                ResearchService._remove_batch_file(batch.id, record.feedback_file_path)

        db.session.delete(batch)
        db.session.commit()
        return True
