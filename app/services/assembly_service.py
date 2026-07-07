from __future__ import annotations

import os
import secrets
import shutil
from datetime import datetime
from typing import Optional

from flask import current_app
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from app import db
from app.models import (
    ASSEMBLY_STATUS_DISPLAY,
    AssemblyAcceptanceSignature,
    AssemblyInspectionRecord,
    AssemblyOrder,
    AssemblyOrderAttachment,
    AssemblyOrderComponent,
    AssemblyOrderHistory,
    AssemblyProduct,
    AssemblyProductAttachment,
    AssemblyProductComponent,
    QC_MANAGER_ROLE_CODES,
    QCWorkpiece,
    User,
)


class AssemblyService:
    """Service helpers for the AI CATS assembly/shipping module."""

    CONTROLLER_ROLE_CODE = 'qc_controller'
    INSPECTOR_ROLE_CODE = 'qc_inspector'
    MANAGER_ROLE_CODES = QC_MANAGER_ROLE_CODES
    PRODUCT_PERMISSION_CODES = (
        'qc_workpiece_view',
        'qc_workpiece_create',
        'qc_workpiece_edit',
        'qc_workpiece_delete',
    )
    ORDER_PERMISSION_CODES = (
        'qc_work_order_view',
        'qc_work_order_create',
        'qc_work_order_edit',
        'qc_work_order_delete',
    )
    INSPECTION_PERMISSION_CODES = (
        'qc_inspection_view',
        'qc_inspection_perform',
    )
    ACCEPTANCE_PERMISSION_CODES = (
        'qc_acceptance_perform',
        'qc_acceptance_rollback',
    )
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'pdf'}
    PRODUCT_ATTACHMENT_TYPES = ('assembly_sheet', 'remark')
    REQUIRED_PRODUCT_ATTACHMENT_TYPES = {'assembly_sheet'}
    RESERVED_STATUSES = {'assembly_pending', 'assembly_completed', 'inspection_pending', 'inspection_completed'}

    _ATTACH_SUBFOLDER_MAP = {
        'assembly_sheet': 'assembly_sheets',
        'remark': 'remarks',
        'assembly_record': 'assembly_records',
        'certificate': 'certificates',
        'report': 'reports',
        'registration_note': 'registration_notes',
        'certificate_note': 'certificate_notes',
        'remark_note': 'remark_notes',
    }

    _ORDER_SECTION_UPLOAD_FIELDS = {
        'registration': (
            'registration_note_file_path',
            'registration_note_file_type',
            'registration_note_original_name',
            'registration_note',
        ),
        'certificate': (
            'certificate_note_file_path',
            'certificate_note_file_type',
            'certificate_note_original_name',
            'certificate_note',
        ),
        'remark': (
            'remark_note_file_path',
            'remark_note_file_type',
            'remark_note_original_name',
            'remark_note',
        ),
    }

    @staticmethod
    def _allowed_file(filename: str) -> bool:
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in AssemblyService.ALLOWED_EXTENSIONS

    @staticmethod
    def _get_file_extension(filename: str) -> str:
        if '.' in filename:
            return filename.rsplit('.', 1)[1].lower()
        return ''

    @staticmethod
    def _to_float(value, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _has_any_permission(user: User, permission_codes: tuple[str, ...]) -> bool:
        return any(user.has_ai_cats_permission(code) for code in permission_codes)

    @staticmethod
    def product_upload_root(product_id: int) -> str:
        return os.path.join(current_app.root_path, '..', 'static', 'uploads', 'assembly', 'products', str(product_id))

    @staticmethod
    def order_upload_root(order_id: int) -> str:
        return os.path.join(current_app.root_path, '..', 'static', 'uploads', 'assembly', 'orders', str(order_id))

    @staticmethod
    def _save_file_to_root(upload_root: str, file, subfolder: str) -> str:
        os.makedirs(os.path.join(upload_root, subfolder), exist_ok=True)
        safe_name = secure_filename(file.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
        target_path = os.path.join(upload_root, subfolder, filename)
        file.save(target_path)
        return f"{subfolder}/{filename}"

    @staticmethod
    def _save_product_file(file, product_id: int, attach_type: str) -> tuple[str, str]:
        if not file or not file.filename:
            raise ValueError('请选择要上传的文件')
        if not AssemblyService._allowed_file(file.filename):
            raise ValueError('不支持的文件格式，请上传图片或 PDF')
        relative_path = AssemblyService._save_file_to_root(
            AssemblyService.product_upload_root(product_id),
            file,
            AssemblyService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others'),
        )
        return relative_path, AssemblyService._get_file_extension(file.filename)

    @staticmethod
    def _save_order_file(file, order_id: int, attach_type: str) -> tuple[str, str]:
        if not file or not file.filename:
            raise ValueError('请选择要上传的文件')
        if not AssemblyService._allowed_file(file.filename):
            raise ValueError('不支持的文件格式，请上传图片或 PDF')
        relative_path = AssemblyService._save_file_to_root(
            AssemblyService.order_upload_root(order_id),
            file,
            AssemblyService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others'),
        )
        return relative_path, AssemblyService._get_file_extension(file.filename)

    @staticmethod
    def _remove_product_file(product_id: int, relative_path: str) -> None:
        if not relative_path:
            return
        filepath = os.path.join(AssemblyService.product_upload_root(product_id), relative_path)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    @staticmethod
    def _remove_order_file(order_id: int, relative_path: str) -> None:
        if not relative_path:
            return
        filepath = os.path.join(AssemblyService.order_upload_root(order_id), relative_path)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    @staticmethod
    def _replace_product_attachment_file(attachment: AssemblyProductAttachment, file, attach_type: str) -> None:
        old_path = attachment.file_path
        relative_path, file_type = AssemblyService._save_product_file(file, attachment.product_id, attach_type)
        attachment.file_path = relative_path
        attachment.file_type = file_type
        if old_path and old_path != relative_path:
            AssemblyService._remove_product_file(attachment.product_id, old_path)

    @staticmethod
    def _replace_order_attachment_file(attachment: AssemblyOrderAttachment, file, attach_type: str) -> None:
        old_path = attachment.file_path
        relative_path, file_type = AssemblyService._save_order_file(file, attachment.order_id, attach_type)
        attachment.file_path = relative_path
        attachment.file_type = file_type
        if old_path and old_path != relative_path:
            AssemblyService._remove_order_file(attachment.order_id, old_path)

    @staticmethod
    def _copy_product_file_to_order(
        product_id: int,
        order_id: int,
        relative_path: str,
        attach_type: str,
    ) -> tuple[str, str]:
        if not relative_path:
            return '', ''

        source_path = os.path.join(AssemblyService.product_upload_root(product_id), relative_path)
        if not os.path.exists(source_path):
            raise ValueError(f'产品模板附件文件不存在：{os.path.basename(relative_path)}')

        source_name = os.path.basename(relative_path)
        safe_name = secure_filename(source_name)
        ext = AssemblyService._get_file_extension(source_name) or 'bin'
        subfolder = AssemblyService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others')
        target_root = AssemblyService.order_upload_root(order_id)
        target_dir = os.path.join(target_root, subfolder)
        os.makedirs(target_dir, exist_ok=True)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
        target_path = os.path.join(target_dir, filename)
        shutil.copy2(source_path, target_path)
        return f"{subfolder}/{filename}", ext

    @staticmethod
    def _replace_order_section_file(order: AssemblyOrder, section_key: str, file) -> None:
        if not file or not file.filename:
            return
        path_field, type_field, name_field, attach_type = AssemblyService._ORDER_SECTION_UPLOAD_FIELDS[section_key]
        old_path = getattr(order, path_field)
        relative_path, file_type = AssemblyService._save_order_file(file, order.id, attach_type)
        setattr(order, path_field, relative_path)
        setattr(order, type_field, file_type)
        setattr(order, name_field, file.filename)
        if old_path and old_path != relative_path:
            AssemblyService._remove_order_file(order.id, old_path)

    @staticmethod
    def _delete_order_section_files(order: AssemblyOrder) -> None:
        for path_field, _, _, _ in AssemblyService._ORDER_SECTION_UPLOAD_FIELDS.values():
            relative_path = getattr(order, path_field)
            if relative_path:
                AssemblyService._remove_order_file(order.id, relative_path)

    @staticmethod
    def add_order_history(
        order: AssemblyOrder,
        action: str,
        detail: str | None = None,
        user: User | None = None,
    ) -> AssemblyOrderHistory:
        history = AssemblyOrderHistory(
            order_id=order.id,
            operator_id=user.id if user else None,
            action=action,
            detail=detail,
        )
        db.session.add(history)
        return history

    @staticmethod
    def _product_query_for_user(user: User):
        query = AssemblyProduct.query
        if user.is_superadmin or user.ai_cats_is_manager:
            return query
        if user.ai_cats_is_controller:
            return query.filter(AssemblyProduct.creator_id == user.id)
        return query.filter(False)

    @staticmethod
    def _order_query_for_user(user: User):
        query = AssemblyOrder.query
        if user.is_superadmin or user.ai_cats_is_manager:
            return query
        if user.ai_cats_is_controller:
            return query.filter(AssemblyOrder.controller_id == user.id)
        if user.ai_cats_is_inspector:
            return query.filter(AssemblyOrder.inspector_id == user.id)
        return query.filter(False)

    @staticmethod
    def can_access_product_library(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return AssemblyService._has_any_permission(user, AssemblyService.PRODUCT_PERMISSION_CODES)
        if user.ai_cats_is_controller:
            return AssemblyService._has_any_permission(user, AssemblyService.PRODUCT_PERMISSION_CODES)
        return False

    @staticmethod
    def can_create_product(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_create')
        return user.ai_cats_is_controller and user.has_ai_cats_permission('qc_workpiece_create')

    @staticmethod
    def can_edit_product(user: User, product: AssemblyProduct) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_edit')
        return user.ai_cats_is_controller and product.creator_id == user.id and user.has_ai_cats_permission('qc_workpiece_edit')

    @staticmethod
    def can_delete_product(user: User, product: AssemblyProduct) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_delete')
        return user.ai_cats_is_controller and product.creator_id == user.id and user.has_ai_cats_permission('qc_workpiece_delete')

    @staticmethod
    def can_access_assembly_launch(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return AssemblyService._has_any_permission(user, AssemblyService.ORDER_PERMISSION_CODES)
        return user.ai_cats_is_controller and AssemblyService._has_any_permission(user, AssemblyService.ORDER_PERMISSION_CODES)

    @staticmethod
    def can_create_order(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_work_order_create')
        return user.ai_cats_is_controller and user.has_ai_cats_permission('qc_work_order_create')

    @staticmethod
    def can_edit_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if order.status not in ['draft', 'assembly_pending', 'rejected']:
            return False
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_work_order_edit')
        return user.ai_cats_is_controller and order.controller_id == user.id and user.has_ai_cats_permission('qc_work_order_edit')

    @staticmethod
    def can_delete_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_work_order_delete')
        return user.ai_cats_is_controller and order.controller_id == user.id and user.has_ai_cats_permission('qc_work_order_delete')

    @staticmethod
    def can_view_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return True
        if order.status == 'draft':
            return user.ai_cats_is_controller and order.controller_id == user.id and AssemblyService.can_access_assembly_launch(user)
        if user.ai_cats_is_controller and order.controller_id == user.id:
            return True
        if user.ai_cats_is_inspector and order.inspector_id == user.id:
            return True
        return False

    @staticmethod
    def can_access_inspection(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return AssemblyService._has_any_permission(user, AssemblyService.INSPECTION_PERMISSION_CODES)
        if user.ai_cats_is_controller:
            return user.has_ai_cats_permission('qc_inspection_view')
        if user.ai_cats_is_inspector:
            return AssemblyService._has_any_permission(user, AssemblyService.INSPECTION_PERMISSION_CODES)
        return False

    @staticmethod
    def can_inspect_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_inspection_perform'):
            return order.status in ['assembly_completed', 'inspection_pending']
        if user.ai_cats_is_inspector and order.inspector_id == user.id:
            return user.has_ai_cats_permission('qc_inspection_perform') and order.status in ['assembly_completed', 'inspection_pending']
        return False

    @staticmethod
    def can_access_acceptance(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return AssemblyService._has_any_permission(user, AssemblyService.ACCEPTANCE_PERMISSION_CODES)
        if user.ai_cats_is_controller:
            return AssemblyService._has_any_permission(user, AssemblyService.ACCEPTANCE_PERMISSION_CODES)
        if user.ai_cats_is_inspector:
            return user.has_ai_cats_permission('qc_acceptance_perform')
        return False

    @staticmethod
    def can_accept_order(user: User, order: AssemblyOrder) -> bool:
        return bool(AssemblyService.eligible_acceptance_signer_roles(user, order))

    @staticmethod
    def eligible_acceptance_signer_roles(user: User, order: AssemblyOrder) -> list[str]:
        """Return every acceptance signer role the user can act as for one assembly order."""
        if order.status != 'inspection_completed':
            return []
        if user.is_superadmin:
            return ['qc_controller', 'qc_inspector']
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_perform'):
            return ['qc_controller', 'qc_inspector']
        signer_roles: list[str] = []
        if user.ai_cats_is_controller and order.controller_id == user.id:
            if user.has_ai_cats_permission('qc_acceptance_perform'):
                signer_roles.append('qc_controller')
        if user.ai_cats_is_inspector and order.inspector_id == user.id:
            if user.has_ai_cats_permission('qc_acceptance_perform'):
                signer_roles.append('qc_inspector')
        return signer_roles

    @staticmethod
    def can_rollback_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_rollback'):
            return order.status in ['inspection_completed', 'accepted']
        if user.ai_cats_is_controller and order.controller_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_rollback') and order.status in ['inspection_completed', 'accepted']
        return False

    @staticmethod
    def can_cancel_acceptance_signature(user: User, order: AssemblyOrder, signer_role: str) -> bool:
        if order.status not in ['inspection_completed', 'accepted']:
            return False
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_rollback'):
            return signer_role in ['qc_controller', 'qc_inspector']
        if signer_role == 'qc_controller' and user.ai_cats_is_controller and order.controller_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_perform')
        if signer_role == 'qc_inspector' and user.ai_cats_is_inspector and order.inspector_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_perform')
        return False

    @staticmethod
    def get_product_list(user: User, keyword: str = None, page: int = 1):
        query = AssemblyService._product_query_for_user(user)
        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(
                or_(
                    AssemblyProduct.product_code.ilike(like_keyword),
                    AssemblyProduct.product_name.ilike(like_keyword),
                )
            )
        query = query.order_by(AssemblyProduct.created_at.desc())
        return query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_product_choices(user: User) -> list[AssemblyProduct]:
        if not AssemblyService.can_access_product_library(user):
            return []
        return AssemblyProduct.query.order_by(AssemblyProduct.product_code.asc(), AssemblyProduct.id.asc()).all()

    @staticmethod
    def get_workpiece_choices(user: User) -> list[QCWorkpiece]:
        """Return workpieces that can be selected in the assembly BOM editor."""
        if not AssemblyService.can_access_product_library(user):
            return []
        return QCWorkpiece.query.order_by(QCWorkpiece.workpiece_code.asc(), QCWorkpiece.id.asc()).all()

    @staticmethod
    def get_product(product_id: int, user: User) -> Optional[AssemblyProduct]:
        product = AssemblyProduct.query.get(product_id)
        if not product:
            return None
        if user.is_superadmin or user.ai_cats_is_manager:
            return product
        if user.ai_cats_is_controller and product.creator_id == user.id:
            return product
        return None

    @staticmethod
    def search_workpieces(user: User, keyword: str, limit: int = 10) -> list[QCWorkpiece]:
        if not keyword or not AssemblyService.can_access_product_library(user):
            return []
        like_keyword = f'%{keyword.strip()}%'
        return QCWorkpiece.query.filter(
            or_(
                QCWorkpiece.workpiece_code.ilike(like_keyword),
                QCWorkpiece.workpiece_name.ilike(like_keyword),
            )
        ).order_by(QCWorkpiece.workpiece_code.asc(), QCWorkpiece.id.asc()).limit(limit).all()

    @staticmethod
    def get_order_list(user: User, status: str = None, keyword: str = None, page: int = 1):
        query = AssemblyService._order_query_for_user(user)
        if user.ai_cats_is_manager and not user.is_superadmin:
            query = query.filter(AssemblyOrder.status != 'draft')
        if status:
            query = query.filter(AssemblyOrder.status == status)
        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(
                or_(
                    AssemblyOrder.batch_no.ilike(like_keyword),
                    AssemblyOrder.product_name_snapshot.ilike(like_keyword),
                )
            )
        query = query.order_by(AssemblyOrder.created_at.desc())
        return query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_inspection_list(user: User, keyword: str = None, page: int = 1):
        query = AssemblyOrder.query.filter(
            AssemblyOrder.status.in_(['assembly_completed', 'inspection_pending'])
        )
        if not user.is_superadmin:
            if user.ai_cats_is_manager and AssemblyService.can_access_inspection(user):
                query = query
            elif user.ai_cats_is_inspector and AssemblyService.can_access_inspection(user):
                query = query.filter(AssemblyOrder.inspector_id == user.id)
            elif user.ai_cats_is_controller and AssemblyService.can_access_inspection(user):
                query = query.filter(AssemblyOrder.controller_id == user.id)
            else:
                query = query.filter(False)
        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(
                or_(
                    AssemblyOrder.batch_no.ilike(like_keyword),
                    AssemblyOrder.product_name_snapshot.ilike(like_keyword),
                )
            )
        query = query.order_by(AssemblyOrder.assembly_submitted_at.desc(), AssemblyOrder.id.desc())
        return query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_acceptance_list(user: User, keyword: str = None, page: int = 1):
        query = AssemblyOrder.query.filter(
            AssemblyOrder.status.in_(['inspection_completed', 'accepted'])
        )
        if not user.is_superadmin:
            if user.ai_cats_is_manager and AssemblyService.can_access_acceptance(user):
                query = query
            elif user.ai_cats_is_controller and AssemblyService.can_access_acceptance(user):
                query = query.filter(AssemblyOrder.controller_id == user.id)
            elif user.ai_cats_is_inspector and AssemblyService.can_access_acceptance(user):
                query = query.filter(AssemblyOrder.inspector_id == user.id)
            else:
                query = query.filter(False)
        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(
                or_(
                    AssemblyOrder.batch_no.ilike(like_keyword),
                    AssemblyOrder.product_name_snapshot.ilike(like_keyword),
                )
            )
        query = query.order_by(AssemblyOrder.inspection_completed_at.desc(), AssemblyOrder.id.desc())
        return query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_dashboard_stats(user: User) -> dict[str, int]:
        query = AssemblyService._order_query_for_user(user)
        return {
            'assembly_pending': query.filter(AssemblyOrder.status.in_(['draft', 'assembly_pending'])).count(),
            'assembly_completed': query.filter(AssemblyOrder.status == 'assembly_completed').count(),
            'inspection_pending': query.filter(AssemblyOrder.status == 'inspection_pending').count(),
            'inspection_completed': query.filter(AssemblyOrder.status == 'inspection_completed').count(),
            'accepted': query.filter(AssemblyOrder.status == 'accepted').count(),
            'rejected': query.filter(AssemblyOrder.status == 'rejected').count(),
        }

    @staticmethod
    def get_recent_orders(user: User, limit: int = 5) -> list[AssemblyOrder]:
        return (
            AssemblyService._order_query_for_user(user)
            .order_by(AssemblyOrder.created_at.desc(), AssemblyOrder.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def create_product(data: dict, creator_id: int, auto_commit: bool = True) -> AssemblyProduct:
        product_code = (data.get('product_code') or '').strip()
        product_name = (data.get('product_name') or '').strip()

        if not product_code:
            raise ValueError('产品编号不能为空')
        if not product_name:
            raise ValueError('产品名称不能为空')

        existing = AssemblyProduct.query.filter_by(product_code=product_code).first()
        if existing:
            raise ValueError(f"产品编号 '{product_code}' 已存在")

        product = AssemblyProduct(
            product_code=product_code,
            product_name=product_name,
            creator_id=creator_id,
        )
        db.session.add(product)
        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return product

    @staticmethod
    def update_product(
        product_id: int,
        data: dict,
        user: User,
        auto_commit: bool = True,
    ) -> AssemblyProduct:
        product = AssemblyProduct.query.get(product_id)
        if not product:
            raise ValueError('产品不存在')
        if not AssemblyService.can_edit_product(user, product):
            raise ValueError('没有权限编辑该产品')

        product_code = (data.get('product_code') or '').strip()
        product_name = (data.get('product_name') or '').strip()
        if not product_code:
            raise ValueError('产品编号不能为空')
        if not product_name:
            raise ValueError('产品名称不能为空')

        if product_code != product.product_code:
            existing = AssemblyProduct.query.filter_by(product_code=product_code).first()
            if existing:
                raise ValueError(f"产品编号 '{product_code}' 已存在")

        product.product_code = product_code
        product.product_name = product_name
        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return product

    @staticmethod
    def sync_product_components(
        product_id: int,
        components: list[dict],
        user: User,
        auto_commit: bool = True,
    ) -> AssemblyProduct:
        product = AssemblyProduct.query.get(product_id)
        if not product:
            raise ValueError('产品不存在')
        if not AssemblyService.can_edit_product(user, product):
            raise ValueError('没有权限编辑该产品')

        normalized: list[dict] = []
        for idx, item in enumerate(components or []):
            workpiece_id = item.get('workpiece_id')
            workpiece = QCWorkpiece.query.get(int(workpiece_id)) if workpiece_id else None
            quantity_per_unit = AssemblyService._to_float(item.get('quantity_per_unit'), 0.0)
            if workpiece and quantity_per_unit > 0:
                normalized.append(
                    {
                        'workpiece': workpiece,
                        'quantity_per_unit': quantity_per_unit,
                        'sort_order': idx,
                    }
                )

        if len(normalized) < 2:
            raise ValueError('装配结构至少需要保留两个配件')

        seen_workpiece_ids: set[int] = set()
        for item in normalized:
            if item['workpiece'].id in seen_workpiece_ids:
                raise ValueError('装配结构中不能重复选择同一工件')
            seen_workpiece_ids.add(item['workpiece'].id)

        existing_components = AssemblyProductComponent.query.filter_by(product_id=product.id).order_by(
            AssemblyProductComponent.sort_order.asc(),
            AssemblyProductComponent.id.asc(),
        ).all()

        for idx, item in enumerate(normalized):
            workpiece = item['workpiece']
            quantity_per_unit = item['quantity_per_unit']
            if idx < len(existing_components):
                component = existing_components[idx]
                component.workpiece_id = workpiece.id
                component.workpiece_code_snapshot = workpiece.workpiece_code
                component.workpiece_name_snapshot = workpiece.workpiece_name
                component.quantity_per_unit = quantity_per_unit
                component.sort_order = idx
            else:
                db.session.add(
                    AssemblyProductComponent(
                        product_id=product.id,
                        workpiece_id=workpiece.id,
                        workpiece_code_snapshot=workpiece.workpiece_code,
                        workpiece_name_snapshot=workpiece.workpiece_name,
                        quantity_per_unit=quantity_per_unit,
                        sort_order=idx,
                    )
                )

        for redundant in existing_components[len(normalized):]:
            db.session.delete(redundant)

        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return product

    @staticmethod
    def sync_product_attachments(
        product_id: int,
        assembly_sheet_items: list[dict],
        remark_items: list[dict],
        user: User,
        auto_commit: bool = True,
    ) -> AssemblyProduct:
        product = AssemblyProduct.query.get(product_id)
        if not product:
            raise ValueError('产品不存在')
        if not AssemblyService.can_edit_product(user, product):
            raise ValueError('没有权限编辑该产品')

        existing_sheets = AssemblyProductAttachment.query.filter_by(
            product_id=product.id,
            attach_type='assembly_sheet',
        ).order_by(AssemblyProductAttachment.sort_order.asc(), AssemblyProductAttachment.id.asc()).all()

        normalized_sheets = []
        for idx, item in enumerate(assembly_sheet_items or []):
            title = (item.get('title') or '').strip() or f'装配单{idx + 1}'
            content = (item.get('content') or '').strip()
            upload = item.get('file')
            if title or content or (upload and upload.filename):
                normalized_sheets.append({'title': title, 'content': content, 'file': upload})

        if not normalized_sheets:
            raise ValueError('请至少添加一项装配单')

        for idx, item in enumerate(normalized_sheets):
            upload = item.get('file')
            if idx < len(existing_sheets):
                attachment = existing_sheets[idx]
                attachment.title = item['title']
                attachment.content = item['content']
                attachment.is_required = True
                attachment.sort_order = idx
                if upload and upload.filename:
                    AssemblyService._replace_product_attachment_file(attachment, upload, 'assembly_sheet')
                if not attachment.file_path:
                    raise ValueError('装配单必须上传文件')
            else:
                if not upload or not upload.filename:
                    raise ValueError('新增装配单必须上传文件')
                file_path, file_type = AssemblyService._save_product_file(upload, product.id, 'assembly_sheet')
                db.session.add(
                    AssemblyProductAttachment(
                        product_id=product.id,
                        attach_type='assembly_sheet',
                        title=item['title'],
                        content=item['content'],
                        file_path=file_path,
                        file_type=file_type,
                        is_required=True,
                        sort_order=idx,
                    )
                )

        for redundant in existing_sheets[len(normalized_sheets):]:
            if redundant.file_path:
                AssemblyService._remove_product_file(product.id, redundant.file_path)
            db.session.delete(redundant)

        existing_remarks = AssemblyProductAttachment.query.filter_by(
            product_id=product.id,
            attach_type='remark',
        ).order_by(AssemblyProductAttachment.sort_order.asc(), AssemblyProductAttachment.id.asc()).all()

        normalized_remarks = []
        for item in remark_items or []:
            content = (item.get('content') or '').strip()
            is_required = bool(item.get('is_required'))
            upload = item.get('file')
            if content or is_required or (upload and upload.filename):
                normalized_remarks.append({'content': content, 'is_required': is_required, 'file': upload})

        for idx, item in enumerate(normalized_remarks):
            upload = item.get('file')
            if item['is_required'] and not item['content']:
                raise ValueError('必填备注必须填写文字内容')
            if idx < len(existing_remarks):
                remark = existing_remarks[idx]
                remark.content = item['content']
                remark.is_required = item['is_required']
                remark.sort_order = idx
                if upload and upload.filename:
                    AssemblyService._replace_product_attachment_file(remark, upload, 'remark')
            else:
                file_path = ''
                file_type = ''
                if upload and upload.filename:
                    file_path, file_type = AssemblyService._save_product_file(upload, product.id, 'remark')
                db.session.add(
                    AssemblyProductAttachment(
                        product_id=product.id,
                        attach_type='remark',
                        title=None,
                        content=item['content'],
                        file_path=file_path,
                        file_type=file_type,
                        is_required=item['is_required'],
                        sort_order=idx,
                    )
                )

        for redundant in existing_remarks[len(normalized_remarks):]:
            if redundant.file_path:
                AssemblyService._remove_product_file(product.id, redundant.file_path)
            db.session.delete(redundant)

        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return product

    @staticmethod
    def _serialize_product_attachment(attachment: AssemblyProductAttachment) -> dict:
        return {
            'title': attachment.display_title,
            'content': attachment.content or '',
            'filename': os.path.basename(attachment.file_path) if attachment.file_path else '',
            'url': attachment.file_url,
            'is_image': attachment.is_image,
            'is_required': bool(attachment.is_required),
        }

    @staticmethod
    def serialize_product_preview(product: AssemblyProduct) -> dict:
        return {
            'id': product.id,
            'product_code': product.product_code,
            'product_name': product.product_name,
            'creator_name': product.creator.real_name or product.creator.username,
            'components': [
                {
                    'id': component.id,
                    'workpiece_id': component.workpiece_id,
                    'workpiece_code': component.workpiece_code_snapshot,
                    'workpiece_name': component.workpiece_name_snapshot,
                    'quantity_per_unit': float(component.quantity_per_unit or 0),
                    'stock_quantity': float(component.workpiece.stock_quantity or 0) if component.workpiece else 0,
                }
                for component in product.components
            ],
            'assembly_sheets': [
                AssemblyService._serialize_product_attachment(attachment)
                for attachment in product.assembly_sheet_attachments
            ],
            'remarks': [
                AssemblyService._serialize_product_attachment(attachment)
                for attachment in product.remark_attachments
            ],
        }

    @staticmethod
    def delete_product(product_id: int, user: User) -> bool:
        product = AssemblyProduct.query.get(product_id)
        if not product:
            raise ValueError('产品不存在')
        if not AssemblyService.can_delete_product(user, product):
            raise ValueError('没有权限删除该产品')
        if product.orders:
            raise ValueError('该产品已被装配单引用，暂不可删除')
        for attachment in product.attachments:
            if attachment.file_path:
                AssemblyService._remove_product_file(product.id, attachment.file_path)
        db.session.delete(product)
        db.session.commit()
        return True

    @staticmethod
    def get_order(order_id: int, user: User) -> Optional[AssemblyOrder]:
        order = AssemblyOrder.query.get(order_id)
        if not order:
            return None
        return order if AssemblyService.can_view_order(user, order) else None

    @staticmethod
    def create_order(
        data: dict,
        controller_id: int,
        status: str = 'assembly_pending',
        allow_partial: bool = False,
        auto_commit: bool = True,
    ) -> AssemblyOrder:
        batch_no = (data.get('batch_no') or '').strip()
        quantity = data.get('quantity')
        product_id = data.get('product_id')
        product_name_snapshot = (data.get('product_name_snapshot') or '').strip()

        selected_product = None
        if product_id:
            selected_product = AssemblyProduct.query.get(int(product_id))
            if not selected_product:
                raise ValueError('请选择有效产品')
            product_name_snapshot = selected_product.product_name

        if allow_partial:
            if not batch_no:
                batch_no = f"DRAFT-A-{controller_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2)}"
            if not product_name_snapshot:
                product_name_snapshot = '未命名草稿'
            quantity = AssemblyService._to_float(quantity, 1.0)
            if quantity <= 0:
                quantity = 1.0
        else:
            if not batch_no:
                raise ValueError('批次编号不能为空')
            if not product_id:
                raise ValueError('请选择产品')
            if not product_name_snapshot:
                raise ValueError('产品名称不能为空')
            quantity = AssemblyService._to_float(quantity, 0.0)
            if quantity <= 0:
                raise ValueError('装配数量必须为正数')

        existing = AssemblyOrder.query.filter_by(batch_no=batch_no).first()
        if existing:
            raise ValueError(f"批次编号 '{batch_no}' 已存在")

        order = AssemblyOrder(
            batch_no=batch_no,
            product_id=selected_product.id if selected_product else None,
            product_name_snapshot=product_name_snapshot,
            quantity=quantity,
            controller_id=controller_id,
            status=status,
        )
        db.session.add(order)
        db.session.flush()
        controller = User.query.get(controller_id)
        AssemblyService.add_order_history(
            order,
            '创建装配单' if status != 'draft' else '保存装配单草稿',
            f'批次 {order.batch_no}，产品 {order.product_name_snapshot}，数量 {float(order.quantity or 0):g}',
            controller,
        )
        if auto_commit:
            db.session.commit()
        return order

    @staticmethod
    def update_order(
        order_id: int,
        data: dict,
        user: User,
        allow_partial: bool = False,
        auto_commit: bool = True,
    ) -> AssemblyOrder:
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if not AssemblyService.can_edit_order(user, order):
            raise ValueError('没有权限编辑此装配单')

        batch_no = (data.get('batch_no') or '').strip()
        quantity = data.get('quantity')
        product_id = data.get('product_id')
        product_name_snapshot = (data.get('product_name_snapshot') or '').strip()

        selected_product = None
        if product_id:
            selected_product = AssemblyProduct.query.get(int(product_id))
            if not selected_product:
                raise ValueError('请选择有效产品')
            product_name_snapshot = selected_product.product_name

        if allow_partial:
            batch_no = batch_no or order.batch_no
            product_name_snapshot = product_name_snapshot or order.product_name_snapshot
            quantity = AssemblyService._to_float(quantity, float(order.quantity or 1.0))
            if quantity <= 0:
                quantity = float(order.quantity or 1.0)
        else:
            if not batch_no:
                raise ValueError('批次编号不能为空')
            if not product_id:
                raise ValueError('请选择产品')
            if not product_name_snapshot:
                raise ValueError('产品名称不能为空')
            quantity = AssemblyService._to_float(quantity, 0.0)
            if quantity <= 0:
                raise ValueError('装配数量必须为正数')

        if batch_no != order.batch_no:
            existing = AssemblyOrder.query.filter_by(batch_no=batch_no).first()
            if existing:
                raise ValueError(f"批次编号 '{batch_no}' 已存在")

        order.batch_no = batch_no
        order.quantity = quantity
        if selected_product:
            order.product_id = selected_product.id
            order.product_name_snapshot = selected_product.product_name
        else:
            order.product_name_snapshot = product_name_snapshot

        AssemblyService.add_order_history(
            order,
            '编辑装配单',
            f'批次 {order.batch_no}，产品 {order.product_name_snapshot}，数量 {float(order.quantity or 0):g}',
            user,
        )
        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
            db.session.expire(order, ['components', 'attachments'])
        return order

    @staticmethod
    def _delete_inspection_report_files(order: AssemblyOrder) -> None:
        for record in order.inspection_records:
            if record.report_file_path:
                AssemblyService._remove_order_file(order.id, record.report_file_path)

    @staticmethod
    def _reset_order_snapshot(order: AssemblyOrder) -> None:
        AssemblyService._reverse_inventory_if_posted(order)
        AssemblyService._delete_inspection_report_files(order)
        for attachment in list(order.attachments):
            if attachment.file_path:
                AssemblyService._remove_order_file(order.id, attachment.file_path)
            db.session.delete(attachment)
        for component in list(order.components):
            db.session.delete(component)
        for record in list(order.inspection_records):
            db.session.delete(record)
        for signature in list(order.signatures):
            db.session.delete(signature)
        order.inspection_completed_at = None
        order.accepted_at = None
        order.rejected_at = None
        order.rejection_reason = None
        order.inventory_posted_at = None

    @staticmethod
    def apply_product_to_order(
        order_id: int,
        product_id: int,
        user: User,
        auto_commit: bool = True,
    ) -> AssemblyOrder:
        order = AssemblyOrder.query.get(order_id)
        product = AssemblyProduct.query.get(product_id)
        if not order or not product:
            raise ValueError('装配单或产品不存在')
        if not AssemblyService.can_edit_order(user, order):
            raise ValueError('没有权限同步该装配单')
        if not AssemblyService.can_access_product_library(user):
            raise ValueError('没有权限读取产品库')
        if len(product.components) < 2:
            raise ValueError('所选产品未完成装配结构配置')
        if not product.assembly_sheet_attachments:
            raise ValueError('所选产品未配置装配单')

        AssemblyService._reset_order_snapshot(order)
        order.product_id = product.id
        order.product_name_snapshot = product.product_name

        for component in product.components:
            total_required = float(component.quantity_per_unit or 0) * float(order.quantity or 0)
            db.session.add(
                AssemblyOrderComponent(
                    order_id=order.id,
                    workpiece_id=component.workpiece_id,
                    workpiece_code_snapshot=component.workpiece_code_snapshot,
                    workpiece_name_snapshot=component.workpiece_name_snapshot,
                    quantity_per_unit=float(component.quantity_per_unit or 0),
                    total_required_quantity=total_required,
                    sort_order=component.sort_order,
                )
            )

        for attachment in product.attachments:
            file_path = ''
            file_type = ''
            if attachment.file_path:
                file_path, file_type = AssemblyService._copy_product_file_to_order(
                    product_id=product.id,
                    order_id=order.id,
                    relative_path=attachment.file_path,
                    attach_type='assembly_record' if attachment.attach_type == 'assembly_sheet' else attachment.attach_type,
                )
            db.session.add(
                AssemblyOrderAttachment(
                    order_id=order.id,
                    attach_type='assembly_record' if attachment.attach_type == 'assembly_sheet' else attachment.attach_type,
                    source_type='product_snapshot',
                    title=attachment.display_title if attachment.attach_type == 'assembly_sheet' else attachment.title,
                    content=attachment.content,
                    file_path=file_path,
                    file_type=file_type,
                    is_required=attachment.is_required,
                    sort_order=attachment.sort_order,
                )
            )

        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
            db.session.expire(order, ['components', 'attachments'])
        return order

    @staticmethod
    def sync_order_section_files(
        order_id: int,
        registration_note_file,
        certificate_note_file,
        remark_note_file,
        user: User,
        auto_commit: bool = True,
    ) -> AssemblyOrder:
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if not AssemblyService.can_edit_order(user, order):
            raise ValueError('没有权限编辑此装配单')
        AssemblyService._replace_order_section_file(order, 'registration', registration_note_file)
        AssemblyService._replace_order_section_file(order, 'certificate', certificate_note_file)
        AssemblyService._replace_order_section_file(order, 'remark', remark_note_file)
        if auto_commit:
            db.session.commit()
        return order

    @staticmethod
    def _reserved_quantity_subquery(workpiece_id: int, exclude_order_id: int | None = None) -> float:
        query = db.session.query(func.coalesce(func.sum(AssemblyOrderComponent.total_required_quantity), 0.0)).join(
            AssemblyOrder,
            AssemblyOrder.id == AssemblyOrderComponent.order_id,
        ).filter(
            AssemblyOrderComponent.workpiece_id == workpiece_id,
            AssemblyOrder.status.in_(tuple(AssemblyService.RESERVED_STATUSES)),
            AssemblyOrder.inventory_posted_at.is_(None),
        )
        if exclude_order_id:
            query = query.filter(AssemblyOrder.id != exclude_order_id)
        return float(query.scalar() or 0.0)

    @staticmethod
    def compute_component_stock_requirements(order: AssemblyOrder, exclude_self: bool = False) -> list[dict]:
        requirements: list[dict] = []
        for component in order.components:
            if not component.workpiece_id or not component.workpiece:
                raise ValueError(f'工件 {component.workpiece_code_snapshot} 已不存在，请重新选择产品模板')
            reserved_by_others = AssemblyService._reserved_quantity_subquery(
                component.workpiece_id,
                exclude_order_id=order.id if exclude_self else None,
            )
            stock_quantity = float(component.workpiece.stock_quantity or 0)
            available_quantity = stock_quantity - reserved_by_others
            requirements.append(
                {
                    'component': component,
                    'stock_quantity': stock_quantity,
                    'reserved_quantity': reserved_by_others,
                    'available_quantity': available_quantity,
                    'required_quantity': float(component.total_required_quantity or 0),
                }
            )
        return requirements

    @staticmethod
    def ensure_stock_available(order: AssemblyOrder, exclude_self: bool = False) -> None:
        for item in AssemblyService.compute_component_stock_requirements(order, exclude_self=exclude_self):
            if item['available_quantity'] + 1e-9 < item['required_quantity']:
                component = item['component']
                raise ValueError(
                    f"工件 {component.workpiece_code_snapshot} / {component.workpiece_name_snapshot} 库存不足，"
                    f"当前可用 {item['available_quantity']:g}，本次需消耗 {item['required_quantity']:g}"
                )

    @staticmethod
    def submit_assembly(
        order_id: int,
        inspector_id: int,
        user: User,
        auto_commit: bool = True,
    ) -> AssemblyOrder:
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if not AssemblyService.can_edit_order(user, order):
            raise ValueError('没有权限执行此操作')
        if order.status not in ['draft', 'assembly_pending', 'rejected']:
            raise ValueError('当前装配单状态不允许完成装配发起')

        inspector = User.query.get(inspector_id)
        if not inspector or not inspector.is_active:
            raise ValueError('请选择有效的指导 / 验收人员')
        if inspector.ai_cats_effective_role_code != AssemblyService.INSPECTOR_ROLE_CODE and not inspector.ai_cats_is_manager:
            raise ValueError('请选择指导 / 验收人员角色用户')
        if not order.product_id or not order.components:
            raise ValueError('请先选择产品并生成装配结构快照')
        if not order.assembly_record_attachments:
            raise ValueError('请确认产品模板中已配置装配单')
        if order.quantity <= 0:
            raise ValueError('装配数量必须大于 0')

        for component in order.components:
            component.total_required_quantity = float(component.quantity_per_unit or 0) * float(order.quantity or 0)

        AssemblyService.ensure_stock_available(order, exclude_self=True)

        order.status = 'assembly_completed'
        order.inspector_id = inspector_id
        order.assembly_submitted_at = datetime.now()
        order.inspection_completed_at = None
        order.accepted_at = None
        order.rejected_at = None
        order.rejection_reason = None
        AssemblyService.add_order_history(
            order,
            '完成装配发起',
            f'已分配给 {inspector.real_name or inspector.username}，进入质量检测',
            user,
        )
        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return order

    @staticmethod
    def inspection_record_map(order: AssemblyOrder) -> dict[int, AssemblyInspectionRecord]:
        return {record.attachment_id: record for record in order.inspection_records}

    @staticmethod
    def submit_inspection(order_id: int, results: list[dict], user: User, final_submit: bool = True) -> AssemblyOrder:
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if not AssemblyService.can_inspect_order(user, order):
            raise ValueError('没有权限执行质量检测')
        if order.status not in ['assembly_completed', 'inspection_pending']:
            raise ValueError('当前装配单状态不允许提交质检')

        attachments = AssemblyOrderAttachment.query.filter_by(order_id=order.id).order_by(
            AssemblyOrderAttachment.sort_order.asc(),
            AssemblyOrderAttachment.id.asc(),
        ).all()
        attachment_ids = {attachment.id for attachment in attachments}
        existing_records = {
            record.attachment_id: record
            for record in AssemblyInspectionRecord.query.filter_by(order_id=order.id).all()
        }

        if final_submit and not results:
            raise ValueError('请填写质检结果')

        submitted_ids: list[int] = []
        for item in results:
            attachment_id = item.get('attachment_id')
            if attachment_id not in attachment_ids:
                raise ValueError('无效的附件 ID')
            submitted_ids.append(attachment_id)
        if len(submitted_ids) != len(set(submitted_ids)):
            raise ValueError('存在重复的附件质检结果，请重新提交')

        touched_records: dict[int, AssemblyInspectionRecord] = {}
        for item in results:
            attachment_id = item.get('attachment_id')
            attachment = next(attachment for attachment in attachments if attachment.id == attachment_id)
            result = (item.get('result') or '').strip()
            remark = (item.get('remark') or '').strip() or None
            report_file = item.get('report_file')
            record = existing_records.get(attachment_id)

            if not record:
                record = AssemblyInspectionRecord(
                    order_id=order.id,
                    inspector_id=user.id,
                    attachment_id=attachment_id,
                    result='draft',
                )
                db.session.add(record)

            if result:
                if result not in ['pass', 'fail', 'draft']:
                    raise ValueError('质检结果只能为通过、不通过或草稿')
                record.result = result
            elif not record.result:
                record.result = 'draft'

            record.inspector_id = user.id
            record.remark = remark

            if report_file and report_file.filename:
                old_report_path = record.report_file_path
                report_path, report_type = AssemblyService._save_order_file(report_file, order.id, 'report')
                record.report_file_path = report_path
                record.report_file_type = report_type
                record.report_original_name = report_file.filename
                if old_report_path and old_report_path != report_path:
                    AssemblyService._remove_order_file(order.id, old_report_path)

            touched_records[attachment_id] = record

        if final_submit:
            unresolved: list[str] = []
            has_fail = False

            for attachment in attachments:
                record = touched_records.get(attachment.id) or existing_records.get(attachment.id)
                if not record or record.result not in ['pass', 'fail']:
                    unresolved.append(attachment.display_title)
                    continue
                if attachment.requires_report and not record.report_file_path:
                    raise ValueError(f'{attachment.display_title} 必须上传合格报告后才能提交')
                if record.result == 'fail':
                    has_fail = True

            if unresolved:
                raise ValueError('请完成所有项目的勾选后再提交')

            order.accepted_at = None
            for signature in list(order.signatures):
                db.session.delete(signature)

            if has_fail:
                order.status = 'rejected'
                order.rejected_at = datetime.now()
                order.inspection_completed_at = None
                AssemblyService.add_order_history(
                    order,
                    '提交质量检测',
                    '质检不合格，退回发起装配流程',
                    user,
                )
            else:
                order.status = 'inspection_completed'
                order.inspection_completed_at = datetime.now()
                order.rejected_at = None
                order.rejection_reason = None
                AssemblyService.add_order_history(
                    order,
                    '提交质量检测',
                    '质检合格，进入验收/出厂',
                    user,
                )
        else:
            if touched_records or existing_records:
                order.status = 'inspection_pending'
                order.inspection_completed_at = None
                AssemblyService.add_order_history(
                    order,
                    '保存质检草稿',
                    f'已保存 {len(touched_records)} 项质检结果',
                    user,
                )

        db.session.commit()
        return order

    @staticmethod
    def _post_inventory_if_needed(order: AssemblyOrder, user: User | None = None) -> None:
        if order.inventory_posted_at or order.status != 'accepted':
            return
        for component in order.components:
            if not component.workpiece:
                raise ValueError(f'工件 {component.workpiece_code_snapshot} 已不存在，无法扣减库存')
            if float(component.workpiece.stock_quantity or 0) + 1e-9 < float(component.total_required_quantity or 0):
                raise ValueError(
                    f"工件 {component.workpiece_code_snapshot} / {component.workpiece_name_snapshot} 库存不足，"
                    f"当前库存 {float(component.workpiece.stock_quantity or 0):g}，需扣减 {float(component.total_required_quantity or 0):g}"
                )

        for component in order.components:
            component.workpiece.stock_quantity = float(component.workpiece.stock_quantity or 0) - float(component.total_required_quantity or 0)

        order.inventory_posted_at = datetime.now()
        AssemblyService.add_order_history(order, '工件库存扣减', f'已按 BOM 扣减 {len(order.components)} 项工件库存', user)

    @staticmethod
    def _reverse_inventory_if_posted(order: AssemblyOrder, user: User | None = None) -> None:
        if not order.inventory_posted_at:
            return
        for component in order.components:
            if component.workpiece:
                component.workpiece.stock_quantity = float(component.workpiece.stock_quantity or 0) + float(component.total_required_quantity or 0)
        order.inventory_posted_at = None
        AssemblyService.add_order_history(order, '工件库存恢复', '已撤销本装配单的库存扣减', user)

    @staticmethod
    def sign_acceptance(order_id: int, user: User, signer_role: Optional[str] = None) -> dict:
        """Sign one acceptance role for the current user."""
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if order.status != 'inspection_completed':
            raise ValueError('当前装配单尚未进入验收确认阶段')

        eligible_roles = AssemblyService.eligible_acceptance_signer_roles(user, order)
        if signer_role:
            signer_role = signer_role.strip()
            if signer_role not in ['qc_controller', 'qc_inspector']:
                raise ValueError('无效的确认角色')
            if signer_role not in eligible_roles:
                raise ValueError('没有权限执行该角色的验收确认')
        else:
            if not eligible_roles:
                raise ValueError('没有权限执行验收确认')
            if len(eligible_roles) != 1:
                raise ValueError('请指定确认角色')
            signer_role = eligible_roles[0]

        existing = AssemblyAcceptanceSignature.query.filter_by(
            order_id=order.id,
            signer_role=signer_role,
        ).first()
        if existing:
            raise ValueError('该角色已完成验收确认，无需重复操作')

        signature = AssemblyAcceptanceSignature(
            order_id=order.id,
            signer_id=user.id,
            signer_role=signer_role,
        )
        db.session.add(signature)
        db.session.flush()
        AssemblyService.add_order_history(
            order,
            '验收确认',
            f'{signature.signer_role_display}已确认',
            user,
        )

        signatures = AssemblyAcceptanceSignature.query.filter_by(order_id=order.id).all()
        roles_signed = {item.signer_role for item in signatures}
        if 'qc_controller' in roles_signed and 'qc_inspector' in roles_signed:
            order.status = 'accepted'
            order.accepted_at = datetime.now()
            AssemblyService._post_inventory_if_needed(order, user)
            AssemblyService.add_order_history(order, '验收完成', '双方确认完成，装配单最终验收通过', user)
            db.session.commit()
            return {'completed': True, 'message': '双方已确认，质检已完成'}

        db.session.commit()
        return {'completed': False, 'message': '验收确认已提交，等待另一方确认'}

    @staticmethod
    def cancel_acceptance_signature(order_id: int, signer_role: str, user: User) -> AssemblyOrder:
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if signer_role not in ['qc_controller', 'qc_inspector']:
            raise ValueError('无效的确认角色')
        if not AssemblyService.can_cancel_acceptance_signature(user, order, signer_role):
            raise ValueError('没有权限取消该验收确认')

        signature = AssemblyAcceptanceSignature.query.filter_by(
            order_id=order.id,
            signer_role=signer_role,
        ).first()
        if not signature:
            raise ValueError('该角色尚未完成验收确认')

        was_accepted = order.status == 'accepted'
        if was_accepted:
            AssemblyService._reverse_inventory_if_posted(order, user)
            order.status = 'inspection_completed'
            order.accepted_at = None

        role_display = signature.signer_role_display
        db.session.delete(signature)
        AssemblyService.add_order_history(
            order,
            '取消验收确认',
            f'{role_display}确认已取消',
            user,
        )
        db.session.commit()
        return order

    @staticmethod
    def rollback_acceptance(order_id: int, target: str, reason: str, user: User) -> AssemblyOrder:
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if not AssemblyService.can_rollback_order(user, order):
            raise ValueError('没有权限执行回退操作')
        if order.status not in ['inspection_completed', 'accepted']:
            raise ValueError('当前装配单状态不允许回退')
        if target not in ['assembly', 'inspection']:
            raise ValueError('无效的回退目标')
        if not reason or not reason.strip():
            raise ValueError('请填写回退原因')

        was_accepted = order.status == 'accepted'
        if was_accepted:
            AssemblyService._reverse_inventory_if_posted(order, user)

        AssemblyAcceptanceSignature.query.filter_by(order_id=order.id).delete()
        order.accepted_at = None

        if target == 'assembly':
            AssemblyService._delete_inspection_report_files(order)
            AssemblyInspectionRecord.query.filter_by(order_id=order.id).delete()
            order.status = 'assembly_pending'
            order.inspection_completed_at = None
        else:
            order.status = 'inspection_pending'
            order.inspection_completed_at = None

        order.rejection_reason = reason.strip()
        AssemblyService.add_order_history(
            order,
            '验收回退',
            f"回退至{'发起装配' if target == 'assembly' else '质量检测'}：{reason.strip()}",
            user,
        )
        db.session.commit()
        return order

    @staticmethod
    def delete_order(order_id: int, user: User) -> bool:
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if not AssemblyService.can_delete_order(user, order):
            raise ValueError('没有权限删除该装配单')
        AssemblyService._reverse_inventory_if_posted(order)
        AssemblyService._delete_inspection_report_files(order)
        AssemblyService._delete_order_section_files(order)
        for attachment in order.attachments:
            if attachment.file_path:
                AssemblyService._remove_order_file(order.id, attachment.file_path)
        db.session.delete(order)
        db.session.commit()
        return True
