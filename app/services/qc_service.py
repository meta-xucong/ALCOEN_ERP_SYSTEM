"""QC service layer."""

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
    QC_GUIDE_ATTACHMENT_TYPES,
    QC_MANAGER_ROLE_CODES,
    QC_QUALITY_MATERIAL_ATTACHMENT_TYPE,
    QC_WORKPIECE_TYPE_OUTSOURCED,
    QC_WORKPIECE_TYPE_SELF,
    QCWorkOrder,
    QCWorkOrderAttachment,
    QCWorkOrderHistory,
    QCInspectionRecord,
    QCAcceptanceBatch,
    QCAcceptanceSignature,
    QCWorkpiece,
    QCWorkpieceAttachment,
    QCWorkpieceStockHistory,
    User,
    normalize_qc_guide_title,
    normalize_qc_workpiece_type,
)


class QCService:
    """QC service operations."""

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'pdf'}
    DOC_TEMPLATE_EXTENSIONS = {'docx'}

    _ATTACH_SUBFOLDER_MAP = {
        'drawing': 'drawings',
        'qc_material': 'qc_materials',
        'coa_template': 'coa_templates',
        'instruction': 'instructions',
        'inspection_point': 'inspection_points',
        'remark': 'remarks',
        'report': 'reports',
        'drawing_note': 'drawing_notes',
        'guide_certificate': 'guide_certificates',
        'remark_note': 'remark_notes',
    }

    _ORDER_SECTION_UPLOAD_FIELDS = {
        'drawing': ('drawing_note_file_path', 'drawing_note_file_type', 'drawing_note_original_name', 'drawing_note'),
        'guide': (
            'guide_certificate_file_path',
            'guide_certificate_file_type',
            'guide_certificate_original_name',
            'guide_certificate',
        ),
        'remark': ('remark_note_file_path', 'remark_note_file_type', 'remark_note_original_name', 'remark_note'),
    }

    @staticmethod
    def add_order_history(
        work_order: QCWorkOrder,
        action: str,
        detail: str | None = None,
        user: User | None = None,
    ) -> QCWorkOrderHistory:
        """Append an immutable history entry for a work order."""
        history = QCWorkOrderHistory(
            work_order_id=work_order.id,
            operator_id=user.id if user else None,
            action=action,
            detail=detail,
        )
        db.session.add(history)
        return history

    @staticmethod
    def _acceptance_batch_sequence(work_order: QCWorkOrder, batch: QCAcceptanceBatch) -> int:
        """Return the 1-based sequence of a batch within its own work order."""
        ordered = sorted(
            list(work_order.acceptance_batches or []),
            key=lambda item: (item.created_at or datetime.min, item.id or 0),
        )
        for index, item in enumerate(ordered, 1):
            if item is batch or (batch.id is not None and item.id == batch.id):
                return index
        return len(ordered) + 1

    @staticmethod
    def _post_acceptance_batch_inventory(batch: QCAcceptanceBatch, user: User | None = None) -> None:
        """Increase workpiece stock once for one completed acceptance batch."""
        work_order = batch.work_order
        if batch.inventory_posted_at or not work_order.workpiece_id or not work_order.workpiece:
            return

        quantity = float(batch.accepted_quantity or 0)
        if quantity <= 0:
            return

        stock_before = float(work_order.workpiece.stock_quantity or 0)
        stock_after = stock_before + quantity
        work_order.workpiece.stock_quantity = stock_after
        batch.inventory_posted_at = datetime.now()
        QCService._add_workpiece_stock_history(
            work_order=work_order,
            acceptance_batch=batch,
            quantity_delta=quantity,
            stock_before=stock_before,
            stock_after=stock_after,
            change_type='acceptance_in',
            user=user,
            note='验收模块验收成功，按质检合格件数入库',
        )
        batch_no = QCService._acceptance_batch_sequence(work_order, batch)
        QCService.add_order_history(
            work_order,
            '验收入库',
            f'验收批次 #{batch_no} 合格件数 {quantity:g} 已入库，当前库存 {work_order.workpiece.stock_quantity:g}',
            user,
        )

    @staticmethod
    def _reverse_acceptance_batch_inventory(batch: QCAcceptanceBatch, user: User | None = None) -> None:
        """Reverse stock added by one acceptance batch."""
        work_order = batch.work_order
        if not batch.inventory_posted_at or not work_order.workpiece_id or not work_order.workpiece:
            return

        quantity = float(batch.accepted_quantity or 0)
        if quantity <= 0:
            batch.inventory_posted_at = None
            return

        current_stock = float(work_order.workpiece.stock_quantity or 0)
        stock_after = max(0.0, current_stock - quantity)
        work_order.workpiece.stock_quantity = stock_after
        batch.inventory_posted_at = None
        QCService._add_workpiece_stock_history(
            work_order=work_order,
            acceptance_batch=batch,
            quantity_delta=-quantity,
            stock_before=current_stock,
            stock_after=stock_after,
            change_type='acceptance_reverse',
            user=user,
            note='验收撤销/回退，扣回该批次已入库数量',
        )
        batch_no = QCService._acceptance_batch_sequence(work_order, batch)
        QCService.add_order_history(
            work_order,
            '撤销入库',
            f'验收批次 #{batch_no} 取消，工件库存扣回 {quantity:g}，当前库存 {work_order.workpiece.stock_quantity:g}',
            user,
        )

    @staticmethod
    def _post_inventory_if_needed(work_order: QCWorkOrder, user: User | None = None) -> None:
        """Backward-compatible full-order stock posting for legacy accepted orders."""
        if work_order.acceptance_batches:
            for batch in work_order.completed_acceptance_batches:
                QCService._post_acceptance_batch_inventory(batch, user)
            return
        if work_order.inventory_posted_at or not work_order.workpiece_id or not work_order.workpiece:
            return

        quantity = float(work_order.quantity or 0)
        if quantity <= 0:
            return

        stock_before = float(work_order.workpiece.stock_quantity or 0)
        stock_after = stock_before + quantity
        work_order.workpiece.stock_quantity = stock_after
        work_order.inventory_posted_at = datetime.now()
        QCService._add_workpiece_stock_history(
            work_order=work_order,
            acceptance_batch=None,
            quantity_delta=quantity,
            stock_before=stock_before,
            stock_after=stock_after,
            change_type='acceptance_in',
            user=user,
            note='兼容旧订单整单验收入库',
        )
        QCService.add_order_history(
            work_order,
            '验收入库',
            f'工件库存增加 {quantity:g}，当前库存 {work_order.workpiece.stock_quantity:g}',
            user,
        )

    @staticmethod
    def _reverse_inventory_if_posted(work_order: QCWorkOrder, user: User | None = None) -> None:
        """Reverse stock increases when acceptance is rolled back."""
        if work_order.acceptance_batches:
            for batch in list(work_order.completed_acceptance_batches):
                QCService._reverse_acceptance_batch_inventory(batch, user)
            return
        if not work_order.inventory_posted_at or not work_order.workpiece_id or not work_order.workpiece:
            return

        quantity = float(work_order.quantity or 0)
        if quantity <= 0:
            work_order.inventory_posted_at = None
            return

        current_stock = float(work_order.workpiece.stock_quantity or 0)
        stock_after = max(0.0, current_stock - quantity)
        work_order.workpiece.stock_quantity = stock_after
        work_order.inventory_posted_at = None
        QCService._add_workpiece_stock_history(
            work_order=work_order,
            acceptance_batch=None,
            quantity_delta=-quantity,
            stock_before=current_stock,
            stock_after=stock_after,
            change_type='acceptance_reverse',
            user=user,
            note='兼容旧订单验收回退，扣回整单入库数量',
        )
        QCService.add_order_history(
            work_order,
            '撤销入库',
            f'验收回退，工件库存扣回 {quantity:g}，当前库存 {work_order.workpiece.stock_quantity:g}',
            user,
        )

    @staticmethod
    def _add_workpiece_stock_history(
        work_order: QCWorkOrder,
        acceptance_batch: QCAcceptanceBatch | None,
        quantity_delta: float,
        stock_before: float,
        stock_after: float,
        change_type: str,
        user: User | None = None,
        note: str | None = None,
    ) -> QCWorkpieceStockHistory | None:
        """Record an immutable workpiece stock movement."""
        if not work_order.workpiece_id:
            return None

        history = QCWorkpieceStockHistory(
            workpiece_id=work_order.workpiece_id,
            work_order_id=work_order.id,
            acceptance_batch_id=acceptance_batch.id if acceptance_batch else None,
            operator_id=user.id if user else None,
            change_type=change_type,
            batch_no=work_order.batch_no,
            production_quantity=float(acceptance_batch.production_quantity or 0) if acceptance_batch else float(work_order.quantity or 0),
            accepted_quantity=float(acceptance_batch.accepted_quantity or 0) if acceptance_batch else abs(float(quantity_delta or 0)),
            quantity_delta=float(quantity_delta or 0),
            stock_before=float(stock_before or 0),
            stock_after=float(stock_after or 0),
            note=note,
        )
        db.session.add(history)
        return history

    @staticmethod
    def _allowed_file(filename: str) -> bool:
        """Check whether the uploaded filename extension is allowed."""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in QCService.ALLOWED_EXTENSIONS

    @staticmethod
    def _allowed_template_file(filename: str) -> bool:
        """Check whether the uploaded filename extension is a Word template."""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in QCService.DOC_TEMPLATE_EXTENSIONS

    @staticmethod
    def _get_file_extension(filename: str) -> str:
        """Return the lowercase file extension."""
        if '.' in filename:
            return filename.rsplit('.', 1)[1].lower()
        return ''

    @staticmethod
    def _order_upload_root(work_order_id: int) -> str:
        return os.path.join(
            current_app.root_path, '..', 'static', 'uploads', 'qc', str(work_order_id)
        )

    @staticmethod
    def _workpiece_upload_root(workpiece_id: int) -> str:
        return os.path.join(
            current_app.root_path, '..', 'static', 'uploads', 'qc', 'workpieces', str(workpiece_id)
        )

    @staticmethod
    def _save_uploaded_file(file, work_order_id: int, subfolder: str) -> str:
        """Save an uploaded file under the work-order QC upload directory."""
        upload_dir = os.path.join(QCService._order_upload_root(work_order_id), subfolder)
        os.makedirs(upload_dir, exist_ok=True)

        safe_name = secure_filename(file.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)

        return f"{subfolder}/{filename}"

    @staticmethod
    def _save_workpiece_file(file, workpiece_id: int, subfolder: str) -> str:
        """Save an uploaded file under the workpiece-library QC upload directory."""
        upload_dir = os.path.join(QCService._workpiece_upload_root(workpiece_id), subfolder)
        os.makedirs(upload_dir, exist_ok=True)

        safe_name = secure_filename(file.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)

        return f"{subfolder}/{filename}"

    @staticmethod
    def _remove_file(work_order_id: int, relative_path: str):
        """Delete the physical uploaded work-order file when it exists."""
        if not relative_path:
            return
        filepath = os.path.join(QCService._order_upload_root(work_order_id), relative_path)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    @staticmethod
    def _remove_workpiece_file(workpiece_id: int, relative_path: str):
        """Delete the physical uploaded workpiece file when it exists."""
        if not relative_path:
            return
        filepath = os.path.join(QCService._workpiece_upload_root(workpiece_id), relative_path)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    @staticmethod
    def _save_file_for_attachment(file, work_order_id: int, attach_type: str) -> tuple[str, str]:
        """Persist a work-order attachment file and return its relative path and type."""
        if not file or not file.filename:
            raise ValueError('请选择要上传的文件')
        if attach_type == 'coa_template':
            if not QCService._allowed_template_file(file.filename):
                raise ValueError('COA报告模板仅支持可拼接的 Word 模板（.docx）')
        elif not QCService._allowed_file(file.filename):
            raise ValueError('不支持的文件格式，请上传图片或 PDF')

        subfolder = QCService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others')
        relative_path = QCService._save_uploaded_file(file, work_order_id, subfolder)
        file_type = QCService._get_file_extension(file.filename)
        return relative_path, file_type

    @staticmethod
    def _save_file_for_workpiece_attachment(file, workpiece_id: int, attach_type: str) -> tuple[str, str]:
        """Persist a workpiece attachment file and return its relative path and type."""
        if not file or not file.filename:
            raise ValueError('请选择要上传的文件')
        if attach_type == 'coa_template':
            if not QCService._allowed_template_file(file.filename):
                raise ValueError('COA报告模板仅支持可拼接的 Word 模板（.docx）')
        elif not QCService._allowed_file(file.filename):
            raise ValueError('不支持的文件格式，请上传图片或 PDF')

        subfolder = QCService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others')
        relative_path = QCService._save_workpiece_file(file, workpiece_id, subfolder)
        file_type = QCService._get_file_extension(file.filename)
        return relative_path, file_type

    @staticmethod
    def _replace_attachment_file(attachment: QCWorkOrderAttachment, file, attach_type: str) -> None:
        """Replace a work-order attachment file and update stored metadata."""
        old_path = attachment.file_path
        relative_path, file_type = QCService._save_file_for_attachment(
            file=file,
            work_order_id=attachment.work_order_id,
            attach_type=attach_type,
        )
        attachment.file_path = relative_path
        attachment.file_type = file_type

        if old_path and old_path != relative_path:
            QCService._remove_file(attachment.work_order_id, old_path)

    @staticmethod
    def _replace_workpiece_attachment_file(attachment: QCWorkpieceAttachment, file, attach_type: str) -> None:
        """Replace a workpiece attachment file and update stored metadata."""
        old_path = attachment.file_path
        relative_path, file_type = QCService._save_file_for_workpiece_attachment(
            file=file,
            workpiece_id=attachment.workpiece_id,
            attach_type=attach_type,
        )
        attachment.file_path = relative_path
        attachment.file_type = file_type

        if old_path and old_path != relative_path:
            QCService._remove_workpiece_file(attachment.workpiece_id, old_path)

    @staticmethod
    def _copy_workpiece_file_to_order(
        workpiece_id: int,
        work_order_id: int,
        relative_path: str,
        attach_type: str,
    ) -> tuple[str, str]:
        """Copy a workpiece-library file into the work-order snapshot directory."""
        if not relative_path:
            return '', ''

        source_path = os.path.join(QCService._workpiece_upload_root(workpiece_id), relative_path)
        if not os.path.exists(source_path):
            raise ValueError(f'工件库附件文件不存在：{os.path.basename(relative_path)}')

        source_name = os.path.basename(relative_path)
        safe_name = secure_filename(source_name)
        ext = QCService._get_file_extension(source_name) or 'bin'
        subfolder = QCService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others')
        target_dir = os.path.join(QCService._order_upload_root(work_order_id), subfolder)
        os.makedirs(target_dir, exist_ok=True)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
        target_path = os.path.join(target_dir, filename)
        shutil.copy2(source_path, target_path)
        return f"{subfolder}/{filename}", ext

    @staticmethod
    def _save_order_section_file(file, work_order_id: int, section_key: str) -> tuple[str, str]:
        """Persist a section-level order file and return its relative path and file type."""
        if not file or not file.filename:
            raise ValueError('请选择要上传的文件')
        if not QCService._allowed_file(file.filename):
            raise ValueError('不支持的文件格式，请上传图片或 PDF')

        subfolder = QCService._ATTACH_SUBFOLDER_MAP[QCService._ORDER_SECTION_UPLOAD_FIELDS[section_key][3]]
        relative_path = QCService._save_uploaded_file(file, work_order_id, subfolder)
        file_type = QCService._get_file_extension(file.filename)
        return relative_path, file_type

    @staticmethod
    def _replace_order_section_file(work_order: QCWorkOrder, section_key: str, file) -> None:
        """Replace a section-level order file and update the stored metadata."""
        if not file or not file.filename:
            return

        path_field, type_field, name_field, _ = QCService._ORDER_SECTION_UPLOAD_FIELDS[section_key]
        old_path = getattr(work_order, path_field)
        relative_path, file_type = QCService._save_order_section_file(file, work_order.id, section_key)
        setattr(work_order, path_field, relative_path)
        setattr(work_order, type_field, file_type)
        setattr(work_order, name_field, file.filename)

        if old_path and old_path != relative_path:
            QCService._remove_file(work_order.id, old_path)

    @staticmethod
    def _delete_order_section_files(work_order: QCWorkOrder) -> None:
        """Delete all section-level order files from disk."""
        for path_field, _, _, _ in QCService._ORDER_SECTION_UPLOAD_FIELDS.values():
            relative_path = getattr(work_order, path_field)
            if relative_path:
                QCService._remove_file(work_order.id, relative_path)

    @staticmethod
    def sync_order_section_files(
        order_id: int,
        drawing_note_file,
        guide_certificate_file,
        remark_note_file,
        user: User,
        auto_commit: bool = True,
    ) -> QCWorkOrder:
        """Persist section-level supplemental files for a work order."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')
        if not QCService.can_edit_work_order(user, work_order):
            raise ValueError('没有权限编辑此订单')

        QCService._replace_order_section_file(work_order, 'drawing', drawing_note_file)
        QCService._replace_order_section_file(work_order, 'guide', guide_certificate_file)
        QCService._replace_order_section_file(work_order, 'remark', remark_note_file)

        if auto_commit:
            db.session.commit()
        return work_order

    @staticmethod
    def _can_access_workpiece_scope(user: User) -> bool:
        """Return whether the user can access the workpiece library."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return any(
                user.has_ai_cats_permission(permission_code)
                for permission_code in (
                    'qc_workpiece_view',
                    'qc_workpiece_create',
                    'qc_workpiece_edit',
                    'qc_workpiece_delete',
                )
            )
        if user.has_ai_cats_identity('controller', 'production'):
            return any(
                user.has_ai_cats_permission(permission_code)
                for permission_code in (
                    'qc_workpiece_view',
                    'qc_workpiece_create',
                    'qc_workpiece_edit',
                    'qc_workpiece_delete',
                )
            )
        return False

    @staticmethod
    def _can_access_work_order_scope(user: User) -> bool:
        """Return whether the user can access the quality-control module."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return any(
                user.has_ai_cats_permission(permission_code)
                for permission_code in (
                    'qc_work_order_view',
                    'qc_work_order_create',
                    'qc_work_order_edit',
                    'qc_work_order_delete',
                )
            )
        if user.has_ai_cats_identity('controller', 'production'):
            return any(
                user.has_ai_cats_permission(permission_code)
                for permission_code in (
                    'qc_work_order_view',
                    'qc_work_order_create',
                    'qc_work_order_edit',
                    'qc_work_order_delete',
                )
            )
        return False

    @staticmethod
    def _delete_inspection_report_files(work_order: QCWorkOrder) -> None:
        """Delete all uploaded qualified-report files for the work order."""
        for record in work_order.inspection_records:
            if record.report_file_path:
                QCService._remove_file(work_order.id, record.report_file_path)

    @staticmethod
    def _reset_work_order_snapshot(work_order: QCWorkOrder) -> None:
        """Clear copied attachments, report files, inspection records, and signatures."""
        QCService._reverse_inventory_if_posted(work_order)
        QCService._delete_inspection_report_files(work_order)
        for attachment in list(work_order.attachments):
            if attachment.file_path:
                QCService._remove_file(work_order.id, attachment.file_path)
            db.session.delete(attachment)

        for record in list(work_order.inspection_records):
            db.session.delete(record)

        for signature in list(work_order.signatures):
            db.session.delete(signature)

        work_order.inspection_completed_at = None
        work_order.accepted_at = None
        work_order.rejected_at = None
        work_order.rejection_reason = None

    @staticmethod
    def _apply_workpiece_snapshot(work_order: QCWorkOrder, workpiece: QCWorkpiece) -> None:
        """Clone workpiece attachments into a work-order snapshot."""
        QCService._reset_work_order_snapshot(work_order)

        work_order.workpiece_id = workpiece.id
        work_order.workpiece_name = workpiece.workpiece_name
        work_order.workpiece_type = normalize_qc_workpiece_type(workpiece.workpiece_type)

        for attachment in workpiece.attachments:
            if attachment.attach_type == 'coa_template':
                continue
            file_path = ''
            file_type = ''
            if attachment.file_path:
                file_path, file_type = QCService._copy_workpiece_file_to_order(
                    workpiece_id=workpiece.id,
                    work_order_id=work_order.id,
                    relative_path=attachment.file_path,
                    attach_type=attachment.attach_type,
                )

            db.session.add(
                QCWorkOrderAttachment(
                    work_order_id=work_order.id,
                    attach_type='inspection_point' if attachment.attach_type == 'instruction' else attachment.attach_type,
                    title=attachment.display_title if attachment.attach_type in QC_GUIDE_ATTACHMENT_TYPES else attachment.title,
                    content=attachment.content,
                    file_path=file_path,
                    file_type=file_type,
                    is_required=attachment.is_required,
                    sort_order=attachment.sort_order,
                )
            )

    @staticmethod
    def serialize_workpiece_preview(workpiece: QCWorkpiece) -> dict:
        """Return a JSON-safe workpiece preview payload for the order form."""
        drawing = workpiece.drawing_attachment
        return {
            'id': workpiece.id,
            'workpiece_code': workpiece.workpiece_code,
            'workpiece_name': workpiece.workpiece_name,
            'workpiece_type': workpiece.normalized_type,
            'workpiece_type_display': workpiece.workpiece_type_display,
            'stock_quantity': float(workpiece.stock_quantity or 0),
            'primary_material_label': workpiece.primary_material_label,
            'creator_name': workpiece.creator.real_name or workpiece.creator.username,
            'drawing': None if not drawing else {
                'title': drawing.display_title,
                'filename': os.path.basename(drawing.file_path) if drawing.file_path else '',
                'url': drawing.file_url,
                'is_image': drawing.is_image,
            },
            'drawings': [
                {
                    'title': attachment.display_title,
                    'content': attachment.content or '',
                    'filename': os.path.basename(attachment.file_path) if attachment.file_path else '',
                    'url': attachment.file_url,
                    'is_image': attachment.is_image,
                }
                for attachment in workpiece.drawing_attachments
            ],
            'quality_materials': [
                {
                    'title': attachment.display_title,
                    'content': attachment.content or '',
                    'filename': os.path.basename(attachment.file_path) if attachment.file_path else '',
                    'url': attachment.file_url,
                    'is_image': attachment.is_image,
                }
                for attachment in workpiece.quality_material_attachments
            ],
            'guides': [
                {
                    'title': attachment.display_title,
                    'content': attachment.content or '',
                    'filename': os.path.basename(attachment.file_path) if attachment.file_path else '',
                    'url': attachment.file_url,
                    'is_image': attachment.is_image,
                }
                for attachment in workpiece.guide_attachments
            ],
            'remarks': [
                {
                    'content': attachment.content or '',
                    'filename': os.path.basename(attachment.file_path) if attachment.file_path else '',
                    'url': attachment.file_url,
                    'is_image': attachment.is_image,
                    'is_required': bool(attachment.is_required),
                }
                for attachment in workpiece.remark_attachments
            ],
        }

    @staticmethod
    def can_access_workpiece_library(user: User) -> bool:
        """Return whether the user can open the workpiece-library module."""
        return QCService._can_access_workpiece_scope(user)

    @staticmethod
    def can_create_workpiece(user: User) -> bool:
        """Return whether the user can create workpieces."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_create')
        return user.has_ai_cats_identity('controller', 'production') and user.has_ai_cats_permission('qc_workpiece_create')

    @staticmethod
    def can_edit_workpiece(user: User, workpiece: QCWorkpiece) -> bool:
        """Return whether the user can edit the workpiece."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_edit')
        if user.has_ai_cats_identity('controller', 'production') and workpiece.creator_id == user.id:
            return user.has_ai_cats_permission('qc_workpiece_edit')
        return False

    @staticmethod
    def can_delete_workpiece(user: User, workpiece: QCWorkpiece) -> bool:
        """Return whether the user can delete the workpiece."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_workpiece_delete')
        if user.has_ai_cats_identity('controller', 'production') and workpiece.creator_id == user.id:
            return user.has_ai_cats_permission('qc_workpiece_delete')
        return False

    @staticmethod
    def can_access_quality_control(user: User) -> bool:
        """Return whether the user can open the quality-control module."""
        return QCService._can_access_work_order_scope(user)

    @staticmethod
    def can_create_work_order(user: User) -> bool:
        """Return whether the user can create a work order."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_work_order_create')
        return user.has_ai_cats_identity('controller', 'production') and user.has_ai_cats_permission('qc_work_order_create')

    @staticmethod
    def can_access_inspection(user: User) -> bool:
        """Return whether the user can open the inspection module."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_inspection_view') or user.has_ai_cats_permission('qc_inspection_perform')
        if user.has_ai_cats_identity('controller', 'production'):
            return user.has_ai_cats_permission('qc_inspection_view')
        if user.has_ai_cats_identity('supplier', 'production'):
            return user.has_ai_cats_permission('qc_inspection_view') or user.has_ai_cats_permission('qc_inspection_perform')
        return False

    @staticmethod
    def can_access_acceptance(user: User) -> bool:
        """Return whether the user can open the acceptance module."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return user.has_ai_cats_permission('qc_acceptance_perform') or user.has_ai_cats_permission('qc_acceptance_rollback')
        if user.has_ai_cats_identity('controller', 'production'):
            return user.has_ai_cats_permission('qc_acceptance_perform') or user.has_ai_cats_permission('qc_acceptance_rollback')
        if user.has_ai_cats_identity('supplier', 'production'):
            return user.has_ai_cats_permission('qc_acceptance_perform')
        return False

    @staticmethod
    def can_view_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can view the work order."""
        if work_order.status == 'draft':
            return user.is_superadmin or (
                user.has_ai_cats_identity('controller', 'production')
                and work_order.controller_id == user.id
                and QCService._can_access_work_order_scope(user)
            )
        return work_order.can_be_viewed_by(user)

    @staticmethod
    def can_edit_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can edit the work order."""
        return work_order.can_be_edited_by(user)

    @staticmethod
    def can_delete_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can delete the work order."""
        return work_order.can_be_deleted_by(user)

    @staticmethod
    def can_inspect_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can perform inspection on the work order."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_inspection_perform'):
            return work_order.status in ['qc_completed', 'inspection_pending']
        if user.has_ai_cats_identity('supplier', 'production') and work_order.inspector_id == user.id:
            return user.has_ai_cats_permission('qc_inspection_perform') and work_order.status in ['qc_completed', 'inspection_pending']
        return False

    @staticmethod
    def can_accept_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can sign acceptance for the work order."""
        return bool(QCService.eligible_acceptance_signer_roles(user, work_order))

    @staticmethod
    def eligible_acceptance_signer_roles(user: User, work_order: QCWorkOrder) -> list[str]:
        """Return every acceptance signer role the user can act as for one work order."""
        if work_order.status not in ['inspection_completed', 'accepted']:
            return []
        if work_order.status == 'accepted' and work_order.remaining_acceptance_quantity <= 1e-9:
            return []
        if user.is_superadmin:
            return ['qc_controller', 'qc_inspector']
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_perform'):
            return ['qc_controller', 'qc_inspector']
        signer_roles: list[str] = []
        if user.has_ai_cats_identity('controller', 'production') and work_order.controller_id == user.id:
            if user.has_ai_cats_permission('qc_acceptance_perform'):
                signer_roles.append('qc_controller')
        if user.has_ai_cats_identity('supplier', 'production') and work_order.inspector_id == user.id:
            if user.has_ai_cats_permission('qc_acceptance_perform'):
                signer_roles.append('qc_inspector')
        return signer_roles

    @staticmethod
    def can_rollback_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can roll back acceptance for the work order."""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_rollback'):
            return work_order.status in ['inspection_completed', 'accepted']
        if user.has_ai_cats_identity('controller', 'production') and work_order.controller_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_rollback') and work_order.status in ['inspection_completed', 'accepted']
        return False

    @staticmethod
    def current_acceptance_batch(work_order: QCWorkOrder) -> QCAcceptanceBatch | None:
        """Return the currently open acceptance batch, if one exists."""
        return work_order.active_acceptance_batch

    @staticmethod
    def _validate_acceptance_quantities(
        work_order: QCWorkOrder,
        production_quantity,
        accepted_quantity,
    ) -> tuple[float, float]:
        """Validate and normalize one acceptance batch's quantity fields."""
        try:
            production_total = float(production_quantity)
        except (TypeError, ValueError):
            raise ValueError('请填写本次生产总数')
        try:
            accepted_total = float(accepted_quantity)
        except (TypeError, ValueError):
            raise ValueError('请填写质检合格件数')

        if production_total <= 0:
            raise ValueError('本次生产总数必须大于 0')
        if accepted_total < 0:
            raise ValueError('质检合格件数不能小于 0')
        if accepted_total > production_total + 1e-9:
            raise ValueError('质检合格件数不能大于本次生产总数')

        remaining = work_order.remaining_acceptance_quantity
        if remaining <= 1e-9:
            raise ValueError('该订单已达到计划生产数量，无需继续验收')
        if accepted_total > remaining + 1e-9:
            raise ValueError(f'质检合格件数不能超过剩余待交付数量 {remaining:g}')
        return production_total, accepted_total

    @staticmethod
    def start_acceptance_batch(order_id: int, user: User) -> QCAcceptanceBatch:
        """Explicitly start a new acceptance batch for a partially delivered work order."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')
        if work_order.status not in ['inspection_completed', 'accepted']:
            raise ValueError('当前订单尚未进入验收确认阶段')
        if work_order.remaining_acceptance_quantity <= 1e-9:
            raise ValueError('该订单已达到计划生产数量，无需继续验收')
        if work_order.active_acceptance_batch:
            raise ValueError('当前已有未完成的验收批次，请先完成该批次确认')
        if not QCService.eligible_acceptance_signer_roles(user, work_order):
            raise ValueError('没有权限发起验收批次')

        batch = QCAcceptanceBatch(
            work_order_id=work_order.id,
            production_quantity=0,
            accepted_quantity=0,
        )
        db.session.add(batch)
        db.session.flush()
        batch_no = QCService._acceptance_batch_sequence(work_order, batch)
        QCService.add_order_history(
            work_order,
            '发起验收批次',
            f'发起第 {batch_no} 个验收批次，等待填写数量并双方确认',
            user,
        )
        db.session.commit()
        return batch

    @staticmethod
    def _ensure_acceptance_batch(
        work_order: QCWorkOrder,
        production_quantity,
        accepted_quantity,
    ) -> QCAcceptanceBatch:
        """Get or create the open acceptance batch and validate its quantities."""
        batch = work_order.active_acceptance_batch
        if batch:
            if not batch.signatures:
                production_total, accepted_total = QCService._validate_acceptance_quantities(
                    work_order,
                    production_quantity,
                    accepted_quantity,
                )
                batch.production_quantity = production_total
                batch.accepted_quantity = accepted_total
                batch.updated_at = datetime.now()
                QCService.add_order_history(
                    work_order,
                    '填写验收批次数量',
                    f'本次生产总数 {production_total:g}，质检合格件数 {accepted_total:g}',
                )
            elif float(batch.production_quantity or 0) <= 0:
                raise ValueError('当前验收批次缺少本次生产总数')
            return batch

        production_total, accepted_total = QCService._validate_acceptance_quantities(
            work_order,
            production_quantity,
            accepted_quantity,
        )

        batch = QCAcceptanceBatch(
            work_order_id=work_order.id,
            production_quantity=production_total,
            accepted_quantity=accepted_total,
        )
        db.session.add(batch)
        db.session.flush()
        QCService.add_order_history(
            work_order,
            '创建验收批次',
            f'本次生产总数 {production_total:g}，质检合格件数 {accepted_total:g}',
        )
        return batch

    @staticmethod
    def can_cancel_acceptance_signature(user: User, work_order: QCWorkOrder, signer_role: str) -> bool:
        """Return whether the user can cancel one acceptance signature."""
        if work_order.status not in ['inspection_completed', 'accepted']:
            return False
        if work_order.acceptance_batches:
            batch = work_order.active_acceptance_batch
            if not batch or signer_role not in batch.signatures_by_role:
                return False
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_acceptance_rollback'):
            return signer_role in ['qc_controller', 'qc_inspector']
        if signer_role == 'qc_controller' and user.has_ai_cats_identity('controller', 'production') and work_order.controller_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_perform')
        if signer_role == 'qc_inspector' and user.has_ai_cats_identity('supplier', 'production') and work_order.inspector_id == user.id:
            return user.has_ai_cats_permission('qc_acceptance_perform')
        return False

    @staticmethod
    def get_workpiece_list(user: User, keyword: str = None, page: int = 1):
        """Return the workpiece-library list for the user scope."""
        query = QCWorkpiece.query

        if not QCService.can_access_workpiece_library(user):
            query = query.filter(False)

        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(
                or_(
                    QCWorkpiece.workpiece_code.ilike(like_keyword),
                    QCWorkpiece.workpiece_name.ilike(like_keyword),
                )
            )

        query = query.order_by(QCWorkpiece.created_at.desc())
        return query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_workpiece_choices(user: User) -> list[QCWorkpiece]:
        """Return selectable workpieces for the work-order form."""
        if not QCService.can_access_workpiece_library(user):
            return []
        return QCWorkpiece.query.order_by(QCWorkpiece.workpiece_code.asc(), QCWorkpiece.id.asc()).all()

    @staticmethod
    def get_workpiece(workpiece_id: int, user: User) -> Optional[QCWorkpiece]:
        """Return a single visible workpiece."""
        workpiece = QCWorkpiece.query.get(workpiece_id)
        if not workpiece:
            return None
        if not QCService.can_access_workpiece_library(user):
            return None
        return workpiece

    @staticmethod
    def get_work_order_list(user: User, status: str = None, keyword: str = None, page: int = 1):
        """Return the quality-control work-order list for the user scope."""
        query = QCWorkOrder.query

        if user.is_superadmin:
            query = query
        elif user.ai_cats_is_manager and QCService.can_access_quality_control(user):
            query = query.filter(QCWorkOrder.status != 'draft')
        else:
            if user.has_ai_cats_identity('controller', 'production') and QCService.can_access_quality_control(user):
                query = query.filter(QCWorkOrder.controller_id == user.id)
            else:
                query = query.filter(False)

        if status:
            query = query.filter(QCWorkOrder.status == status)

        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(
                or_(
                    QCWorkOrder.batch_no.ilike(like_keyword),
                    QCWorkOrder.workpiece_name.ilike(like_keyword),
                )
            )

        query = query.order_by(QCWorkOrder.created_at.desc())
        return query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_inspection_list(user: User, keyword: str = None, page: int = 1):
        """Return the inspection list for the user scope."""
        query = QCWorkOrder.query.filter(
            QCWorkOrder.status.in_(['qc_completed', 'inspection_pending'])
        )

        if not user.is_superadmin:
            if user.ai_cats_is_manager and QCService.can_access_inspection(user):
                query = query
            elif user.has_ai_cats_identity('supplier', 'production') and QCService.can_access_inspection(user):
                query = query.filter(QCWorkOrder.inspector_id == user.id)
            elif user.has_ai_cats_identity('controller', 'production') and QCService.can_access_inspection(user):
                query = query.filter(QCWorkOrder.controller_id == user.id)
            else:
                query = query.filter(False)

        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(
                or_(
                    QCWorkOrder.batch_no.ilike(like_keyword),
                    QCWorkOrder.workpiece_name.ilike(like_keyword),
                )
            )

        query = query.order_by(QCWorkOrder.qc_completed_at.desc())
        return query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def get_acceptance_list(user: User, keyword: str = None, page: int = 1):
        """Return the acceptance list for the user scope."""
        query = QCWorkOrder.query.filter(
            QCWorkOrder.status.in_(['inspection_completed', 'accepted'])
        )

        if not user.is_superadmin:
            if user.ai_cats_is_manager and QCService.can_access_acceptance(user):
                query = query
            elif user.has_ai_cats_identity('controller', 'production') and QCService.can_access_acceptance(user):
                query = query.filter(QCWorkOrder.controller_id == user.id)
            elif user.has_ai_cats_identity('supplier', 'production') and QCService.can_access_acceptance(user):
                query = query.filter(QCWorkOrder.inspector_id == user.id)
            else:
                query = query.filter(False)

        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(
                or_(
                    QCWorkOrder.batch_no.ilike(like_keyword),
                    QCWorkOrder.workpiece_name.ilike(like_keyword),
                )
            )

        query = query.order_by(QCWorkOrder.inspection_completed_at.desc())
        return query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False,
        )

    @staticmethod
    def create_workpiece(data: dict, creator_id: int, auto_commit: bool = True) -> QCWorkpiece:
        """Create a workpiece."""
        workpiece_code = (data.get('workpiece_code') or '').strip()
        workpiece_name = (data.get('workpiece_name') or '').strip()
        workpiece_type = normalize_qc_workpiece_type(data.get('workpiece_type'))

        if not workpiece_code:
            raise ValueError('工件编号不能为空')
        if not workpiece_name:
            raise ValueError('工件名称不能为空')

        existing = QCWorkpiece.query.filter_by(workpiece_code=workpiece_code).first()
        if existing:
            raise ValueError(f"工件编号 '{workpiece_code}' 已存在")

        workpiece = QCWorkpiece(
            workpiece_code=workpiece_code,
            workpiece_name=workpiece_name,
            workpiece_type=workpiece_type,
            stock_quantity=0,
            creator_id=creator_id,
        )
        db.session.add(workpiece)
        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return workpiece

    @staticmethod
    def update_workpiece(workpiece_id: int, data: dict, user: User) -> QCWorkpiece:
        """Update the basic workpiece fields."""
        workpiece = QCWorkpiece.query.get(workpiece_id)
        if not workpiece:
            raise ValueError('工件不存在')
        if not QCService.can_edit_workpiece(user, workpiece):
            raise ValueError('没有权限编辑此工件')

        workpiece_code = (data.get('workpiece_code') or '').strip()
        workpiece_name = (data.get('workpiece_name') or '').strip()
        workpiece_type = normalize_qc_workpiece_type(data.get('workpiece_type'))

        if not workpiece_code:
            raise ValueError('工件编号不能为空')
        if not workpiece_name:
            raise ValueError('工件名称不能为空')

        if workpiece_code != workpiece.workpiece_code:
            existing = QCWorkpiece.query.filter_by(workpiece_code=workpiece_code).first()
            if existing:
                raise ValueError(f"工件编号 '{workpiece_code}' 已存在")

        workpiece.workpiece_code = workpiece_code
        workpiece.workpiece_name = workpiece_name
        workpiece.workpiece_type = workpiece_type
        db.session.commit()
        return workpiece

    @staticmethod
    def sync_workpiece_attachments(
        workpiece_id: int,
        guide_items: list[dict],
        remark_items: list[dict],
        drawing_file,
        user: User,
        material_items: list[dict] | None = None,
        drawing_items: list[dict] | None = None,
        coa_template_file=None,
    ) -> QCWorkpiece:
        """Synchronize workpiece-library attachments from the form."""
        workpiece = QCWorkpiece.query.get(workpiece_id)
        if not workpiece:
            raise ValueError('工件不存在')
        if not QCService.can_edit_workpiece(user, workpiece):
            raise ValueError('没有权限编辑此工件')

        material_items = material_items or []
        drawing_items = drawing_items or []

        if not drawing_items and drawing_file and drawing_file.filename:
            drawing_items = [{'title': '图纸1', 'content': '', 'file': drawing_file}]

        existing_drawings = QCWorkpieceAttachment.query.filter_by(
            workpiece_id=workpiece.id,
            attach_type='drawing',
        ).order_by(QCWorkpieceAttachment.sort_order.asc(), QCWorkpieceAttachment.id.asc()).all()

        existing_materials = QCWorkpieceAttachment.query.filter_by(
            workpiece_id=workpiece.id,
            attach_type=QC_QUALITY_MATERIAL_ATTACHMENT_TYPE,
        ).order_by(QCWorkpieceAttachment.sort_order.asc(), QCWorkpieceAttachment.id.asc()).all()

        if workpiece.is_outsourced:
            for drawing in existing_drawings:
                if drawing.file_path:
                    QCService._remove_workpiece_file(workpiece.id, drawing.file_path)
                db.session.delete(drawing)

            if not material_items:
                raise ValueError('请至少添加一项质检材料')

            for idx, item in enumerate(material_items):
                title = (item.get('title') or '').strip() or f'质检材料{idx + 1}'
                content = (item.get('content') or '').strip()
                upload = item.get('file')

                if idx < len(existing_materials):
                    material = existing_materials[idx]
                    material.title = title
                    material.content = content
                    material.is_required = True
                    material.sort_order = idx
                    if upload and upload.filename:
                        QCService._replace_workpiece_attachment_file(
                            material,
                            upload,
                            QC_QUALITY_MATERIAL_ATTACHMENT_TYPE,
                        )
                    if not material.file_path:
                        raise ValueError('质检材料必须上传文件')
                else:
                    if not upload or not upload.filename:
                        raise ValueError('新增质检材料必须上传文件')
                    relative_path, file_type = QCService._save_file_for_workpiece_attachment(
                        file=upload,
                        workpiece_id=workpiece.id,
                        attach_type=QC_QUALITY_MATERIAL_ATTACHMENT_TYPE,
                    )
                    db.session.add(
                        QCWorkpieceAttachment(
                            workpiece_id=workpiece.id,
                            attach_type=QC_QUALITY_MATERIAL_ATTACHMENT_TYPE,
                            title=title,
                            content=content,
                            file_path=relative_path,
                            file_type=file_type,
                            is_required=True,
                            sort_order=idx,
                        )
                    )

            for redundant in existing_materials[len(material_items):]:
                if redundant.file_path:
                    QCService._remove_workpiece_file(workpiece.id, redundant.file_path)
                db.session.delete(redundant)
        else:
            for redundant in existing_materials:
                if redundant.file_path:
                    QCService._remove_workpiece_file(workpiece.id, redundant.file_path)
                db.session.delete(redundant)

            if not drawing_items:
                raise ValueError('请至少添加一项图纸')

            for idx, item in enumerate(drawing_items):
                title = (item.get('title') or '').strip() or f'图纸{idx + 1}'
                content = (item.get('content') or '').strip()
                upload = item.get('file')

                if idx < len(existing_drawings):
                    drawing = existing_drawings[idx]
                    drawing.title = title
                    drawing.content = content
                    drawing.is_required = True
                    drawing.sort_order = idx
                    if upload and upload.filename:
                        QCService._replace_workpiece_attachment_file(drawing, upload, 'drawing')
                    if not drawing.file_path:
                        raise ValueError('图纸必须上传文件')
                else:
                    if not upload or not upload.filename:
                        raise ValueError('新增图纸必须上传文件')
                    relative_path, file_type = QCService._save_file_for_workpiece_attachment(
                        file=upload,
                        workpiece_id=workpiece.id,
                        attach_type='drawing',
                    )
                    db.session.add(
                        QCWorkpieceAttachment(
                            workpiece_id=workpiece.id,
                            attach_type='drawing',
                            title=title,
                            content=content,
                            file_path=relative_path,
                            file_type=file_type,
                            is_required=True,
                            sort_order=idx,
                        )
                    )

            for redundant in existing_drawings[len(drawing_items):]:
                if redundant.file_path:
                    QCService._remove_workpiece_file(workpiece.id, redundant.file_path)
                db.session.delete(redundant)

        existing_guides = QCWorkpieceAttachment.query.filter(
            QCWorkpieceAttachment.workpiece_id == workpiece.id,
            QCWorkpieceAttachment.attach_type.in_(QC_GUIDE_ATTACHMENT_TYPES),
        ).order_by(QCWorkpieceAttachment.sort_order.asc(), QCWorkpieceAttachment.id.asc()).all()

        if not guide_items:
            raise ValueError('请至少添加一项作业指导书')

        for idx, item in enumerate(guide_items):
            title = normalize_qc_guide_title(item.get('title'), idx + 1)
            content = (item.get('content') or '').strip()
            upload = item.get('file')

            if idx < len(existing_guides):
                guide = existing_guides[idx]
                guide.attach_type = 'inspection_point'
                guide.title = title
                guide.content = content
                guide.is_required = True
                guide.sort_order = idx
                if upload and upload.filename:
                    QCService._replace_workpiece_attachment_file(guide, upload, 'inspection_point')
                if not guide.file_path:
                    raise ValueError('作业指导书必须上传文件')
            else:
                if not upload or not upload.filename:
                    raise ValueError('新增作业指导书必须上传文件')
                relative_path, file_type = QCService._save_file_for_workpiece_attachment(
                    file=upload,
                    workpiece_id=workpiece.id,
                    attach_type='inspection_point',
                )
                db.session.add(
                    QCWorkpieceAttachment(
                        workpiece_id=workpiece.id,
                        attach_type='inspection_point',
                        title=title,
                        content=content,
                        file_path=relative_path,
                        file_type=file_type,
                        is_required=True,
                        sort_order=idx,
                    )
                )

        for redundant in existing_guides[len(guide_items):]:
            if redundant.file_path:
                QCService._remove_workpiece_file(workpiece.id, redundant.file_path)
            db.session.delete(redundant)

        existing_coa_templates = QCWorkpieceAttachment.query.filter_by(
            workpiece_id=workpiece.id,
            attach_type='coa_template',
        ).order_by(QCWorkpieceAttachment.sort_order.asc(), QCWorkpieceAttachment.id.asc()).all()
        if coa_template_file and coa_template_file.filename:
            if existing_coa_templates:
                template = existing_coa_templates[0]
                template.title = 'COA报告模板'
                template.content = ''
                template.is_required = False
                template.sort_order = 0
                QCService._replace_workpiece_attachment_file(template, coa_template_file, 'coa_template')
                for redundant in existing_coa_templates[1:]:
                    if redundant.file_path:
                        QCService._remove_workpiece_file(workpiece.id, redundant.file_path)
                    db.session.delete(redundant)
            else:
                file_path, file_type = QCService._save_file_for_workpiece_attachment(
                    file=coa_template_file,
                    workpiece_id=workpiece.id,
                    attach_type='coa_template',
                )
                db.session.add(
                    QCWorkpieceAttachment(
                        workpiece_id=workpiece.id,
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
                    QCService._remove_workpiece_file(workpiece.id, redundant.file_path)
                db.session.delete(redundant)

        existing_remarks = QCWorkpieceAttachment.query.filter_by(
            workpiece_id=workpiece.id,
            attach_type='remark',
        ).order_by(QCWorkpieceAttachment.sort_order.asc(), QCWorkpieceAttachment.id.asc()).all()

        for idx, item in enumerate(remark_items):
            content = (item.get('content') or '').strip()
            is_required = bool(item.get('is_required'))
            upload = item.get('file')

            if idx < len(existing_remarks):
                remark = existing_remarks[idx]
                remark.content = content
                remark.is_required = is_required
                remark.sort_order = idx
                if upload and upload.filename:
                    QCService._replace_workpiece_attachment_file(remark, upload, 'remark')
            else:
                file_path = ''
                file_type = ''
                if upload and upload.filename:
                    file_path, file_type = QCService._save_file_for_workpiece_attachment(
                        file=upload,
                        workpiece_id=workpiece.id,
                        attach_type='remark',
                    )
                db.session.add(
                    QCWorkpieceAttachment(
                        workpiece_id=workpiece.id,
                        attach_type='remark',
                        title=None,
                        content=content,
                        file_path=file_path,
                        file_type=file_type,
                        is_required=is_required,
                        sort_order=idx,
                    )
                )

            if is_required and not content:
                raise ValueError('必填备注必须填写文字内容')

        for redundant in existing_remarks[len(remark_items):]:
            if redundant.file_path:
                QCService._remove_workpiece_file(workpiece.id, redundant.file_path)
            db.session.delete(redundant)

        db.session.commit()
        return workpiece

    @staticmethod
    def delete_workpiece(workpiece_id: int, user: User) -> bool:
        """Delete a workpiece and its physical files."""
        workpiece = QCWorkpiece.query.get(workpiece_id)
        if not workpiece:
            raise ValueError('工件不存在')
        if not QCService.can_delete_workpiece(user, workpiece):
            raise ValueError('没有权限删除此工件')
        if workpiece.work_orders:
            raise ValueError('已有工件订单引用该工件，不能删除')

        for attachment in workpiece.attachments:
            if attachment.file_path:
                QCService._remove_workpiece_file(workpiece.id, attachment.file_path)

        db.session.delete(workpiece)
        db.session.commit()
        return True

    @staticmethod
    def get_work_order(order_id: int, user: User) -> Optional[QCWorkOrder]:
        """Return a single visible work order."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            return None
        if not QCService.can_view_work_order(user, work_order):
            return None
        return work_order

    @staticmethod
    def create_work_order(
        data: dict,
        controller_id: int,
        status: str = 'qc_pending',
        allow_partial: bool = False,
        auto_commit: bool = True,
    ) -> QCWorkOrder:
        """Create a work order."""
        batch_no = (data.get('batch_no') or '').strip()
        quantity = data.get('quantity')
        workpiece_id = data.get('workpiece_id')
        workpiece_name = (data.get('workpiece_name') or '').strip()
        workpiece_type = normalize_qc_workpiece_type(data.get('workpiece_type'))

        selected_workpiece = None
        if workpiece_id:
            selected_workpiece = QCWorkpiece.query.get(int(workpiece_id))
            if not selected_workpiece:
                raise ValueError('请选择有效的工件')
            workpiece_name = selected_workpiece.workpiece_name
            workpiece_type = selected_workpiece.normalized_type

        if allow_partial:
            if not batch_no:
                batch_no = f"DRAFT-{controller_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2)}"
            if not workpiece_name:
                workpiece_name = '未命名草稿'
            try:
                quantity = float(quantity)
                if quantity <= 0:
                    quantity = 1.0
            except (TypeError, ValueError):
                quantity = 1.0
        else:
            if not batch_no:
                raise ValueError('批次编号不能为空')
            if not workpiece_name:
                raise ValueError('工件名称不能为空')
            try:
                quantity = float(quantity)
                if quantity <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError('生产数量必须为正数')

        existing = QCWorkOrder.query.filter_by(batch_no=batch_no).first()
        if existing:
            raise ValueError(f"批次编号 '{batch_no}' 已存在")

        work_order = QCWorkOrder(
            batch_no=batch_no,
            workpiece_id=selected_workpiece.id if selected_workpiece else None,
            workpiece_name=workpiece_name,
            workpiece_type=workpiece_type,
            quantity=quantity,
            controller_id=controller_id,
            status=status,
        )
        db.session.add(work_order)
        db.session.flush()
        QCService.add_order_history(
            work_order,
            '创建工件订单' if status != 'draft' else '保存工件订单草稿',
            f'批次 {work_order.batch_no}，工件 {work_order.workpiece_name}，数量 {float(work_order.quantity or 0):g}',
            User.query.get(controller_id),
        )
        if auto_commit:
            db.session.commit()
        return work_order

    @staticmethod
    def update_work_order(order_id: int, data: dict, user: User, allow_partial: bool = False) -> QCWorkOrder:
        """Update the basic work-order fields."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')

        if not QCService.can_edit_work_order(user, work_order):
            raise ValueError('没有权限编辑此订单')

        batch_no = (data.get('batch_no') or '').strip()
        quantity = data.get('quantity')
        workpiece_id = data.get('workpiece_id')
        workpiece_name = (data.get('workpiece_name') or '').strip()
        workpiece_type = normalize_qc_workpiece_type(data.get('workpiece_type') or work_order.workpiece_type)

        selected_workpiece = None
        if workpiece_id:
            selected_workpiece = QCWorkpiece.query.get(int(workpiece_id))
            if not selected_workpiece:
                raise ValueError('请选择有效的工件')
            workpiece_name = selected_workpiece.workpiece_name
            workpiece_type = selected_workpiece.normalized_type

        if allow_partial:
            batch_no = batch_no or work_order.batch_no
            workpiece_name = workpiece_name or work_order.workpiece_name
            try:
                quantity = float(quantity)
                if quantity <= 0:
                    quantity = work_order.quantity
            except (TypeError, ValueError):
                quantity = work_order.quantity
        else:
            if not batch_no:
                raise ValueError('批次编号不能为空')
            if not workpiece_name:
                raise ValueError('工件名称不能为空')
            try:
                quantity = float(quantity)
                if quantity <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError('生产数量必须为正数')

        if batch_no != work_order.batch_no:
            existing = QCWorkOrder.query.filter_by(batch_no=batch_no).first()
            if existing:
                raise ValueError(f"批次编号 '{batch_no}' 已存在")

        work_order.batch_no = batch_no
        work_order.quantity = quantity
        work_order.workpiece_type = workpiece_type
        if selected_workpiece:
            work_order.workpiece_id = selected_workpiece.id
            work_order.workpiece_name = selected_workpiece.workpiece_name
        else:
            work_order.workpiece_name = workpiece_name
        QCService.add_order_history(
            work_order,
            '编辑工件订单',
            f'批次 {work_order.batch_no}，工件 {work_order.workpiece_name}，数量 {float(work_order.quantity or 0):g}',
            user,
        )
        db.session.commit()
        return work_order

    @staticmethod
    def apply_workpiece_to_order(order_id: int, workpiece_id: int, user: User) -> QCWorkOrder:
        """Clone a workpiece-library snapshot into the work order."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')
        if not QCService.can_edit_work_order(user, work_order):
            raise ValueError('没有权限编辑此订单')

        workpiece = QCWorkpiece.query.get(workpiece_id)
        if not workpiece:
            raise ValueError('工件不存在')
        if not QCService.can_access_workpiece_library(user):
            raise ValueError('没有权限使用工件库')

        if workpiece.is_outsourced:
            if not workpiece.quality_material_attachments:
                raise ValueError('所选外采工件未配置质检材料')
            for idx, material in enumerate(workpiece.quality_material_attachments, start=1):
                if not material.file_path:
                    raise ValueError(f'请完善质检材料{idx}')
        else:
            if not workpiece.drawing_attachments:
                raise ValueError('所选工件未配置图纸')
            for idx, drawing in enumerate(workpiece.drawing_attachments, start=1):
                if not drawing.file_path:
                    raise ValueError(f'请完善图纸{idx}')
        if not workpiece.guide_attachments:
            raise ValueError('所选工件未配置作业指导书')

        QCService._apply_workpiece_snapshot(work_order, workpiece)
        QCService.add_order_history(
            work_order,
            '应用工件库快照',
            f'来源工件 {workpiece.workpiece_code}，类型 {workpiece.workpiece_type_display}',
            user,
        )
        db.session.commit()
        return work_order

    @staticmethod
    def sync_work_order_attachments(
        order_id: int,
        point_items: list[dict],
        remark_items: list[dict],
        drawing_file,
        instruction_file,
        user: User,
        allow_partial: bool = False,
    ) -> QCWorkOrder:
        """Synchronize edited attachment data from the legacy work-order form."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')

        if not QCService.can_edit_work_order(user, work_order):
            raise ValueError('没有权限编辑此订单')

        for attach_type, upload in (('drawing', drawing_file), ('instruction', instruction_file)):
            existing = QCWorkOrderAttachment.query.filter_by(
                work_order_id=work_order.id,
                attach_type=attach_type,
            ).order_by(QCWorkOrderAttachment.id.asc()).first()

            if upload and upload.filename:
                if existing:
                    QCService._replace_attachment_file(existing, upload, attach_type)
                else:
                    relative_path, file_type = QCService._save_file_for_attachment(
                        file=upload,
                        work_order_id=work_order.id,
                        attach_type=attach_type,
                    )
                    db.session.add(
                        QCWorkOrderAttachment(
                            work_order_id=work_order.id,
                            attach_type=attach_type,
                            title='图纸' if attach_type == 'drawing' else '作业指导书',
                            content='',
                            file_path=relative_path,
                            file_type=file_type,
                            is_required=True,
                            sort_order=0,
                        )
                    )

        existing_points = QCWorkOrderAttachment.query.filter(
            QCWorkOrderAttachment.work_order_id == work_order.id,
            QCWorkOrderAttachment.attach_type.in_(QC_GUIDE_ATTACHMENT_TYPES),
        ).order_by(QCWorkOrderAttachment.sort_order.asc(), QCWorkOrderAttachment.id.asc()).all()

        if not point_items and not allow_partial:
            raise ValueError('请至少保留一项作业指导书')

        for idx, item in enumerate(point_items):
            title = normalize_qc_guide_title(item.get('title'), idx + 1)
            content = (item.get('content') or '').strip()
            upload = item.get('file')

            if idx < len(existing_points):
                point = existing_points[idx]
                point.attach_type = 'inspection_point'
                point.title = title
                point.content = content
                point.is_required = True
                point.sort_order = idx
                if upload and upload.filename:
                    QCService._replace_attachment_file(point, upload, 'inspection_point')
                if not point.file_path and not allow_partial:
                    raise ValueError('作业指导书必须上传文件')
            else:
                if (not upload or not upload.filename) and not allow_partial:
                    raise ValueError('新增作业指导书必须上传文件')
                relative_path = ''
                file_type = ''
                if upload and upload.filename:
                    relative_path, file_type = QCService._save_file_for_attachment(
                        file=upload,
                        work_order_id=work_order.id,
                        attach_type='inspection_point',
                    )
                db.session.add(
                    QCWorkOrderAttachment(
                        work_order_id=work_order.id,
                        attach_type='inspection_point',
                        title=title,
                        content=content,
                        file_path=relative_path,
                        file_type=file_type,
                        is_required=True,
                        sort_order=idx,
                    )
                )

        for redundant in existing_points[len(point_items):]:
            if redundant.file_path:
                QCService._remove_file(work_order.id, redundant.file_path)
            db.session.delete(redundant)

        existing_remarks = QCWorkOrderAttachment.query.filter_by(
            work_order_id=work_order.id,
            attach_type='remark',
        ).order_by(QCWorkOrderAttachment.sort_order.asc(), QCWorkOrderAttachment.id.asc()).all()

        for idx, item in enumerate(remark_items):
            content = (item.get('content') or '').strip()
            is_required = bool(item.get('is_required'))
            upload = item.get('file')

            if idx < len(existing_remarks):
                remark = existing_remarks[idx]
                remark.content = content
                remark.is_required = is_required
                remark.sort_order = idx
                if upload and upload.filename:
                    QCService._replace_attachment_file(remark, upload, 'remark')
            else:
                file_path = ''
                file_type = ''
                if upload and upload.filename:
                    file_path, file_type = QCService._save_file_for_attachment(
                        file=upload,
                        work_order_id=work_order.id,
                        attach_type='remark',
                    )
                db.session.add(
                    QCWorkOrderAttachment(
                        work_order_id=work_order.id,
                        attach_type='remark',
                        title=None,
                        content=content,
                        file_path=file_path,
                        file_type=file_type,
                        is_required=is_required,
                        sort_order=idx,
                    )
                )

            if is_required and not content and not allow_partial:
                raise ValueError('必填备注必须填写文字内容')

        for redundant in existing_remarks[len(remark_items):]:
            if redundant.file_path:
                QCService._remove_file(work_order.id, redundant.file_path)
            db.session.delete(redundant)

        db.session.commit()
        return work_order

    @staticmethod
    def delete_work_order(order_id: int, user: User) -> bool:
        """Delete a work order and its related resources."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')

        if not QCService.can_delete_work_order(user, work_order):
            raise ValueError('没有权限删除此订单')

        QCService._delete_inspection_report_files(work_order)
        QCService._delete_order_section_files(work_order)
        for attachment in work_order.attachments:
            if attachment.file_path:
                QCService._remove_file(work_order.id, attachment.file_path)

        db.session.delete(work_order)
        db.session.commit()
        return True

    @staticmethod
    def add_attachment(work_order_id: int, file, attach_type: str, title: str = None,
                       content: str = None, is_required: bool = True,
                       sort_order: int = 0, user: User = None,
                       auto_commit: bool = True) -> QCWorkOrderAttachment:
        """Add a work-order attachment."""
        work_order = QCWorkOrder.query.get(work_order_id)
        if not work_order:
            raise ValueError('工件订单不存在')

        if user and not QCService.can_edit_work_order(user, work_order):
            raise ValueError('没有权限编辑此订单')

        relative_path, file_type = QCService._save_file_for_attachment(file, work_order_id, attach_type)

        attachment = QCWorkOrderAttachment(
            work_order_id=work_order_id,
            attach_type=attach_type,
            title=title,
            content=content,
            file_path=relative_path,
            file_type=file_type,
            is_required=is_required,
            sort_order=sort_order,
        )
        db.session.add(attachment)
        if auto_commit:
            db.session.commit()
        return attachment

    @staticmethod
    def delete_attachment(attachment_id: int, user: User) -> bool:
        """Delete an attachment."""
        attachment = QCWorkOrderAttachment.query.get(attachment_id)
        if not attachment:
            raise ValueError('附件不存在')

        work_order = QCWorkOrder.query.get(attachment.work_order_id)
        if not QCService.can_edit_work_order(user, work_order):
            raise ValueError('没有权限删除此附件')

        QCService._remove_file(work_order.id, attachment.file_path)
        db.session.delete(attachment)
        db.session.commit()
        return True

    @staticmethod
    def update_attachment_meta(attachment_id: int, title: str = None, content: str = None,
                               is_required: bool = None, user: User = None) -> QCWorkOrderAttachment:
        """Update attachment metadata."""
        attachment = QCWorkOrderAttachment.query.get(attachment_id)
        if not attachment:
            raise ValueError('附件不存在')

        work_order = QCWorkOrder.query.get(attachment.work_order_id)
        if user and not QCService.can_edit_work_order(user, work_order):
            raise ValueError('没有权限编辑此附件')

        if title is not None:
            attachment.title = title
        if content is not None:
            attachment.content = content
        if is_required is not None:
            attachment.is_required = is_required

        db.session.commit()
        return attachment

    @staticmethod
    def complete_quality_control(order_id: int, inspector_id: int, user: User) -> QCWorkOrder:
        """Complete quality control and move the work order forward."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')

        if not QCService.can_edit_work_order(user, work_order):
            raise ValueError('没有权限执行此操作')

        if work_order.status not in ['draft', 'qc_pending', 'rejected']:
            raise ValueError('当前订单状态不允许完成质控')

        inspector = User.query.get(inspector_id)
        if not inspector:
            raise ValueError('请选择有效的供应商')
        if not inspector.is_active:
            raise ValueError('请选择已激活的供应商')
        if not inspector.has_ai_cats_identity('supplier', 'production'):
            raise ValueError('请选择具有配件生产权限的供应商')
        if inspector.id == work_order.controller_id:
            raise ValueError('质量控制人与供应商必须由不同用户担任')

        primary_materials = work_order.primary_material_attachments
        guides = work_order.guide_attachments

        if work_order.is_outsourced:
            if not primary_materials:
                raise ValueError('请上传质检材料')
            for idx, material in enumerate(primary_materials, start=1):
                if not material.file_path:
                    raise ValueError(f'请完善质检材料{idx}')
        elif not primary_materials or not primary_materials[0].file_path:
            raise ValueError('请上传图纸')
        if not guides:
            raise ValueError('请至少添加一项作业指导书')

        for idx, guide in enumerate(guides, start=1):
            if guide.is_required and (not guide.display_title or not guide.file_path):
                raise ValueError(f'请完善作业指导书{idx}')

        remarks = QCWorkOrderAttachment.query.filter_by(
            work_order_id=work_order.id, attach_type='remark'
        ).all()
        for remark in remarks:
            if remark.is_required and not (remark.content or '').strip():
                raise ValueError('请完善所有必填备注')

        work_order.status = 'qc_completed'
        work_order.inspector_id = inspector_id
        work_order.qc_completed_at = datetime.now()
        work_order.inspection_completed_at = None
        work_order.accepted_at = None
        work_order.rejected_at = None
        work_order.rejection_reason = None
        QCService.add_order_history(
            work_order,
            '完成质量控制',
            f'已分配给 {inspector.real_name or inspector.username}，进入质量检测',
            user,
        )
        db.session.commit()
        return work_order

    @staticmethod
    def submit_inspection(order_id: int, results: list[dict], user: User, final_submit: bool = True) -> QCWorkOrder:
        """Save or submit inspection results."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')

        if not QCService.can_inspect_work_order(user, work_order):
            raise ValueError('没有权限执行质检')

        if work_order.status not in ['qc_completed', 'inspection_pending']:
            raise ValueError('当前订单状态不允许提交质检')

        attachments = QCWorkOrderAttachment.query.filter_by(work_order_id=work_order.id).order_by(
            QCWorkOrderAttachment.sort_order.asc(),
            QCWorkOrderAttachment.id.asc(),
        ).all()
        attachment_ids = {attachment.id for attachment in attachments}
        existing_records = {
            record.attachment_id: record
            for record in QCInspectionRecord.query.filter_by(work_order_id=work_order.id).all()
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
            raise ValueError('存在重复的附件检验结果，请重新提交')

        touched_records: dict[int, QCInspectionRecord] = {}

        for item in results:
            attachment_id = item.get('attachment_id')
            attachment = next(attachment for attachment in attachments if attachment.id == attachment_id)
            result = (item.get('result') or '').strip()
            remark = (item.get('remark') or '').strip() or None
            report_file = item.get('report_file')
            record = existing_records.get(attachment_id)

            if not record:
                record = QCInspectionRecord(
                    work_order_id=work_order.id,
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
                report_path, report_type = QCService._save_file_for_attachment(
                    file=report_file,
                    work_order_id=work_order.id,
                    attach_type='report',
                )
                record.report_file_path = report_path
                record.report_file_type = report_type
                record.report_original_name = report_file.filename
                if old_report_path and old_report_path != report_path:
                    QCService._remove_file(work_order.id, old_report_path)

            touched_records[attachment_id] = record

        if final_submit:
            unresolved = []
            has_fail = False

            for attachment in attachments:
                record = touched_records.get(attachment.id) or existing_records.get(attachment.id)
                if not record:
                    unresolved.append(attachment.display_title)
                    continue
                if record.result not in ['pass', 'fail']:
                    unresolved.append(attachment.display_title)
                    continue
                if attachment.requires_report and not record.report_file_path:
                    report_label = (attachment.report_label or '合格报告').replace('（必选）', '')
                    raise ValueError(f'{attachment.display_title} 必须上传{report_label}后才能提交')
                if record.result == 'fail':
                    has_fail = True

            if unresolved:
                raise ValueError('请完成所有项目的勾选后再提交')

            work_order.accepted_at = None
            for signature in list(work_order.signatures):
                db.session.delete(signature)

            if has_fail:
                work_order.status = 'rejected'
                work_order.rejected_at = datetime.now()
                work_order.inspection_completed_at = None
                QCService.add_order_history(
                    work_order,
                    '提交质量检测',
                    '质检不合格，退回质量控制流程',
                    user,
                )
            else:
                work_order.status = 'inspection_completed'
                work_order.inspection_completed_at = datetime.now()
                work_order.rejected_at = None
                work_order.rejection_reason = None
                QCService.add_order_history(
                    work_order,
                    '提交质量检测',
                    '质检合格，进入验收确认',
                    user,
                )
        else:
            if touched_records or existing_records:
                work_order.status = 'inspection_pending'
                work_order.inspection_completed_at = None
                QCService.add_order_history(
                    work_order,
                    '保存质检草稿',
                    f'已保存 {len(touched_records)} 项质检结果',
                    user,
                )

        db.session.commit()
        return work_order

    @staticmethod
    def sign_acceptance(
        order_id: int,
        user: User,
        signer_role: Optional[str] = None,
        production_quantity=None,
        accepted_quantity=None,
    ) -> dict:
        """Sign one acceptance role for the current user."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')

        if work_order.status not in ['inspection_completed', 'accepted']:
            raise ValueError('当前订单尚未进入验收确认阶段')
        if work_order.status == 'accepted' and work_order.remaining_acceptance_quantity <= 1e-9:
            raise ValueError('该订单已完成全部计划数量的验收')

        eligible_roles = QCService.eligible_acceptance_signer_roles(user, work_order)
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

        batch = QCService._ensure_acceptance_batch(
            work_order,
            production_quantity=production_quantity,
            accepted_quantity=accepted_quantity,
        )

        existing = QCAcceptanceSignature.query.filter_by(
            work_order_id=work_order.id,
            acceptance_batch_id=batch.id,
            signer_role=signer_role,
        ).first()
        if existing:
            raise ValueError('该角色已完成验收确认，无需重复操作')

        signature = QCAcceptanceSignature(
            work_order_id=work_order.id,
            acceptance_batch_id=batch.id,
            signer_id=user.id,
            signer_role=signer_role,
        )
        db.session.add(signature)
        db.session.flush()
        QCService.add_order_history(
            work_order,
            '验收确认',
            f'{signature.signer_role_display}已确认',
            user,
        )

        signatures = QCAcceptanceSignature.query.filter_by(acceptance_batch_id=batch.id).all()
        roles_signed = {signature.signer_role for signature in signatures}
        if 'qc_controller' in roles_signed and 'qc_inspector' in roles_signed:
            batch.completed_at = datetime.now()
            QCService._post_acceptance_batch_inventory(batch, user)
            delivered = work_order.actual_delivered_quantity
            planned = float(work_order.quantity or 0)
            if delivered + 1e-9 >= planned:
                work_order.status = 'accepted'
                work_order.accepted_at = datetime.now()
                work_order.inventory_posted_at = datetime.now()
                QCService.add_order_history(
                    work_order,
                    '验收完成',
                    f'累计实际交付 {delivered:g} / 计划生产 {planned:g}，订单质检已完成',
                    user,
                )
                message = '双方已确认，质检已完成'
            else:
                work_order.status = 'inspection_completed'
                work_order.accepted_at = None
                QCService.add_order_history(
                    work_order,
                    '阶段验收完成',
                    f'本批合格 {float(batch.accepted_quantity or 0):g}，累计实际交付 {delivered:g} / 计划生产 {planned:g}',
                    user,
                )
                message = '本次验收已确认，仍有剩余数量待验收'
            db.session.commit()
            return {'completed': delivered + 1e-9 >= planned, 'message': message}

        db.session.commit()
        return {'completed': False, 'message': '验收确认已提交，等待另一方确认'}

    @staticmethod
    def cancel_acceptance_signature(order_id: int, signer_role: str, user: User) -> QCWorkOrder:
        """Cancel one acceptance signature without rolling the order back to earlier modules."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')
        if signer_role not in ['qc_controller', 'qc_inspector']:
            raise ValueError('无效的确认角色')
        if not QCService.can_cancel_acceptance_signature(user, work_order, signer_role):
            raise ValueError('没有权限取消该验收确认')

        batch = work_order.active_acceptance_batch
        query = QCAcceptanceSignature.query.filter_by(
            work_order_id=work_order.id,
            signer_role=signer_role,
        )
        if batch:
            query = query.filter_by(acceptance_batch_id=batch.id)
        signature = query.order_by(QCAcceptanceSignature.id.desc()).first()
        if not signature:
            raise ValueError('该角色尚未完成验收确认')

        role_display = signature.signer_role_display
        db.session.delete(signature)
        db.session.flush()
        if batch and not QCAcceptanceSignature.query.filter_by(acceptance_batch_id=batch.id).first():
            db.session.delete(batch)
        QCService.add_order_history(
            work_order,
            '取消验收确认',
            f'{role_display}确认已取消',
            user,
        )
        db.session.commit()
        return work_order

    @staticmethod
    def rollback_acceptance(order_id: int, target: str, reason: str, user: User) -> QCWorkOrder:
        """Roll back acceptance and return the workflow."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')

        if not QCService.can_rollback_work_order(user, work_order):
            raise ValueError('没有权限执行回退操作')

        if work_order.status not in ['inspection_completed', 'accepted']:
            raise ValueError('当前订单状态不允许回退')

        if target not in ['qc', 'inspection']:
            raise ValueError('无效的回退目标')

        if not reason or not reason.strip():
            raise ValueError('请填写回退原因')

        QCService._reverse_inventory_if_posted(work_order, user)

        QCAcceptanceBatch.query.filter_by(work_order_id=work_order.id).delete()
        QCAcceptanceSignature.query.filter_by(work_order_id=work_order.id).delete()
        work_order.accepted_at = None
        work_order.inventory_posted_at = None

        if target == 'qc':
            QCService._delete_inspection_report_files(work_order)
            QCInspectionRecord.query.filter_by(work_order_id=work_order.id).delete()
            work_order.status = 'qc_pending'
            work_order.inspection_completed_at = None
        else:
            work_order.status = 'inspection_pending'
            work_order.inspection_completed_at = None

        work_order.rejection_reason = reason.strip()
        QCService.add_order_history(
            work_order,
            '验收回退',
            f'回退至{"质量控制" if target == "qc" else "质量检测"}：{reason.strip()}',
            user,
        )
        db.session.commit()
        return work_order

    @staticmethod
    def get_dashboard_stats(user: User) -> dict:
        """Return dashboard statistics for the current user."""
        base_query = QCWorkOrder.query

        if not user.is_superadmin:
            if user.ai_cats_is_manager and (
                QCService.can_access_quality_control(user)
                or QCService.can_access_inspection(user)
                or QCService.can_access_acceptance(user)
            ):
                base_query = base_query.filter(QCWorkOrder.status != 'draft')
            elif user.has_ai_cats_identity('controller', 'production'):
                base_query = base_query.filter(QCWorkOrder.controller_id == user.id)
            elif user.has_ai_cats_identity('supplier', 'production'):
                base_query = base_query.filter(QCWorkOrder.inspector_id == user.id)
            else:
                return {
                    'qc_pending': 0,
                    'qc_completed': 0,
                    'inspection_pending': 0,
                    'inspection_completed': 0,
                    'accepted': 0,
                    'rejected': 0,
                }

        stats = {}
        for status in ['qc_pending', 'qc_completed', 'inspection_pending', 'inspection_completed', 'accepted', 'rejected']:
            stats[status] = base_query.filter(QCWorkOrder.status == status).count()

        return stats

    @staticmethod
    def get_recent_work_orders(user: User, limit: int = 5) -> list[QCWorkOrder]:
        """Return recent work orders visible to the current user."""
        query = QCWorkOrder.query

        if user.is_superadmin:
            query = query
        elif user.ai_cats_is_manager and (
            QCService.can_access_quality_control(user)
            or QCService.can_access_inspection(user)
            or QCService.can_access_acceptance(user)
        ):
            query = query.filter(QCWorkOrder.status != 'draft')
        elif user.has_ai_cats_identity('controller', 'production'):
            query = query.filter(QCWorkOrder.controller_id == user.id)
        elif user.has_ai_cats_identity('supplier', 'production'):
            query = query.filter(QCWorkOrder.inspector_id == user.id)
        else:
            return []

        return query.order_by(QCWorkOrder.created_at.desc()).limit(limit).all()
