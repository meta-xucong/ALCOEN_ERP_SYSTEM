from __future__ import annotations

import os
import re
import secrets
import shutil
import zipfile
from io import BytesIO
from datetime import datetime
from html import escape, unescape as html_unescape
from typing import Optional

from flask import current_app
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from app import db
from app.models import (
    ASSEMBLY_PRODUCT_LEVEL_DISPLAY,
    ASSEMBLY_STATUS_DISPLAY,
    AssemblyAcceptanceBatch,
    AssemblyAcceptanceSignature,
    AssemblyInspectionRecord,
    AssemblyOrder,
    AssemblyOrderAttachment,
    AssemblyOrderComponent,
    AssemblyOrderHistory,
    AssemblyOutboundBatch,
    AssemblyOutboundHistory,
    AssemblyOutboundOrder,
    AssemblyOutboundSignature,
    AssemblyProduct,
    AssemblyProductAttachment,
    AssemblyProductComponent,
    AssemblyProductStockHistory,
    QC_MANAGER_ROLE_CODES,
    QCWorkpiece,
    QCWorkpieceStockHistory,
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
    DOC_TEMPLATE_EXTENSIONS = {'docx'}
    PRODUCT_ATTACHMENT_TYPES = ('assembly_sheet', 'coa_template', 'remark')
    PRODUCT_LEVEL_CHOICES = (1, 2, 3)
    REQUIRED_PRODUCT_ATTACHMENT_TYPES = {'assembly_sheet'}
    RESERVED_STATUSES = {'assembly_pending', 'assembly_completed', 'inspection_pending', 'inspection_completed'}

    _ATTACH_SUBFOLDER_MAP = {
        'assembly_sheet': 'assembly_sheets',
        'coa_template': 'coa_templates',
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
    def _allowed_template_file(filename: str) -> bool:
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in AssemblyService.DOC_TEMPLATE_EXTENSIONS

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
        if attach_type == 'coa_template':
            if not AssemblyService._allowed_template_file(file.filename):
                raise ValueError('COA报告模板仅支持可拼接的 Word 模板（.docx）')
        elif not AssemblyService._allowed_file(file.filename):
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
        if user.has_ai_cats_identity('controller', 'assembly'):
            return query.filter(AssemblyProduct.creator_id == user.id)
        return query.filter(False)

    @staticmethod
    def _order_query_for_user(user: User):
        query = AssemblyOrder.query
        if user.is_superadmin or user.ai_cats_is_manager:
            return query
        if user.has_ai_cats_identity('controller', 'assembly'):
            return query.filter(AssemblyOrder.controller_id == user.id)
        if user.has_ai_cats_identity('supplier', 'assembly'):
            return query.filter(AssemblyOrder.inspector_id == user.id)
        return query.filter(False)

    @staticmethod
    def can_access_product_library(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return AssemblyService._has_any_permission(user, AssemblyService.PRODUCT_PERMISSION_CODES)
        if user.has_ai_cats_identity('controller', 'assembly'):
            return AssemblyService._has_any_permission(user, AssemblyService.PRODUCT_PERMISSION_CODES)
        return False

    @staticmethod
    def can_create_product(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_create')
        return user.has_ai_cats_identity('controller', 'assembly') and user.has_ai_cats_permission('qc_workpiece_create')

    @staticmethod
    def can_edit_product(user: User, product: AssemblyProduct) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_edit')
        return user.has_ai_cats_identity('controller', 'assembly') and product.creator_id == user.id and user.has_ai_cats_permission('qc_workpiece_edit')

    @staticmethod
    def can_delete_product(user: User, product: AssemblyProduct) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_delete')
        return user.has_ai_cats_identity('controller', 'assembly') and product.creator_id == user.id and user.has_ai_cats_permission('qc_workpiece_delete')

    @staticmethod
    def can_access_assembly_launch(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return AssemblyService._has_any_permission(user, AssemblyService.ORDER_PERMISSION_CODES)
        return user.has_ai_cats_identity('controller', 'assembly') and AssemblyService._has_any_permission(user, AssemblyService.ORDER_PERMISSION_CODES)

    @staticmethod
    def can_create_order(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_work_order_create')
        return user.has_ai_cats_identity('controller', 'assembly') and user.has_ai_cats_permission('qc_work_order_create')

    @staticmethod
    def can_edit_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if order.status not in ['draft', 'assembly_pending', 'rejected']:
            return False
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_work_order_edit')
        return user.has_ai_cats_identity('controller', 'assembly') and order.controller_id == user.id and user.has_ai_cats_permission('qc_work_order_edit')

    @staticmethod
    def can_delete_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_work_order_delete')
        return user.has_ai_cats_identity('controller', 'assembly') and order.controller_id == user.id and user.has_ai_cats_permission('qc_work_order_delete')

    @staticmethod
    def can_view_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return True
        if order.status == 'draft':
            return user.has_ai_cats_identity('controller', 'assembly') and order.controller_id == user.id and AssemblyService.can_access_assembly_launch(user)
        if user.has_ai_cats_identity('controller', 'assembly') and order.controller_id == user.id:
            return True
        if user.has_ai_cats_identity('supplier', 'assembly') and order.inspector_id == user.id:
            return True
        return False

    @staticmethod
    def can_access_inspection(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return AssemblyService._has_any_permission(user, AssemblyService.INSPECTION_PERMISSION_CODES)
        if user.has_ai_cats_identity('controller', 'assembly'):
            return user.has_ai_cats_permission('qc_inspection_view')
        if user.has_ai_cats_identity('supplier', 'assembly'):
            return AssemblyService._has_any_permission(user, AssemblyService.INSPECTION_PERMISSION_CODES)
        return False

    @staticmethod
    def can_inspect_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_inspection_perform'):
            return order.status in ['assembly_completed', 'inspection_pending']
        if user.has_ai_cats_identity('supplier', 'assembly') and order.inspector_id == user.id:
            return user.has_ai_cats_permission('qc_inspection_perform') and order.status in ['assembly_completed', 'inspection_pending']
        return False

    @staticmethod
    def can_access_acceptance(user: User) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return AssemblyService._has_any_permission(user, AssemblyService.ACCEPTANCE_PERMISSION_CODES)
        if user.has_ai_cats_identity('controller', 'assembly'):
            return AssemblyService._has_any_permission(user, AssemblyService.ACCEPTANCE_PERMISSION_CODES)
        if user.has_ai_cats_identity('supplier', 'assembly'):
            return user.has_ai_cats_permission('qc_acceptance_perform')
        return False

    @staticmethod
    def can_access_outbound(user: User) -> bool:
        """Return whether the user can access outbound shipping."""
        if not user or not user.is_active:
            return False
        return bool(
            user.ai_cats_is_manager
            or user.has_ai_cats_identity('controller', 'assembly')
        )

    @staticmethod
    def can_create_outbound(user: User) -> bool:
        return AssemblyService.can_access_outbound(user)

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
        if user.has_ai_cats_identity('controller', 'assembly') and order.controller_id == user.id:
            if user.has_ai_cats_permission('qc_acceptance_perform'):
                signer_roles.append('qc_controller')
        if user.has_ai_cats_identity('supplier', 'assembly') and order.inspector_id == user.id:
            if user.has_ai_cats_permission('qc_acceptance_perform'):
                signer_roles.append('qc_inspector')
        return signer_roles

    @staticmethod
    def can_rollback_order(user: User, order: AssemblyOrder) -> bool:
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_rollback'):
            return order.status in ['inspection_completed', 'accepted']
        if user.has_ai_cats_identity('controller', 'assembly') and order.controller_id == user.id:
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
        if signer_role == 'qc_controller' and user.has_ai_cats_identity('controller', 'assembly') and order.controller_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_perform')
        if signer_role == 'qc_inspector' and user.has_ai_cats_identity('supplier', 'assembly') and order.inspector_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_perform')
        return False

    @staticmethod
    def get_product_list(user: User, keyword: str = None, page: int = 1, product_level: int = 1):
        query = AssemblyService._product_query_for_user(user)
        query = query.filter(AssemblyProduct.product_level == AssemblyService.normalize_product_level(product_level))
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
        return AssemblyProduct.query.order_by(AssemblyProduct.product_level.asc(), AssemblyProduct.product_code.asc(), AssemblyProduct.id.asc()).all()

    @staticmethod
    def normalize_product_level(value) -> int:
        level = int(AssemblyService._to_float(value, 1))
        return level if level in AssemblyService.PRODUCT_LEVEL_CHOICES else 1

    @staticmethod
    def product_level_display(level: int) -> str:
        return ASSEMBLY_PRODUCT_LEVEL_DISPLAY.get(AssemblyService.normalize_product_level(level), '一级产品库')

    @staticmethod
    def allowed_component_products(product_level: int, exclude_product_id: int | None = None) -> list[AssemblyProduct]:
        allowed_levels = [level for level in AssemblyService.PRODUCT_LEVEL_CHOICES if level < AssemblyService.normalize_product_level(product_level)]
        if not allowed_levels:
            return []
        query = AssemblyProduct.query.filter(AssemblyProduct.product_level.in_(allowed_levels))
        if exclude_product_id:
            query = query.filter(AssemblyProduct.id != exclude_product_id)
        return query.order_by(AssemblyProduct.product_level.asc(), AssemblyProduct.product_code.asc(), AssemblyProduct.id.asc()).all()

    @staticmethod
    def get_component_choices(user: User, product_level: int = 1, exclude_product_id: int | None = None) -> dict:
        if not AssemblyService.can_access_product_library(user):
            return {'workpieces': [], 'products': []}
        return {
            'workpieces': AssemblyService.get_workpiece_choices(user),
            'products': AssemblyService.allowed_component_products(product_level, exclude_product_id=exclude_product_id),
        }

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
        if user.has_ai_cats_identity('controller', 'assembly') and product.creator_id == user.id:
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
    def search_components(user: User, keyword: str, product_level: int = 1, limit: int = 10) -> list[dict]:
        if not keyword or not AssemblyService.can_access_product_library(user):
            return []
        like_keyword = f'%{keyword.strip()}%'
        items: list[dict] = []
        for workpiece in QCWorkpiece.query.filter(
            or_(QCWorkpiece.workpiece_code.ilike(like_keyword), QCWorkpiece.workpiece_name.ilike(like_keyword))
        ).order_by(QCWorkpiece.workpiece_code.asc(), QCWorkpiece.id.asc()).limit(limit).all():
            items.append({
                'type': 'workpiece',
                'id': workpiece.id,
                'code': workpiece.workpiece_code,
                'name': workpiece.workpiece_name,
                'type_display': '工件库',
                'stock_quantity': float(workpiece.stock_quantity or 0),
            })
        remaining = max(0, limit - len(items))
        if remaining:
            allowed_levels = [level for level in AssemblyService.PRODUCT_LEVEL_CHOICES if level < AssemblyService.normalize_product_level(product_level)]
            if allowed_levels:
                products = AssemblyProduct.query.filter(
                    AssemblyProduct.product_level.in_(allowed_levels),
                    or_(AssemblyProduct.product_code.ilike(like_keyword), AssemblyProduct.product_name.ilike(like_keyword)),
                ).order_by(AssemblyProduct.product_level.asc(), AssemblyProduct.product_code.asc(), AssemblyProduct.id.asc()).limit(remaining).all()
                for product in products:
                    items.append({
                        'type': 'product',
                        'id': product.id,
                        'code': product.product_code,
                        'name': product.product_name,
                        'type_display': product.product_level_display,
                        'stock_quantity': float(product.stock_quantity or 0),
                    })
        return items

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
            elif user.has_ai_cats_identity('supplier', 'assembly') and AssemblyService.can_access_inspection(user):
                query = query.filter(AssemblyOrder.inspector_id == user.id)
            elif user.has_ai_cats_identity('controller', 'assembly') and AssemblyService.can_access_inspection(user):
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
            elif user.has_ai_cats_identity('controller', 'assembly') and AssemblyService.can_access_acceptance(user):
                query = query.filter(AssemblyOrder.controller_id == user.id)
            elif user.has_ai_cats_identity('supplier', 'assembly') and AssemblyService.can_access_acceptance(user):
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
    def get_outbound_list(user: User, keyword: str = None, page: int = 1):
        query = AssemblyOutboundOrder.query
        if not AssemblyService.can_access_outbound(user):
            query = query.filter(False)
        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(
                or_(
                    AssemblyOutboundOrder.outbound_no.ilike(like_keyword),
                    AssemblyOutboundOrder.item_code_snapshot.ilike(like_keyword),
                    AssemblyOutboundOrder.item_name_snapshot.ilike(like_keyword),
                )
            )
        query = query.order_by(AssemblyOutboundOrder.created_at.desc(), AssemblyOutboundOrder.id.desc())
        return query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_outbound_order(order_id: int, user: User) -> Optional[AssemblyOutboundOrder]:
        order = AssemblyOutboundOrder.query.get(order_id)
        if not order or not AssemblyService.can_access_outbound(user):
            return None
        return order

    @staticmethod
    def get_outbound_item_choices(user: User) -> list[dict]:
        if not AssemblyService.can_access_outbound(user):
            return []
        items: list[dict] = []
        for workpiece in QCWorkpiece.query.order_by(QCWorkpiece.workpiece_code.asc(), QCWorkpiece.id.asc()).all():
            items.append({
                'type': 'workpiece',
                'id': workpiece.id,
                'code': workpiece.workpiece_code,
                'name': workpiece.workpiece_name,
                'type_display': '工件库',
                'stock_quantity': float(workpiece.stock_quantity or 0),
            })
        for product in AssemblyProduct.query.order_by(
            AssemblyProduct.product_level.asc(),
            AssemblyProduct.product_code.asc(),
            AssemblyProduct.id.asc(),
        ).all():
            items.append({
                'type': 'product',
                'id': product.id,
                'code': product.product_code,
                'name': product.product_name,
                'type_display': product.product_level_display,
                'stock_quantity': float(product.stock_quantity or 0),
            })
        return items

    @staticmethod
    def search_outbound_items(user: User, keyword: str, limit: int = 12) -> list[dict]:
        if not keyword or not AssemblyService.can_access_outbound(user):
            return []
        like_keyword = f'%{keyword.strip()}%'
        items: list[dict] = []
        for workpiece in QCWorkpiece.query.filter(
            or_(QCWorkpiece.workpiece_code.ilike(like_keyword), QCWorkpiece.workpiece_name.ilike(like_keyword))
        ).order_by(QCWorkpiece.workpiece_code.asc(), QCWorkpiece.id.asc()).limit(limit).all():
            items.append({
                'type': 'workpiece',
                'id': workpiece.id,
                'code': workpiece.workpiece_code,
                'name': workpiece.workpiece_name,
                'type_display': '工件库',
                'stock_quantity': float(workpiece.stock_quantity or 0),
            })
        remaining = max(0, limit - len(items))
        if remaining:
            for product in AssemblyProduct.query.filter(
                or_(AssemblyProduct.product_code.ilike(like_keyword), AssemblyProduct.product_name.ilike(like_keyword))
            ).order_by(AssemblyProduct.product_level.asc(), AssemblyProduct.product_code.asc(), AssemblyProduct.id.asc()).limit(remaining).all():
                items.append({
                    'type': 'product',
                    'id': product.id,
                    'code': product.product_code,
                    'name': product.product_name,
                    'type_display': product.product_level_display,
                    'stock_quantity': float(product.stock_quantity or 0),
                })
        return items

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
        product_level = AssemblyService.normalize_product_level(data.get('product_level'))

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
            product_level=product_level,
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
        product_level = AssemblyService.normalize_product_level(data.get('product_level', product.product_level))
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
        product.product_level = product_level
        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return product

    @staticmethod
    def _component_identity(item: dict) -> tuple[str, int | None]:
        component_type = (item.get('component_type') or 'workpiece').strip()
        if component_type not in ['workpiece', 'product']:
            component_type = 'workpiece'
        if component_type == 'product':
            component_id = item.get('component_product_id') or item.get('item_id')
        else:
            component_id = item.get('workpiece_id') or item.get('item_id')
        try:
            return component_type, int(component_id) if component_id else None
        except (TypeError, ValueError):
            return component_type, None

    @staticmethod
    def _component_snapshot(component_type: str, component_id: int) -> dict:
        if component_type == 'product':
            product = AssemblyProduct.query.get(component_id)
            if not product:
                raise ValueError('请选择有效产品组件')
            return {
                'component_type': 'product',
                'component_product_id': product.id,
                'workpiece_id': None,
                'code': product.product_code,
                'name': product.product_name,
                'level': int(product.product_level or 1),
            }
        workpiece = QCWorkpiece.query.get(component_id)
        if not workpiece:
            raise ValueError('请选择有效工件')
        return {
            'component_type': 'workpiece',
            'component_product_id': None,
            'workpiece_id': workpiece.id,
            'code': workpiece.workpiece_code,
            'name': workpiece.workpiece_name,
            'level': 0,
        }

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
        product_level = AssemblyService.normalize_product_level(product.product_level)
        for idx, item in enumerate(components or []):
            component_type, component_id = AssemblyService._component_identity(item)
            quantity_per_unit = AssemblyService._to_float(item.get('quantity_per_unit'), 0.0)
            if not component_id or quantity_per_unit <= 0:
                continue
            snapshot = AssemblyService._component_snapshot(component_type, component_id)
            if snapshot['component_type'] == 'product':
                if snapshot['component_product_id'] == product.id:
                    raise ValueError('产品不能选择自身作为配件')
                if snapshot['level'] >= product_level:
                    raise ValueError(f'{product.product_level_display} 只能选择更低层级的产品作为组件')
            normalized.append({**snapshot, 'quantity_per_unit': quantity_per_unit, 'sort_order': idx})

        if len(normalized) < 2:
            raise ValueError('装配结构至少需要保留两个配件')

        seen_keys: set[tuple[str, int]] = set()
        for item in normalized:
            key = (item['component_type'], item['component_product_id'] or item['workpiece_id'])
            if key in seen_keys:
                raise ValueError('装配结构中不能重复选择同一配件')
            seen_keys.add(key)

        existing_components = AssemblyProductComponent.query.filter_by(product_id=product.id).order_by(
            AssemblyProductComponent.sort_order.asc(),
            AssemblyProductComponent.id.asc(),
        ).all()

        for idx, item in enumerate(normalized):
            if idx < len(existing_components):
                component = existing_components[idx]
                component.component_type = item['component_type']
                component.workpiece_id = item['workpiece_id']
                component.component_product_id = item['component_product_id']
                component.workpiece_code_snapshot = item['code']
                component.workpiece_name_snapshot = item['name']
                component.quantity_per_unit = item['quantity_per_unit']
                component.sort_order = idx
            else:
                db.session.add(
                    AssemblyProductComponent(
                        product_id=product.id,
                        component_type=item['component_type'],
                        workpiece_id=item['workpiece_id'],
                        component_product_id=item['component_product_id'],
                        workpiece_code_snapshot=item['code'],
                        workpiece_name_snapshot=item['name'],
                        quantity_per_unit=item['quantity_per_unit'],
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
        coa_template_file=None,
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

        existing_coa_templates = AssemblyProductAttachment.query.filter_by(
            product_id=product.id,
            attach_type='coa_template',
        ).order_by(AssemblyProductAttachment.sort_order.asc(), AssemblyProductAttachment.id.asc()).all()
        if coa_template_file and coa_template_file.filename:
            if existing_coa_templates:
                template = existing_coa_templates[0]
                template.title = 'COA报告模板'
                template.content = ''
                template.is_required = False
                template.sort_order = 0
                AssemblyService._replace_product_attachment_file(template, coa_template_file, 'coa_template')
                for redundant in existing_coa_templates[1:]:
                    if redundant.file_path:
                        AssemblyService._remove_product_file(product.id, redundant.file_path)
                    db.session.delete(redundant)
            else:
                file_path, file_type = AssemblyService._save_product_file(coa_template_file, product.id, 'coa_template')
                db.session.add(
                    AssemblyProductAttachment(
                        product_id=product.id,
                        attach_type='coa_template',
                        title='COA报告模板',
                        content='',
                        file_path=file_path,
                        file_type=file_type,
                        is_required=False,
                        sort_order=0,
                    )
                )
        elif len(existing_coa_templates) > 1:
            for redundant in existing_coa_templates[1:]:
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
            'stock_quantity': float(product.stock_quantity or 0),
            'product_level': int(product.product_level or 1),
            'product_level_display': product.product_level_display,
            'creator_name': product.creator.real_name or product.creator.username,
            'components': [
                {
                    'id': component.id,
                    'component_type': component.component_type or 'workpiece',
                    'component_id': component.component_product_id if component.component_type == 'product' else component.workpiece_id,
                    'workpiece_id': component.workpiece_id,
                    'component_product_id': component.component_product_id,
                    'workpiece_code': component.workpiece_code_snapshot,
                    'workpiece_name': component.workpiece_name_snapshot,
                    'type_display': component.component_type_display,
                    'quantity_per_unit': float(component.quantity_per_unit or 0),
                    'stock_quantity': component.component_stock_quantity,
                }
                for component in product.components
            ],
            'assembly_sheets': [
                AssemblyService._serialize_product_attachment(attachment)
                for attachment in product.assembly_sheet_attachments
            ],
            'coa_templates': [
                AssemblyService._serialize_product_attachment(attachment)
                for attachment in product.coa_template_attachments
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
                    component_type=component.component_type or 'workpiece',
                    workpiece_id=component.workpiece_id,
                    component_product_id=component.component_product_id,
                    workpiece_code_snapshot=component.workpiece_code_snapshot,
                    workpiece_name_snapshot=component.workpiece_name_snapshot,
                    quantity_per_unit=float(component.quantity_per_unit or 0),
                    total_required_quantity=total_required,
                    sort_order=component.sort_order,
                )
            )

        for attachment in product.attachments:
            if attachment.attach_type == 'coa_template':
                continue
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
    def _component_inventory_item(component):
        if (component.component_type or 'workpiece') == 'product':
            return component.component_product
        return component.workpiece

    @staticmethod
    def _component_inventory_label(component) -> str:
        return f"{component.workpiece_code_snapshot} / {component.workpiece_name_snapshot}"

    @staticmethod
    def _reserved_quantity_subquery(component_type: str, item_id: int, exclude_order_id: int | None = None) -> float:
        query = db.session.query(func.coalesce(func.sum(AssemblyOrderComponent.total_required_quantity), 0.0)).join(
            AssemblyOrder,
            AssemblyOrder.id == AssemblyOrderComponent.order_id,
        ).filter(
            AssemblyOrderComponent.component_type == component_type,
            AssemblyOrder.status.in_(tuple(AssemblyService.RESERVED_STATUSES)),
            AssemblyOrder.inventory_posted_at.is_(None),
        )
        if component_type == 'product':
            query = query.filter(AssemblyOrderComponent.component_product_id == item_id)
        else:
            query = query.filter(AssemblyOrderComponent.workpiece_id == item_id)
        if exclude_order_id:
            query = query.filter(AssemblyOrder.id != exclude_order_id)
        return float(query.scalar() or 0.0)

    @staticmethod
    def compute_component_stock_requirements(order: AssemblyOrder, exclude_self: bool = False) -> list[dict]:
        requirements: list[dict] = []
        for component in order.components:
            component_type = component.component_type or 'workpiece'
            item = AssemblyService._component_inventory_item(component)
            item_id = component.component_product_id if component_type == 'product' else component.workpiece_id
            if not item_id or not item:
                raise ValueError(f'配件 {component.workpiece_code_snapshot} 已不存在，请重新选择产品模板')
            reserved_by_others = AssemblyService._reserved_quantity_subquery(
                component_type,
                item_id,
                exclude_order_id=order.id if exclude_self else None,
            )
            stock_quantity = float(item.stock_quantity or 0)
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
                    f"配件 {AssemblyService._component_inventory_label(component)} 库存不足，"
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
            raise ValueError('请选择有效的供应商')
        if not inspector.has_ai_cats_identity('supplier', 'assembly'):
            raise ValueError('请选择具有装配/出厂权限的供应商')
        if inspector.id == order.controller_id:
            raise ValueError('质量控制人与供应商必须由不同用户担任')
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
                    report_label = (attachment.report_label or '合格报告').replace('（必选）', '')
                    raise ValueError(f'{attachment.display_title} 必须上传{report_label}后才能提交')
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
                    '质检合格，进入验收',
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
    def add_outbound_history(
        order: AssemblyOutboundOrder,
        action: str,
        detail: str | None = None,
        user: User | None = None,
    ) -> AssemblyOutboundHistory:
        history = AssemblyOutboundHistory(
            outbound_order_id=order.id,
            operator_id=user.id if user else None,
            action=action,
            detail=detail,
        )
        db.session.add(history)
        return history

    @staticmethod
    def _batch_sequence(batches, batch) -> int:
        """Return the 1-based sequence of a batch within its own order."""
        ordered = sorted(
            list(batches or []),
            key=lambda item: (item.created_at or datetime.min, item.id or 0),
        )
        for index, item in enumerate(ordered, 1):
            if item is batch or (batch.id is not None and item.id == batch.id):
                return index
        return len(ordered) + 1

    @staticmethod
    def _add_product_stock_history(
        product: AssemblyProduct,
        *,
        change_type: str,
        batch_no: str | None,
        quantity_delta: float,
        stock_before: float,
        stock_after: float,
        user: User | None = None,
        assembly_order: AssemblyOrder | None = None,
        acceptance_batch: AssemblyAcceptanceBatch | None = None,
        outbound_order: AssemblyOutboundOrder | None = None,
        outbound_batch: AssemblyOutboundBatch | None = None,
        production_quantity: float | None = None,
        accepted_quantity: float | None = None,
        note: str | None = None,
    ) -> AssemblyProductStockHistory:
        history = AssemblyProductStockHistory(
            product_id=product.id,
            assembly_order_id=assembly_order.id if assembly_order else None,
            assembly_acceptance_batch_id=acceptance_batch.id if acceptance_batch else None,
            outbound_order_id=outbound_order.id if outbound_order else None,
            outbound_batch_id=outbound_batch.id if outbound_batch else None,
            operator_id=user.id if user else None,
            change_type=change_type,
            batch_no=batch_no,
            production_quantity=production_quantity,
            accepted_quantity=accepted_quantity,
            quantity_delta=quantity_delta,
            stock_before=stock_before,
            stock_after=stock_after,
            note=note,
        )
        db.session.add(history)
        return history

    @staticmethod
    def _add_workpiece_stock_history(
        workpiece: QCWorkpiece,
        *,
        change_type: str,
        batch_no: str | None,
        quantity_delta: float,
        stock_before: float,
        stock_after: float,
        user: User | None = None,
        assembly_order: AssemblyOrder | None = None,
        acceptance_batch: AssemblyAcceptanceBatch | None = None,
        outbound_order: AssemblyOutboundOrder | None = None,
        outbound_batch: AssemblyOutboundBatch | None = None,
        production_quantity: float | None = None,
        accepted_quantity: float | None = None,
        note: str | None = None,
    ) -> QCWorkpieceStockHistory:
        history = QCWorkpieceStockHistory(
            workpiece_id=workpiece.id,
            assembly_order_id=assembly_order.id if assembly_order else None,
            assembly_acceptance_batch_id=acceptance_batch.id if acceptance_batch else None,
            outbound_order_id=outbound_order.id if outbound_order else None,
            outbound_batch_id=outbound_batch.id if outbound_batch else None,
            operator_id=user.id if user else None,
            change_type=change_type,
            batch_no=batch_no,
            production_quantity=production_quantity,
            accepted_quantity=accepted_quantity,
            quantity_delta=quantity_delta,
            stock_before=stock_before,
            stock_after=stock_after,
            note=note,
        )
        db.session.add(history)
        return history

    @staticmethod
    def _parse_date(value):
        if not value:
            return None
        if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
            return value
        try:
            return datetime.strptime(str(value), '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('出厂日期格式不正确')

    @staticmethod
    def _resolve_outbound_item(item_type: str, item_id) -> tuple[str, QCWorkpiece | AssemblyProduct]:
        normalized_type = (item_type or '').strip()
        if normalized_type not in ['workpiece', 'product']:
            raise ValueError('请选择有效的出厂产品/工件')
        try:
            normalized_id = int(item_id)
        except (TypeError, ValueError):
            raise ValueError('请选择有效的出厂产品/工件')
        if normalized_type == 'product':
            item = AssemblyProduct.query.get(normalized_id)
            if not item:
                raise ValueError('请选择有效产品')
            return normalized_type, item
        item = QCWorkpiece.query.get(normalized_id)
        if not item:
            raise ValueError('请选择有效工件')
        return normalized_type, item

    @staticmethod
    def create_outbound_order(data: dict, initiator: User, auto_commit: bool = True) -> AssemblyOutboundOrder:
        if not AssemblyService.can_create_outbound(initiator):
            raise ValueError('没有权限发起出厂')
        outbound_no = (data.get('outbound_no') or '').strip()
        planned_quantity = AssemblyService._to_float(data.get('planned_quantity'), 0.0)
        if not outbound_no:
            raise ValueError('出厂批次不能为空')
        if planned_quantity <= 0:
            raise ValueError('计划出厂总数量必须大于 0')
        if AssemblyOutboundOrder.query.filter_by(outbound_no=outbound_no).first():
            raise ValueError(f"出厂批次 '{outbound_no}' 已存在")

        item_type, item = AssemblyService._resolve_outbound_item(data.get('item_type'), data.get('item_id'))
        order = AssemblyOutboundOrder(
            outbound_no=outbound_no,
            item_type=item_type,
            workpiece_id=item.id if item_type == 'workpiece' else None,
            product_id=item.id if item_type == 'product' else None,
            item_code_snapshot=item.workpiece_code if item_type == 'workpiece' else item.product_code,
            item_name_snapshot=item.workpiece_name if item_type == 'workpiece' else item.product_name,
            planned_quantity=planned_quantity,
            outbound_date=AssemblyService._parse_date(data.get('outbound_date')),
            initiator_id=initiator.id,
            status='confirming',
        )
        db.session.add(order)
        db.session.flush()
        AssemblyService.add_outbound_history(
            order,
            '创建出厂订单',
            f'批次 {order.outbound_no}，对象 {order.item_display_name}，计划出厂 {planned_quantity:g}',
            initiator,
        )
        if auto_commit:
            db.session.commit()
        return order

    @staticmethod
    def start_outbound_batch(order_id: int, user: User) -> AssemblyOutboundBatch:
        order = AssemblyOutboundOrder.query.get(order_id)
        if not order:
            raise ValueError('出厂订单不存在')
        if not AssemblyService.can_access_outbound(user):
            raise ValueError('没有权限发起出厂批次')
        if order.status == 'completed':
            raise ValueError('该出厂订单已完成并锁定')
        if order.remaining_quantity <= 1e-9:
            raise ValueError('该出厂订单已无剩余数量')
        if order.active_batch:
            raise ValueError('当前已有未完成的出厂批次，请先完成该批次确认')
        batch = AssemblyOutboundBatch(order_id=order.id, outbound_quantity=0)
        db.session.add(batch)
        db.session.flush()
        batch_no = AssemblyService._batch_sequence(order.batches, batch)
        AssemblyService.add_outbound_history(
            order,
            '发起出厂批次',
            f'发起第 {batch_no} 个出厂批次，等待填写数量并双方确认',
            user,
        )
        db.session.commit()
        return batch

    @staticmethod
    def eligible_outbound_signer_roles(user: User, order: AssemblyOutboundOrder) -> list[str]:
        """Return the one outbound role this user may sign as.

        The initiator and approver must always be different people, including
        when a manager has full module permissions.
        """
        if order.status != 'confirming' or not AssemblyService.can_access_outbound(user):
            return []
        if user.id == order.initiator_id:
            return ['initiator']
        return ['approver']

    @staticmethod
    def _validate_outbound_quantity(order: AssemblyOutboundOrder, outbound_quantity) -> float:
        quantity = AssemblyService._to_float(outbound_quantity, 0.0)
        if quantity <= 0:
            raise ValueError('出厂数量必须大于 0')
        remaining = order.remaining_quantity
        if quantity > remaining + 1e-9:
            raise ValueError(f'出厂数量不能超过剩余数量 {remaining:g}')
        item = order.inventory_item
        if not item:
            raise ValueError('对应库存对象已不存在，无法出厂')
        if float(item.stock_quantity or 0) + 1e-9 < quantity:
            raise ValueError(f'库存不足，当前库存 {float(item.stock_quantity or 0):g}，本批需出厂 {quantity:g}')
        return quantity

    @staticmethod
    def _ensure_outbound_batch(order: AssemblyOutboundOrder, outbound_quantity) -> AssemblyOutboundBatch:
        batch = order.active_batch
        if batch:
            if not batch.signatures:
                quantity = AssemblyService._validate_outbound_quantity(order, outbound_quantity)
                batch.outbound_quantity = quantity
                batch.updated_at = datetime.now()
                AssemblyService.add_outbound_history(order, '填写出厂数量', f'本批出厂数量 {quantity:g}')
            elif float(batch.outbound_quantity or 0) <= 0:
                raise ValueError('当前出厂批次缺少出厂数量')
            return batch
        quantity = AssemblyService._validate_outbound_quantity(order, outbound_quantity)
        batch = AssemblyOutboundBatch(order_id=order.id, outbound_quantity=quantity)
        db.session.add(batch)
        db.session.flush()
        AssemblyService.add_outbound_history(order, '创建出厂批次', f'本批出厂数量 {quantity:g}')
        return batch

    @staticmethod
    def _post_outbound_batch_inventory(batch: AssemblyOutboundBatch, user: User | None = None) -> None:
        if batch.inventory_posted_at:
            return
        order = batch.order
        quantity = float(batch.outbound_quantity or 0)
        if quantity <= 0:
            batch.inventory_posted_at = datetime.now()
            return
        item = order.inventory_item
        if not item:
            raise ValueError('对应库存对象已不存在，无法扣减库存')
        stock_before = float(item.stock_quantity or 0)
        if stock_before + 1e-9 < quantity:
            raise ValueError(f'库存不足，当前库存 {stock_before:g}，本批需出厂 {quantity:g}')
        item.stock_quantity = stock_before - quantity
        batch.inventory_posted_at = datetime.now()
        batch_no = AssemblyService._batch_sequence(order.batches, batch)
        if order.item_type == 'workpiece' and order.workpiece_id:
            AssemblyService._add_workpiece_stock_history(
                item,
                change_type='outbound_out',
                batch_no=order.outbound_no,
                production_quantity=quantity,
                accepted_quantity=quantity,
                quantity_delta=-quantity,
                stock_before=stock_before,
                stock_after=float(item.stock_quantity or 0),
                outbound_order=order,
                outbound_batch=batch,
                user=user,
                note=f'出厂批次 #{batch_no} 已完成，扣减库存 {quantity:g}',
            )
        elif order.item_type == 'product' and order.product_id:
            AssemblyService._add_product_stock_history(
                item,
                change_type='outbound_out',
                batch_no=order.outbound_no,
                production_quantity=quantity,
                accepted_quantity=quantity,
                quantity_delta=-quantity,
                stock_before=stock_before,
                stock_after=float(item.stock_quantity or 0),
                outbound_order=order,
                outbound_batch=batch,
                user=user,
                note=f'出厂批次 #{batch_no} 已完成，扣减库存 {quantity:g}',
            )
        AssemblyService.add_outbound_history(
            order,
            '出厂扣减库存',
            f'出厂批次 #{batch_no} 数量 {quantity:g} 已扣减库存，当前库存 {float(item.stock_quantity or 0):g}',
            user,
        )

    @staticmethod
    def sign_outbound_batch(
        order_id: int,
        user: User,
        signer_role: Optional[str] = None,
        outbound_quantity=None,
    ) -> dict:
        order = AssemblyOutboundOrder.query.get(order_id)
        if not order:
            raise ValueError('出厂订单不存在')
        if order.status == 'completed':
            raise ValueError('该出厂订单已完成并锁定')

        eligible_roles = AssemblyService.eligible_outbound_signer_roles(user, order)
        if signer_role:
            signer_role = signer_role.strip()
            if signer_role not in ['initiator', 'approver']:
                raise ValueError('无效的确认角色')
            if signer_role not in eligible_roles:
                raise ValueError('没有权限执行该角色的出厂确认')
        else:
            if len(eligible_roles) != 1:
                raise ValueError('请指定确认角色')
            signer_role = eligible_roles[0]

        batch = AssemblyService._ensure_outbound_batch(order, outbound_quantity)
        existing = AssemblyOutboundSignature.query.filter_by(
            outbound_order_id=order.id,
            outbound_batch_id=batch.id,
            signer_role=signer_role,
        ).first()
        if existing:
            raise ValueError('该角色已完成出厂确认，无需重复操作')

        signature = AssemblyOutboundSignature(
            outbound_order_id=order.id,
            outbound_batch_id=batch.id,
            signer_id=user.id,
            signer_role=signer_role,
        )
        db.session.add(signature)
        db.session.flush()
        AssemblyService.add_outbound_history(order, '出厂确认', f'{signature.signer_role_display}已确认', user)

        roles_signed = {
            item.signer_role
            for item in AssemblyOutboundSignature.query.filter_by(outbound_batch_id=batch.id).all()
        }
        if 'initiator' in roles_signed and 'approver' in roles_signed:
            batch.completed_at = datetime.now()
            AssemblyService._post_outbound_batch_inventory(batch, user)
            shipped = order.shipped_quantity
            planned = float(order.planned_quantity or 0)
            if shipped + 1e-9 >= planned:
                order.status = 'completed'
                order.completed_at = datetime.now()
                AssemblyService.add_outbound_history(
                    order,
                    '出厂完成',
                    f'累计出厂数量 {shipped:g} / 计划出厂数量 {planned:g}，订单已锁定完成',
                    user,
                )
                message = '本批次双方已确认，出厂订单已完成'
            else:
                AssemblyService.add_outbound_history(
                    order,
                    '阶段出厂完成',
                    f'本批出厂 {float(batch.outbound_quantity or 0):g}，累计出厂数量 {shipped:g} / 计划出厂数量 {planned:g}',
                    user,
                )
                message = '本批次双方已确认，仍有剩余数量待出厂'
            db.session.commit()
            return {'completed': shipped + 1e-9 >= planned, 'message': message}

        db.session.commit()
        return {'completed': False, 'message': '出厂确认已提交，等待另一方确认'}

    @staticmethod
    def _template_file_path(attachment) -> str | None:
        if not attachment or not attachment.file_path:
            return None
        if isinstance(attachment, AssemblyProductAttachment):
            return os.path.join(AssemblyService.product_upload_root(attachment.product_id), attachment.file_path)
        return os.path.join(current_app.root_path, '..', 'static', 'uploads', 'qc', 'workpieces', str(attachment.workpiece_id), attachment.file_path)

    @staticmethod
    def _docx_paragraph_xml(text: str = '') -> str:
        preserve = ' xml:space="preserve"' if text and (text[0].isspace() or text[-1].isspace()) else ''
        return f'<w:p><w:r><w:t{preserve}>{escape(str(text), quote=False)}</w:t></w:r></w:p>'

    @staticmethod
    def _docx_lines_xml(lines: list[str]) -> str:
        return ''.join(AssemblyService._docx_paragraph_xml(line) for line in lines)

    @staticmethod
    def _docx_page_break_xml() -> str:
        return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'

    @staticmethod
    def _minimal_docx_bytes(document_text: str) -> bytes:
        escaped_lines = AssemblyService._docx_lines_xml(document_text.splitlines())
        document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{escaped_lines}<w:sectPr/></w:body>
</w:document>'''
        return AssemblyService._minimal_docx_package(document_xml)

    @staticmethod
    def _minimal_docx_package(document_xml: str) -> bytes:
        output = BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as docx:
            docx.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>''')
            docx.writestr('_rels/.rels', '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''')
            docx.writestr('word/document.xml', document_xml)
        return output.getvalue()

    @staticmethod
    def _replace_docx_placeholders(xml_text: str, replacements: dict[str, str]) -> str:
        for key, value in replacements.items():
            safe_value = escape(str(value), quote=False)
            xml_text = xml_text.replace(f'{{{{{key}}}}}', safe_value)
            xml_text = xml_text.replace(f'{{ {key} }}', safe_value)
        return xml_text

    @staticmethod
    def _render_docx_template(template_bytes: bytes, replacements: dict[str, str]) -> bytes:
        output = BytesIO()
        with zipfile.ZipFile(BytesIO(template_bytes), 'r') as source, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename.startswith('word/') and item.filename.endswith('.xml'):
                    text = data.decode('utf-8')
                    text = AssemblyService._replace_docx_placeholders(text, replacements)
                    data = text.encode('utf-8')
                target.writestr(item, data)
        return output.getvalue()

    @staticmethod
    def _split_docx_body(document_xml: str) -> tuple[str, str, str, str]:
        body_match = re.search(r'(<w:body[^>]*>)(.*)(</w:body>)', document_xml, flags=re.DOTALL)
        if not body_match:
            return (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
                '<w:body>',
                '',
                '<w:sectPr/>',
            )
        document_prefix = document_xml[:body_match.start(1)]
        body_start, body_inner, body_end = body_match.groups()
        section_match = re.search(r'(<w:sectPr[\s\S]*?</w:sectPr>|<w:sectPr[^>]*/>)\s*$', body_inner)
        section_xml = section_match.group(1) if section_match else '<w:sectPr/>'
        if section_match:
            body_inner = body_inner[:section_match.start()]
        return document_prefix, body_start, body_inner, section_xml

    @staticmethod
    def _build_coa_cover_xml(replacements: dict[str, str]) -> str:
        lines = [
            'COA报告',
            '',
            f"出厂批次：{replacements['出厂批次']}",
            f"产品/工件编号：{replacements['产品编号']}",
            f"产品/工件名称：{replacements['产品名称']}",
            f"来源库：{replacements['来源库']}",
            f"本批出厂数量：{replacements['出厂数量']}",
            f"计划出厂总数量：{replacements['计划出厂总数量']}",
            f"累计出厂数量：{replacements['累计出厂数量']}",
            f"剩余待出厂数量：{replacements['剩余待出厂数量']}",
            f"出厂日期：{replacements['出厂日期']}",
            f"发起人：{replacements['发起人']}",
            f"验收人：{replacements['验收人']}",
            f"打印时间：{replacements['打印时间']}",
        ]
        return AssemblyService._docx_lines_xml(lines)

    @staticmethod
    def _build_coa_signature_xml(replacements: dict[str, str]) -> str:
        lines = [
            '签名确认',
            '',
            f"出厂发起人：{replacements['发起人']}",
            f"发起确认时间：{replacements['发起确认时间']}",
            '',
            f"出厂验收人：{replacements['验收人']}",
            f"验收确认时间：{replacements['验收确认时间']}",
            '',
            f"签名：{replacements['签名']}",
        ]
        return AssemblyService._docx_lines_xml(lines)

    @staticmethod
    def _compose_coa_docx(
        template_bytes: bytes | None,
        replacements: dict[str, str],
    ) -> bytes:
        cover_xml = AssemblyService._build_coa_cover_xml(replacements)
        signature_xml = AssemblyService._build_coa_signature_xml(replacements)
        if template_bytes:
            source_buffer = BytesIO(template_bytes)
            output = BytesIO()
            with zipfile.ZipFile(source_buffer, 'r') as source, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as target:
                document_xml = source.read('word/document.xml').decode('utf-8')
                document_xml = AssemblyService._replace_docx_placeholders(document_xml, replacements)
                document_prefix, body_start, template_body, section_xml = AssemblyService._split_docx_body(document_xml)
                combined_document_xml = (
                    document_prefix +
                    f'{body_start}{cover_xml}{AssemblyService._docx_page_break_xml()}'
                    f'{template_body}{AssemblyService._docx_page_break_xml()}'
                    f'{signature_xml}{section_xml}</w:body></w:document>'
                )
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename == 'word/document.xml':
                        data = combined_document_xml.encode('utf-8')
                    elif item.filename.startswith('word/') and item.filename.endswith('.xml'):
                        data = AssemblyService._replace_docx_placeholders(
                            data.decode('utf-8'),
                            replacements,
                        ).encode('utf-8')
                    target.writestr(item, data)
            return output.getvalue()

        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body>{cover_xml}{AssemblyService._docx_page_break_xml()}'
            f'{AssemblyService._docx_lines_xml(["默认 COA 模板内容", "未上传 .docx 模板，本页使用系统默认占位内容。"])}'
            f'{AssemblyService._docx_page_break_xml()}{signature_xml}<w:sectPr/></w:body></w:document>'
        )
        return AssemblyService._minimal_docx_package(document_xml)

    @staticmethod
    def _extract_docx_text_lines(template_bytes: bytes, replacements: dict[str, str]) -> list[str]:
        with zipfile.ZipFile(BytesIO(template_bytes), 'r') as docx:
            document_xml = docx.read('word/document.xml').decode('utf-8')
        document_xml = AssemblyService._replace_docx_placeholders(document_xml, replacements)
        lines: list[str] = []
        for paragraph in re.findall(r'<w:p[\s\S]*?</w:p>', document_xml):
            parts = [
                html_unescape(re.sub(r'<[^>]+>', '', text))
                for text in re.findall(r'<w:t[^>]*>([\s\S]*?)</w:t>', paragraph)
            ]
            line = ''.join(parts).strip()
            if line:
                lines.append(line)
        return lines or ['模板正文为空。']

    @staticmethod
    def _build_outbound_coa_payload(order_id: int, batch_id: int, user: User) -> dict:
        order = AssemblyService.get_outbound_order(order_id, user)
        if not order:
            raise ValueError('出厂订单不存在或没有权限查看')
        batch = next((item for item in order.batches if item.id == batch_id), None)
        if not batch or not batch.completed_at:
            raise ValueError('请选择已完成的出厂批次打印 COA 报告')

        signatures = batch.signatures_by_role
        initiator_signature = signatures.get('initiator')
        approver_signature = signatures.get('approver')
        initiator_name = order.initiator.real_name or order.initiator.username
        approver_name = ''
        if approver_signature and approver_signature.signer:
            approver_name = approver_signature.signer.real_name or approver_signature.signer.username
        batch_quantity = float(batch.outbound_quantity or 0)
        planned_quantity = float(order.planned_quantity or 0)
        shipped_quantity = float(order.shipped_quantity or 0)
        replacements = {
            '批次号': order.outbound_no,
            '出厂批次': order.outbound_no,
            '产品编号': order.item_code_snapshot or '',
            '产品名称': order.item_name_snapshot or '',
            '来源库': order.item_type_display,
            '数量': f'{batch_quantity:g}',
            '出厂数量': f'{batch_quantity:g}',
            '计划出厂总数量': f'{planned_quantity:g}',
            '累计出厂数量': f'{shipped_quantity:g}',
            '剩余待出厂数量': f'{max(0.0, planned_quantity - shipped_quantity):g}',
            '出厂日期': order.outbound_date.strftime('%Y-%m-%d') if order.outbound_date else '',
            '发起人': initiator_name,
            '验收人': approver_name,
            '签名': approver_name,
            '发起确认时间': initiator_signature.signed_at.strftime('%Y-%m-%d %H:%M') if initiator_signature else '',
            '验收确认时间': approver_signature.signed_at.strftime('%Y-%m-%d %H:%M') if approver_signature else '',
            '打印时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }

        attachment = order.coa_template_attachment
        template_path = AssemblyService._template_file_path(attachment)
        template_bytes = None
        if template_path and os.path.exists(template_path) and (attachment.file_type or '').lower() == 'docx':
            with open(template_path, 'rb') as handle:
                template_bytes = handle.read()
        template_lines = (
            AssemblyService._extract_docx_text_lines(template_bytes, replacements)
            if template_bytes else
            ['默认 COA 模板内容', '未上传 .docx 模板，本页使用系统默认占位内容。']
        )
        batch_no = AssemblyService._batch_sequence(order.batches, batch)
        filename = f"COA_{order.outbound_no}_batch_{batch_no}.docx"
        return {
            'order': order,
            'batch': batch,
            'batch_no': batch_no,
            'replacements': replacements,
            'template_bytes': template_bytes,
            'template_lines': template_lines,
            'filename': filename,
        }

    @staticmethod
    def get_outbound_coa_preview(order_id: int, batch_id: int, user: User) -> dict:
        return AssemblyService._build_outbound_coa_payload(order_id, batch_id, user)

    @staticmethod
    def generate_outbound_coa_docx(order_id: int, batch_id: int, user: User) -> tuple[bytes, str]:
        payload = AssemblyService._build_outbound_coa_payload(order_id, batch_id, user)
        document_bytes = AssemblyService._compose_coa_docx(
            payload['template_bytes'],
            payload['replacements'],
        )
        return document_bytes, payload['filename']

    @staticmethod
    def _validate_acceptance_quantities(order: AssemblyOrder, production_quantity, accepted_quantity) -> tuple[float, float]:
        production_total = AssemblyService._to_float(production_quantity, 0.0)
        accepted_total = AssemblyService._to_float(accepted_quantity, 0.0)
        if production_total <= 0:
            raise ValueError('本次生产总数必须大于 0')
        if accepted_total < 0:
            raise ValueError('质检合格数量不能为负数')
        if accepted_total > production_total + 1e-9:
            raise ValueError('质检合格数量不能大于本次生产总数')
        remaining = order.remaining_acceptance_quantity
        if accepted_total > remaining + 1e-9:
            raise ValueError(f'质检合格数量不能超过剩余待验收数量 {remaining:g}')
        return production_total, accepted_total

    @staticmethod
    def start_acceptance_batch(order_id: int, user: User) -> AssemblyAcceptanceBatch:
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if order.status not in ['inspection_completed', 'accepted']:
            raise ValueError('当前装配单尚未进入验收阶段')
        if order.remaining_acceptance_quantity <= 1e-9:
            raise ValueError('该装配单已达到计划装配数量，无需继续验收')
        if order.active_acceptance_batch:
            raise ValueError('当前已有未完成的验收批次，请先完成该批次确认')
        if not AssemblyService.eligible_acceptance_signer_roles(user, order):
            raise ValueError('没有权限发起验收批次')
        batch = AssemblyAcceptanceBatch(order_id=order.id, production_quantity=0, accepted_quantity=0)
        db.session.add(batch)
        db.session.flush()
        batch_no = AssemblyService._batch_sequence(order.acceptance_batches, batch)
        AssemblyService.add_order_history(
            order,
            '发起验收批次',
            f'发起第 {batch_no} 个验收批次，等待填写数量并双方确认',
            user,
        )
        db.session.commit()
        return batch

    @staticmethod
    def _ensure_acceptance_batch(order: AssemblyOrder, production_quantity, accepted_quantity) -> AssemblyAcceptanceBatch:
        batch = order.active_acceptance_batch
        if batch:
            if not batch.signatures:
                production_total, accepted_total = AssemblyService._validate_acceptance_quantities(
                    order,
                    production_quantity,
                    accepted_quantity,
                )
                batch.production_quantity = production_total
                batch.accepted_quantity = accepted_total
                batch.updated_at = datetime.now()
                AssemblyService.add_order_history(
                    order,
                    '填写验收批次数量',
                    f'本次生产总数 {production_total:g}，质检合格数量 {accepted_total:g}',
                )
            elif float(batch.production_quantity or 0) <= 0:
                raise ValueError('当前验收批次缺少本次生产总数')
            return batch
        production_total, accepted_total = AssemblyService._validate_acceptance_quantities(
            order,
            production_quantity,
            accepted_quantity,
        )
        batch = AssemblyAcceptanceBatch(
            order_id=order.id,
            production_quantity=production_total,
            accepted_quantity=accepted_total,
        )
        db.session.add(batch)
        db.session.flush()
        AssemblyService.add_order_history(
            order,
            '创建验收批次',
            f'本次生产总数 {production_total:g}，质检合格数量 {accepted_total:g}',
        )
        return batch

    @staticmethod
    def _post_acceptance_batch_inventory(batch: AssemblyAcceptanceBatch, user: User | None = None) -> None:
        order = batch.order
        if batch.inventory_posted_at:
            return
        accepted_quantity = float(batch.accepted_quantity or 0)
        if accepted_quantity <= 0:
            batch.inventory_posted_at = datetime.now()
            return
        for component in order.components:
            item = AssemblyService._component_inventory_item(component)
            required_quantity = float(component.quantity_per_unit or 0) * accepted_quantity
            if not item:
                raise ValueError(f'配件 {component.workpiece_code_snapshot} 已不存在，无法扣减库存')
            if float(item.stock_quantity or 0) + 1e-9 < required_quantity:
                raise ValueError(
                    f"配件 {AssemblyService._component_inventory_label(component)} 库存不足，"
                    f"当前库存 {float(item.stock_quantity or 0):g}，需扣减 {required_quantity:g}"
                )
        for component in order.components:
            item = AssemblyService._component_inventory_item(component)
            required_quantity = float(component.quantity_per_unit or 0) * accepted_quantity
            stock_before = float(item.stock_quantity or 0)
            item.stock_quantity = float(item.stock_quantity or 0) - required_quantity
            stock_after = float(item.stock_quantity or 0)
            if component.component_type == 'product' and component.component_product:
                AssemblyService._add_product_stock_history(
                    component.component_product,
                    change_type='assembly_consumption',
                    batch_no=order.batch_no,
                    production_quantity=float(batch.production_quantity or 0),
                    accepted_quantity=accepted_quantity,
                    quantity_delta=-required_quantity,
                    stock_before=stock_before,
                    stock_after=stock_after,
                    assembly_order=order,
                    acceptance_batch=batch,
                    user=user,
                    note=f'装配验收批次 #{AssemblyService._batch_sequence(order.acceptance_batches, batch)} 扣减组件 {required_quantity:g}',
                )
            elif component.workpiece:
                AssemblyService._add_workpiece_stock_history(
                    component.workpiece,
                    change_type='assembly_consumption',
                    batch_no=order.batch_no,
                    production_quantity=float(batch.production_quantity or 0),
                    accepted_quantity=accepted_quantity,
                    quantity_delta=-required_quantity,
                    stock_before=stock_before,
                    stock_after=stock_after,
                    assembly_order=order,
                    acceptance_batch=batch,
                    user=user,
                    note=f'装配验收批次 #{AssemblyService._batch_sequence(order.acceptance_batches, batch)} 扣减组件 {required_quantity:g}',
                )
        if order.product:
            product_stock_before = float(order.product.stock_quantity or 0)
            order.product.stock_quantity = float(order.product.stock_quantity or 0) + accepted_quantity
            AssemblyService._add_product_stock_history(
                order.product,
                change_type='acceptance_in',
                batch_no=order.batch_no,
                production_quantity=float(batch.production_quantity or 0),
                accepted_quantity=accepted_quantity,
                quantity_delta=accepted_quantity,
                stock_before=product_stock_before,
                stock_after=float(order.product.stock_quantity or 0),
                assembly_order=order,
                acceptance_batch=batch,
                user=user,
                note=f'装配验收批次 #{AssemblyService._batch_sequence(order.acceptance_batches, batch)} 合格数量入库 {accepted_quantity:g}',
            )
        batch.inventory_posted_at = datetime.now()
        batch_no = AssemblyService._batch_sequence(order.acceptance_batches, batch)
        AssemblyService.add_order_history(
            order,
            '验收入库',
            f'验收批次 #{batch_no} 合格数量 {accepted_quantity:g} 已入库，并按 BOM 扣减 {len(order.components)} 项库存',
            user,
        )

    @staticmethod
    def _reverse_acceptance_batch_inventory(batch: AssemblyAcceptanceBatch, user: User | None = None) -> None:
        if not batch.inventory_posted_at:
            return
        order = batch.order
        accepted_quantity = float(batch.accepted_quantity or 0)
        for component in order.components:
            item = AssemblyService._component_inventory_item(component)
            if item:
                restored_quantity = float(component.quantity_per_unit or 0) * accepted_quantity
                stock_before = float(item.stock_quantity or 0)
                item.stock_quantity = stock_before + restored_quantity
                stock_after = float(item.stock_quantity or 0)
                if component.component_type == 'product' and component.component_product:
                    AssemblyService._add_product_stock_history(
                        component.component_product,
                        change_type='assembly_reverse',
                        batch_no=order.batch_no,
                        production_quantity=float(batch.production_quantity or 0),
                        accepted_quantity=accepted_quantity,
                        quantity_delta=restored_quantity,
                        stock_before=stock_before,
                        stock_after=stock_after,
                        assembly_order=order,
                        acceptance_batch=batch,
                        user=user,
                        note=f'验收批次 #{AssemblyService._batch_sequence(order.acceptance_batches, batch)} 撤销，恢复组件库存 {restored_quantity:g}',
                    )
                elif component.workpiece:
                    AssemblyService._add_workpiece_stock_history(
                        component.workpiece,
                        change_type='assembly_reverse',
                        batch_no=order.batch_no,
                        production_quantity=float(batch.production_quantity or 0),
                        accepted_quantity=accepted_quantity,
                        quantity_delta=restored_quantity,
                        stock_before=stock_before,
                        stock_after=stock_after,
                        assembly_order=order,
                        acceptance_batch=batch,
                        user=user,
                        note=f'验收批次 #{AssemblyService._batch_sequence(order.acceptance_batches, batch)} 撤销，恢复组件库存 {restored_quantity:g}',
                    )
        if order.product:
            product_stock_before = float(order.product.stock_quantity or 0)
            order.product.stock_quantity = max(0.0, product_stock_before - accepted_quantity)
            AssemblyService._add_product_stock_history(
                order.product,
                change_type='acceptance_reverse',
                batch_no=order.batch_no,
                production_quantity=float(batch.production_quantity or 0),
                accepted_quantity=accepted_quantity,
                quantity_delta=-accepted_quantity,
                stock_before=product_stock_before,
                stock_after=float(order.product.stock_quantity or 0),
                assembly_order=order,
                acceptance_batch=batch,
                user=user,
                note=f'验收批次 #{AssemblyService._batch_sequence(order.acceptance_batches, batch)} 撤销，扣回产品入库 {accepted_quantity:g}',
            )
        batch.inventory_posted_at = None
        batch_no = AssemblyService._batch_sequence(order.acceptance_batches, batch)
        AssemblyService.add_order_history(
            order,
            '撤销入库',
            f'验收批次 #{batch_no} 取消，已撤销产品入库 {accepted_quantity:g} 及组件扣减',
            user,
        )

    @staticmethod
    def _post_inventory_if_needed(order: AssemblyOrder, user: User | None = None) -> None:
        if order.acceptance_batches:
            for batch in order.completed_acceptance_batches:
                AssemblyService._post_acceptance_batch_inventory(batch, user)
            return
        if order.inventory_posted_at or order.status != 'accepted':
            return
        legacy_batch = AssemblyAcceptanceBatch(
            order_id=order.id,
            production_quantity=float(order.quantity or 0),
            accepted_quantity=float(order.quantity or 0),
            completed_at=datetime.now(),
        )
        db.session.add(legacy_batch)
        db.session.flush()
        AssemblyService._post_acceptance_batch_inventory(legacy_batch, user)
        order.inventory_posted_at = legacy_batch.inventory_posted_at

    @staticmethod
    def _reverse_inventory_if_posted(order: AssemblyOrder, user: User | None = None) -> None:
        if order.acceptance_batches:
            for batch in list(order.completed_acceptance_batches):
                AssemblyService._reverse_acceptance_batch_inventory(batch, user)
            order.inventory_posted_at = None
            return
        if not order.inventory_posted_at:
            return
        order.inventory_posted_at = None
        AssemblyService.add_order_history(order, '库存恢复', '已撤销本装配单的工件扣减与产品入库', user)

    @staticmethod
    def sign_acceptance(
        order_id: int,
        user: User,
        signer_role: Optional[str] = None,
        production_quantity=None,
        accepted_quantity=None,
    ) -> dict:
        """Sign one acceptance role for the current user."""
        order = AssemblyOrder.query.get(order_id)
        if not order:
            raise ValueError('装配单不存在')
        if order.status not in ['inspection_completed', 'accepted']:
            raise ValueError('当前装配单尚未进入验收确认阶段')
        if order.status == 'accepted' and order.remaining_acceptance_quantity <= 1e-9:
            raise ValueError('该装配单已完成全部计划装配数量的验收')

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

        batch = AssemblyService._ensure_acceptance_batch(
            order,
            production_quantity=production_quantity,
            accepted_quantity=accepted_quantity,
        )

        existing = AssemblyAcceptanceSignature.query.filter_by(
            order_id=order.id,
            acceptance_batch_id=batch.id,
            signer_role=signer_role,
        ).first()
        if existing:
            raise ValueError('该角色已完成验收确认，无需重复操作')

        signature = AssemblyAcceptanceSignature(
            order_id=order.id,
            acceptance_batch_id=batch.id,
            signer_id=user.id,
            signer_role=signer_role,
        )
        db.session.add(signature)
        db.session.flush()
        AssemblyService.add_order_history(order, '验收确认', f'{signature.signer_role_display}已确认', user)

        roles_signed = {
            item.signer_role
            for item in AssemblyAcceptanceSignature.query.filter_by(acceptance_batch_id=batch.id).all()
        }
        if 'qc_controller' in roles_signed and 'qc_inspector' in roles_signed:
            batch.completed_at = datetime.now()
            AssemblyService._post_acceptance_batch_inventory(batch, user)
            delivered = order.actual_delivered_quantity
            planned = float(order.quantity or 0)
            if delivered + 1e-9 >= planned:
                order.status = 'accepted'
                order.accepted_at = datetime.now()
                order.inventory_posted_at = datetime.now()
                AssemblyService.add_order_history(
                    order,
                    '验收完成',
                    f'累计质检合格数量 {delivered:g} / 计划装配数量 {planned:g}，装配单已锁定完成',
                    user,
                )
                message = '本批次双方已确认，装配单已完成'
            else:
                order.status = 'inspection_completed'
                order.accepted_at = None
                AssemblyService.add_order_history(
                    order,
                    '阶段验收完成',
                    f'本批合格 {float(batch.accepted_quantity or 0):g}，累计质检合格数量 {delivered:g} / 计划装配数量 {planned:g}',
                    user,
                )
                message = '本批次双方已确认，仍有剩余数量待验收'
            db.session.commit()
            return {'completed': delivered + 1e-9 >= planned, 'message': message}

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
        batch = order.active_acceptance_batch
        query = AssemblyAcceptanceSignature.query.filter_by(order_id=order.id, signer_role=signer_role)
        if batch:
            query = query.filter_by(acceptance_batch_id=batch.id)
        signature = query.order_by(AssemblyAcceptanceSignature.id.desc()).first()
        if not signature:
            raise ValueError('该角色尚未完成验收确认')
        role_display = signature.signer_role_display
        db.session.delete(signature)
        db.session.flush()
        if batch and not AssemblyAcceptanceSignature.query.filter_by(acceptance_batch_id=batch.id).first():
            db.session.delete(batch)
        AssemblyService.add_order_history(order, '取消验收确认', f'{role_display}确认已取消', user)
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

        AssemblyService._reverse_inventory_if_posted(order, user)
        AssemblyAcceptanceSignature.query.filter_by(order_id=order.id).delete()
        AssemblyAcceptanceBatch.query.filter_by(order_id=order.id).delete()
        order.accepted_at = None
        order.inventory_posted_at = None

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
