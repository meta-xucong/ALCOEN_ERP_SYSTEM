"""QC service layer."""


import os
import secrets
from datetime import datetime
from typing import Optional

from flask import current_app
from sqlalchemy import or_, func
from werkzeug.utils import secure_filename

from app import db
from app.models import QCWorkOrder, QCWorkOrderAttachment, QCInspectionRecord, QCAcceptanceSignature, User


class QCService:
    """QC service operations."""
    
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'pdf'}

    _ATTACH_SUBFOLDER_MAP = {
        'drawing': 'drawings',
        'instruction': 'instructions',
        'inspection_point': 'inspection_points',
        'remark': 'remarks',
    }
    
    @staticmethod
    def _allowed_file(filename: str) -> bool:
        """Check whether the uploaded filename extension is allowed."""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in QCService.ALLOWED_EXTENSIONS
    
    @staticmethod
    def _get_file_extension(filename: str) -> str:
        """Return the lowercase file extension."""
        if '.' in filename:
            return filename.rsplit('.', 1)[1].lower()
        return ''
    
    @staticmethod
    def _save_uploaded_file(file, work_order_id: int, subfolder: str) -> str:
        """Save an uploaded file under the work-order QC upload directory."""
        upload_dir = os.path.join(
            current_app.root_path, '..', 'static', 'uploads', 'qc', str(work_order_id), subfolder
        )
        os.makedirs(upload_dir, exist_ok=True)
        
        safe_name = secure_filename(file.filename)
        ext = QCService._get_file_extension(safe_name) or 'bin'
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}_{safe_name}"
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        
        return f"{subfolder}/{filename}"
    
    @staticmethod
    def _remove_file(work_order_id: int, relative_path: str):
        """Delete the physical uploaded file when it exists."""
        filepath = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'qc', str(work_order_id), relative_path)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    @staticmethod
    def _save_file_for_attachment(file, work_order_id: int, attach_type: str) -> tuple[str, str]:
        """Persist an attachment file and return its relative path and type."""
        if not file or not file.filename:
            raise ValueError('璇烽€夋嫨瑕佷笂浼犵殑鏂囦欢')
        if not QCService._allowed_file(file.filename):
            raise ValueError('涓嶆敮鎸佺殑鏂囦欢鏍煎紡锛岃涓婁紶鍥剧墖鎴朠DF')

        subfolder = QCService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others')
        relative_path = QCService._save_uploaded_file(file, work_order_id, subfolder)
        file_type = QCService._get_file_extension(file.filename)
        return relative_path, file_type

    @staticmethod
    def _replace_attachment_file(attachment: QCWorkOrderAttachment, file, attach_type: str) -> None:
        """Replace an attachment file and update stored metadata."""
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
    
    # ==================== 鏉冮檺鍒ゆ柇 ====================
    
    @staticmethod
    def can_view_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can view the work order."""
        if work_order.status == 'draft':
            return user.is_superadmin or work_order.controller_id == user.id
        if user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']:
            return True
        if user.role.code == 'qc_controller' and work_order.controller_id == user.id:
            return True
        if user.role.code == 'qc_inspector' and work_order.inspector_id == user.id:
            return True
        return False
    
    @staticmethod
    def can_edit_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can edit the work order."""
        if work_order.status == 'draft':
            return user.is_superadmin or (user.role.code == 'qc_controller' and work_order.controller_id == user.id)
        if user.is_superadmin:
            return True
        if user.role.code == 'qc_controller' and work_order.controller_id == user.id:
            return work_order.status in ['qc_pending', 'rejected']
        return False

    @staticmethod
    def can_delete_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can delete the work order."""
        if user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']:
            return True
        if user.role.code == 'qc_controller' and work_order.controller_id == user.id:
            return True
        return False
    
    @staticmethod
    def can_inspect_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can perform inspection on the work order."""
        if user.is_superadmin:
            return True
        if user.role.code == 'qc_inspector' and work_order.inspector_id == user.id:
            return work_order.status in ['qc_completed', 'inspection_pending']
        return False
    
    @staticmethod
    def can_accept_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can sign acceptance for the work order."""
        if user.is_superadmin:
            return True
        if user.role.code == 'qc_controller' and work_order.controller_id == user.id:
            return work_order.status == 'inspection_completed'
        if user.role.code == 'qc_inspector' and work_order.inspector_id == user.id:
            return work_order.status == 'inspection_completed'
        return False
    
    @staticmethod
    def can_rollback_work_order(user: User, work_order: QCWorkOrder) -> bool:
        """Return whether the user can roll back acceptance for the work order."""
        if user.is_superadmin:
            return True
        if user.role.code == 'qc_controller' and work_order.controller_id == user.id:
            return work_order.status in ['inspection_completed', 'accepted']
        return False
    
    # ==================== 鍒楄〃鏌ヨ ====================
    
    @staticmethod
    def get_work_order_list(user: User, status: str = None, keyword: str = None, page: int = 1):
        """Return the quality control work-order list for the user scope."""
        query = QCWorkOrder.query
        
        if user.is_superadmin:
            query = query
        elif user.role.code in ['general_manager', 'gm_assistant']:
            # 鑽夌浠呭垱寤轰汉鍜岃秴绾х鐞嗗憳鍙
            query = query.filter(QCWorkOrder.status != 'draft')
        else:
            if user.role.code == 'qc_controller':
                query = query.filter(QCWorkOrder.controller_id == user.id)
            elif user.role.code == 'qc_inspector':
                query = query.filter(False)
            else:
                query = query.filter(False)
        
        if status:
            query = query.filter(QCWorkOrder.status == status)
        
        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(or_(
                QCWorkOrder.batch_no.ilike(like_keyword),
                QCWorkOrder.workpiece_name.ilike(like_keyword)
            ))
        
        query = query.order_by(QCWorkOrder.created_at.desc())
        pagination = query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False
        )
        return pagination
    
    @staticmethod
    def get_inspection_list(user: User, keyword: str = None, page: int = 1):
        """Return the inspection list for the user scope."""
        query = QCWorkOrder.query.filter(
            QCWorkOrder.status.in_(['qc_completed', 'inspection_pending'])
        )
        
        if not (user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']):
            if user.role.code == 'qc_inspector':
                query = query.filter(QCWorkOrder.inspector_id == user.id)
            elif user.role.code == 'qc_controller':
                query = query.filter(QCWorkOrder.controller_id == user.id)
            else:
                query = query.filter(False)
        
        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(or_(
                QCWorkOrder.batch_no.ilike(like_keyword),
                QCWorkOrder.workpiece_name.ilike(like_keyword)
            ))
        
        query = query.order_by(QCWorkOrder.qc_completed_at.desc())
        pagination = query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False
        )
        return pagination
    
    @staticmethod
    def get_acceptance_list(user: User, keyword: str = None, page: int = 1):
        """Return the acceptance list for the user scope."""
        query = QCWorkOrder.query.filter(
            QCWorkOrder.status.in_(['inspection_completed', 'accepted'])
        )
        
        if not (user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']):
            if user.role.code == 'qc_controller':
                query = query.filter(QCWorkOrder.controller_id == user.id)
            elif user.role.code == 'qc_inspector':
                query = query.filter(QCWorkOrder.inspector_id == user.id)
            else:
                query = query.filter(False)
        
        if keyword:
            like_keyword = f'%{keyword}%'
            query = query.filter(or_(
                QCWorkOrder.batch_no.ilike(like_keyword),
                QCWorkOrder.workpiece_name.ilike(like_keyword)
            ))
        
        query = query.order_by(QCWorkOrder.inspection_completed_at.desc())
        pagination = query.paginate(
            page=page,
            per_page=current_app.config.get('ITEMS_PER_PAGE', 20),
            error_out=False
        )
        return pagination
    
    # ==================== CRUD ====================
    
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











        batch_no = data.get('batch_no', '').strip()
        workpiece_name = data.get('workpiece_name', '').strip()
        quantity = data.get('quantity')

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
                raise ValueError('鎵规缂栧彿涓嶈兘涓虹┖')
            if not workpiece_name:
                raise ValueError('宸ヤ欢鍚嶇О涓嶈兘涓虹┖')

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
            workpiece_name=workpiece_name,
            quantity=quantity,
            controller_id=controller_id,
            status=status
        )
        db.session.add(work_order)
        if auto_commit:
            db.session.commit()
        else:
            db.session.flush()
        return work_order
    
    @staticmethod
    def update_work_order(order_id: int, data: dict, user: User, allow_partial: bool = False) -> QCWorkOrder:
        """Update the basic work-order fields."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')
        
        if not QCService.can_edit_work_order(user, work_order):
            raise ValueError('没有权限编辑此订单')
        
        batch_no = data.get('batch_no', '').strip()
        workpiece_name = data.get('workpiece_name', '').strip()
        quantity = data.get('quantity')

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
                raise ValueError('鎵规缂栧彿涓嶈兘涓虹┖')
            if not workpiece_name:
                raise ValueError('宸ヤ欢鍚嶇О涓嶈兘涓虹┖')
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
        work_order.workpiece_name = workpiece_name
        work_order.quantity = quantity
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
        """Synchronize edited attachment data from the work-order form."""
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

        # 妫€娴嬬偣锛堟湁搴忛泦鍚堬級
        existing_points = QCWorkOrderAttachment.query.filter_by(
            work_order_id=work_order.id,
            attach_type='inspection_point',
        ).order_by(QCWorkOrderAttachment.sort_order.asc(), QCWorkOrderAttachment.id.asc()).all()

        if not point_items and not allow_partial:
            raise ValueError('璇疯嚦灏戜繚鐣欎竴涓娴嬬偣')

        for idx, item in enumerate(point_items):
            title = (item.get('title') or '').strip()
            content = (item.get('content') or '').strip()
            upload = item.get('file')

            if not title and not allow_partial:
                raise ValueError('妫€娴嬬偣鍚嶇О涓嶈兘涓虹┖')

            if idx < len(existing_points):
                point = existing_points[idx]
                point.title = title or point.title
                point.content = content
                point.is_required = True
                point.sort_order = idx
                if upload and upload.filename:
                    QCService._replace_attachment_file(point, upload, 'inspection_point')
                if not point.file_path and not allow_partial:
                    raise ValueError('妫€娴嬬偣蹇呴』涓婁紶鍥剧墖')
            else:
                if (not upload or not upload.filename) and not allow_partial:
                    raise ValueError('鏂板妫€娴嬬偣蹇呴』涓婁紶鍥剧墖')
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
                        title=title or f'妫€娴嬬偣{idx + 1}',
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
                raise ValueError('蹇呭～澶囨敞蹇呴』濉啓鏂囧瓧鍐呭')

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
        
        # 鍒犻櫎鐗╃悊闄勪欢鏂囦欢
        for attach in work_order.attachments:
            QCService._remove_file(work_order.id, attach.file_path)
        
        db.session.delete(work_order)
        db.session.commit()
        return True
    
    # ==================== 闄勪欢绠＄悊 ====================
    
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
        
        if not file or not file.filename:
            raise ValueError('璇烽€夋嫨瑕佷笂浼犵殑鏂囦欢')
        
        if not QCService._allowed_file(file.filename):
            raise ValueError('涓嶆敮鎸佺殑鏂囦欢鏍煎紡锛岃涓婁紶鍥剧墖鎴朠DF')
        
        subfolder = QCService._ATTACH_SUBFOLDER_MAP.get(attach_type, 'others')
        relative_path = QCService._save_uploaded_file(file, work_order_id, subfolder)
        
        attachment = QCWorkOrderAttachment(
            work_order_id=work_order_id,
            attach_type=attach_type,
            title=title,
            content=content,
            file_path=relative_path,
            file_type=QCService._get_file_extension(file.filename),
            is_required=is_required,
            sort_order=sort_order
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

    # ==================== 鐘舵€佹祦杞?====================
    
    @staticmethod
    def complete_quality_control(order_id: int, inspector_id: int, user: User) -> QCWorkOrder:
        """Complete quality control and move the work order forward."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')
        
        if not (user.is_superadmin or (user.role.code == 'qc_controller' and work_order.controller_id == user.id)):
            raise ValueError('没有权限执行此操作')
        
        if work_order.status not in ['draft', 'qc_pending', 'rejected']:
            raise ValueError('当前订单状态不允许完成质控')
        
        inspector = User.query.get(inspector_id)
        if not inspector:
            raise ValueError('请选择有效的质量检测员')
        if not inspector.is_active:
            raise ValueError('请选择已激活的质量检测员')
        if not inspector.role or inspector.role.code != 'qc_inspector':
            raise ValueError('请选择质量检测员角色用户')
        
        # 妫€鏌ュ繀濉」鏄惁瀹屾暣
        drawing = QCWorkOrderAttachment.query.filter_by(
            work_order_id=work_order.id, attach_type='drawing'
        ).first()
        instruction = QCWorkOrderAttachment.query.filter_by(
            work_order_id=work_order.id, attach_type='instruction'
        ).first()
        inspection_points = QCWorkOrderAttachment.query.filter_by(
            work_order_id=work_order.id, attach_type='inspection_point'
        ).all()
        
        if not drawing:
            raise ValueError('请上传图纸')
        if not instruction:
            raise ValueError('璇蜂笂浼犱綔涓氭寚瀵间功')
        if not inspection_points:
            raise ValueError('璇疯嚦灏戞坊鍔犱竴涓娴嬬偣')
        
        for point in inspection_points:
            if point.is_required and (not point.title or not point.file_path):
                raise ValueError('璇峰畬鍠勬墍鏈夊繀濉娴嬬偣')
        
        # 妫€鏌ュ娉ㄤ腑鐨勫繀濉」
        remarks = QCWorkOrderAttachment.query.filter_by(
            work_order_id=work_order.id, attach_type='remark'
        ).all()
        for remark in remarks:
            if remark.is_required and (not remark.content or not remark.file_path):
                raise ValueError('请完善所有必填备注')
        
        work_order.status = 'qc_completed'
        work_order.inspector_id = inspector_id
        work_order.qc_completed_at = datetime.now()
        work_order.rejected_at = None
        work_order.rejection_reason = None
        db.session.commit()
        return work_order
    
    @staticmethod
    def submit_inspection(order_id: int, results: list, user: User) -> QCWorkOrder:
        """Submit inspection results."""




        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')
        
        if not QCService.can_inspect_work_order(user, work_order):
            raise ValueError('娌℃湁鏉冮檺鎵ц璐ㄦ')
        
        if work_order.status not in ['qc_completed', 'inspection_pending']:
            raise ValueError('褰撳墠璁㈠崟鐘舵€佷笉鍏佽鎻愪氦璐ㄦ')
        
        attachments = QCWorkOrderAttachment.query.filter_by(work_order_id=work_order.id).all()
        attachment_ids = {a.id for a in attachments}
        
        if not results:
            raise ValueError('璇峰～鍐欒川妫€缁撴灉')

        submitted_ids = []
        for item in results:
            attachment_id = item.get('attachment_id')
            if attachment_id not in attachment_ids:
                raise ValueError('鏃犳晥鐨勯檮浠禝D')
            submitted_ids.append(attachment_id)

        if len(submitted_ids) != len(set(submitted_ids)):
            raise ValueError('存在重复的附件检验结果，请重新提交')

        missing_ids = attachment_ids.difference(submitted_ids)
        if missing_ids:
            raise ValueError('请完成所有附件的勾选后再提交')
        
        QCInspectionRecord.query.filter_by(work_order_id=work_order.id).delete()
        
        has_fail = False
        for item in results:
            attachment_id = item.get('attachment_id')
            result = item.get('result')
            remark = (item.get('remark') or '').strip() or None
            
            if result not in ['pass', 'fail']:
                raise ValueError('璐ㄦ缁撴灉鍙兘涓洪€氳繃鎴栦笉閫氳繃')
            
            record = QCInspectionRecord(
                work_order_id=work_order.id,
                inspector_id=user.id,
                attachment_id=attachment_id,
                result=result,
                remark=remark
            )
            db.session.add(record)
            if result == 'fail':
                has_fail = True
        
        if has_fail:
            work_order.status = 'rejected'
            work_order.rejected_at = datetime.now()
        else:
            work_order.status = 'inspection_completed'
            work_order.inspection_completed_at = datetime.now()
        
        db.session.commit()
        return work_order
    
    @staticmethod
    def sign_acceptance(order_id: int, user: User) -> dict:
        """Sign acceptance for the current user role."""




        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')
        
        if not QCService.can_accept_work_order(user, work_order):
            raise ValueError('娌℃湁鏉冮檺鎵ц楠屾敹纭')
        
        if work_order.status != 'inspection_completed':
            raise ValueError('当前订单尚未完成质检，无法验收')
        
        signer_role = user.role.code
        if signer_role not in ['qc_controller', 'qc_inspector', 'superadmin']:
            raise ValueError('当前角色无权验收')
        
        if user.is_superadmin:
            QCAcceptanceSignature.query.filter_by(work_order_id=work_order.id).delete()
            db.session.flush()
            db.session.add_all([
                QCAcceptanceSignature(work_order_id=work_order.id, signer_id=user.id, signer_role='qc_controller'),
                QCAcceptanceSignature(work_order_id=work_order.id, signer_id=user.id, signer_role='qc_inspector'),
            ])
            work_order.status = 'accepted'
            work_order.accepted_at = datetime.now()
            db.session.commit()
            return {'completed': True, 'message': '验收完成'}
        # 妫€鏌ユ槸鍚﹀凡绛捐繃
        existing = QCAcceptanceSignature.query.filter_by(
            work_order_id=work_order.id,
            signer_role=signer_role
        ).first()
        if existing:
            raise ValueError('鎮ㄥ凡瀹屾垚楠屾敹纭锛屾棤闇€閲嶅鎿嶄綔')
        
        signature = QCAcceptanceSignature(
            work_order_id=work_order.id,
            signer_id=user.id,
            signer_role=signer_role
        )
        db.session.add(signature)
        db.session.flush()
        
        # 妫€鏌ユ槸鍚﹀弻绛鹃兘瀹屾垚
        signatures = QCAcceptanceSignature.query.filter_by(work_order_id=work_order.id).all()
        roles_signed = {s.signer_role for s in signatures}
        if 'qc_controller' in roles_signed and 'qc_inspector' in roles_signed:
            work_order.status = 'accepted'
            work_order.accepted_at = datetime.now()
            db.session.commit()
            return {'completed': True, 'message': '鍙屾柟宸茬‘璁わ紝楠屾敹瀹屾垚'}
        
        db.session.commit()
        return {'completed': False, 'message': '验收确认已提交，等待另一方确认'}
    
    @staticmethod
    def rollback_acceptance(order_id: int, target: str, reason: str, user: User) -> QCWorkOrder:
        """Roll back acceptance and return the workflow."""
        work_order = QCWorkOrder.query.get(order_id)
        if not work_order:
            raise ValueError('工件订单不存在')
        
        if not QCService.can_rollback_work_order(user, work_order):
            raise ValueError('娌℃湁鏉冮檺鎵ц鍥為€€鎿嶄綔')
        
        if work_order.status not in ['inspection_completed', 'accepted']:
            raise ValueError('褰撳墠璁㈠崟鐘舵€佷笉鍏佽鍥為€€')
        
        if target not in ['qc', 'inspection']:
            raise ValueError('鏃犳晥鐨勫洖閫€鐩爣')
        
        if not reason or not reason.strip():
            raise ValueError('璇峰～鍐欏洖閫€鍘熷洜')
        
        # 鍒犻櫎绛惧瓧璁板綍
        QCAcceptanceSignature.query.filter_by(work_order_id=work_order.id).delete()
        
        if target == 'qc':
            work_order.status = 'qc_pending'
            QCInspectionRecord.query.filter_by(work_order_id=work_order.id).delete()
        else:
            work_order.status = 'inspection_pending'
        
        work_order.rejection_reason = reason.strip()
        db.session.commit()
        return work_order
    
    # ==================== 浠〃鐩樼粺璁?====================
    
    @staticmethod
    def get_dashboard_stats(user: User) -> dict:
        """Return dashboard statistics for the current user."""
        base_query = QCWorkOrder.query
        
        if not (user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']):
            if user.role.code == 'qc_controller':
                base_query = base_query.filter(QCWorkOrder.controller_id == user.id)
            elif user.role.code == 'qc_inspector':
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
    def get_recent_work_orders(user: User, limit: int = 5) -> list:
        """Return recent work orders visible to the current user."""
        query = QCWorkOrder.query
        
        if user.is_superadmin:
            query = query
        elif user.role.code in ['general_manager', 'gm_assistant']:
            query = query.filter(QCWorkOrder.status != 'draft')
        else:
            if user.role.code == 'qc_controller':
                query = query.filter(QCWorkOrder.controller_id == user.id)
            elif user.role.code == 'qc_inspector':
                query = query.filter(QCWorkOrder.inspector_id == user.id)
            else:
                return []
        
        return query.order_by(QCWorkOrder.created_at.desc()).limit(limit).all()


