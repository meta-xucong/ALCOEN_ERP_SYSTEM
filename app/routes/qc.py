"""QC routes."""
import re
from datetime import datetime

from flask import Blueprint, render_template, g, request, redirect, url_for, flash
from sqlalchemy import or_

from app import db
from app.models import User, Role, QCWorkOrderAttachment, QCUserBinding, QCWorkOrder, PERMISSIONS
from app.services.auth_service import AuthService
from app.services.qc_service import QCService
from app.services.user_service import UserService
from app.utils.decorators import login_required

qc_bp = Blueprint('qc', __name__, url_prefix='/qc')


def _extract_dynamic_indexes(form_data, prefix: str) -> list[int]:
    """Extract and sort numeric suffixes from dynamic field names."""
    pattern = re.compile(rf'^{re.escape(prefix)}([0-9]+)$')
    indexes = []
    for key in form_data.keys():
        match = pattern.match(key)
        if match:
            indexes.append(int(match.group(1)))
    return sorted(set(indexes))


def _block_quality_control_for_inspector(user):
    """Redirect inspectors away from the quality control module."""
    if user.role.code == 'qc_inspector':
        flash('质量检测员不可访问质量控制模块', 'warning')
        return redirect(url_for('qc.quality_inspection_list'))
    return None


def _build_inspection_record_map(work_order: QCWorkOrder) -> dict[int, object]:
    """Build an attachment-to-record mapping for templates that may have empty records."""
    return {record.attachment_id: record for record in work_order.inspection_records}


def _is_qc_admin(user) -> bool:
    """Return whether the user can access QC admin pages."""
    return bool(user and (user.is_superadmin or user.role.code == 'general_manager'))


def _require_qc_admin():
    """Enforce QC admin access and redirect when missing."""
    if _is_qc_admin(g.current_user):
        return None
    flash('需要 QC 系统管理权限', 'error')
    return redirect(url_for('qc.index'))

@qc_bp.route('/')
@login_required
def index():
    """QC dashboard."""
    user = g.current_user
    
    # 妫€鏌?QC 璁块棶鏉冮檺
    binding = None
    if user.role.code not in ['superadmin', 'general_manager', 'gm_assistant']:
        from app.models import QCUserBinding
        binding = QCUserBinding.query.filter_by(user_id=user.id, is_active=True).first()
        if not binding:
            flash('您尚未获得 QC 系统访问权限', 'warning')
            return redirect(url_for('auth.qc_login'))
    
    stats = QCService.get_dashboard_stats(user)
    recent_orders = QCService.get_recent_work_orders(user, limit=5)
    
    # 鑾峰彇鍙敤鐨勮川妫€鍛樺垪琛紙鐢ㄤ簬瀹屾垚鎸夐挳涓嬫媺妗嗭級
    inspectors = User.query.join(Role).filter(Role.code == 'qc_inspector', User.is_active == True).all()
    
    return render_template('qc/dashboard.html',
                         stats=stats,
                         recent_orders=recent_orders,
                         inspectors=inspectors)


# ==================== QC 绯荤粺绠＄悊 ====================

QC_ADMIN_ROLE_CODES = ['superadmin', 'general_manager', 'gm_assistant', 'qc_controller', 'qc_inspector']


@qc_bp.route('/admin/users')
@login_required
def qc_admin_users():
    """QC admin: user list."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    role_code = request.args.get('role', '').strip()
    status = request.args.get('status', '').strip()
    keyword = request.args.get('keyword', '').strip()

    query = User.query.join(Role).outerjoin(QCUserBinding, QCUserBinding.user_id == User.id).filter(
        or_(Role.code.in_(QC_ADMIN_ROLE_CODES), QCUserBinding.id.isnot(None))
    )

    if role_code:
        query = query.filter(Role.code == role_code)
    if status == 'active':
        query = query.filter(User.is_active.is_(True))
    elif status == 'inactive':
        query = query.filter(User.is_active.is_(False))
    if keyword:
        like_keyword = f'%{keyword}%'
        query = query.filter(
            or_(
                User.username.ilike(like_keyword),
                User.real_name.ilike(like_keyword),
                User.email.ilike(like_keyword),
            )
        )

    pagination = query.order_by(User.created_at.desc()).distinct().paginate(
        page=page,
        per_page=20,
        error_out=False,
    )
    roles = Role.query.filter(Role.code.in_(QC_ADMIN_ROLE_CODES)).order_by(Role.level.desc()).all()
    return render_template(
        'qc/admin_users.html',
        users=pagination.items,
        pagination=pagination,
        roles=roles,
        role=role_code,
        status=status,
        keyword=keyword,
    )


@qc_bp.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@login_required
def qc_admin_toggle_user(user_id: int):
    """QC admin: toggle user status."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    user = UserService.get_user_by_id(user_id, include_qc=True)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('qc.qc_admin_users'))
    if user.is_superadmin:
        flash('不能禁用超级管理员账号', 'error')
        return redirect(url_for('qc.qc_admin_users'))

    AuthService.toggle_user_status(user)
    flash(f'用户 {user.username} 状态已更新', 'success')
    return redirect(url_for('qc.qc_admin_users'))


@qc_bp.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
def qc_admin_reset_password(user_id: int):
    """QC admin: reset user password."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    user = UserService.get_user_by_id(user_id, include_qc=True)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('qc.qc_admin_users'))

    AuthService.reset_password(user)
    flash(f'用户 {user.username} 密码已重置为默认值', 'success')
    return redirect(url_for('qc.qc_admin_users'))


@qc_bp.route('/admin/pending')
@login_required
def qc_admin_pending():
    """QC admin: pending approvals."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    pending_qc_users = User.query.join(Role).filter(
        Role.code.in_(['qc_controller', 'qc_inspector']),
        User.is_active.is_(False),
        User.approved_at.is_(None),
    ).order_by(User.created_at.asc()).all()

    pending_qc_bindings = QCUserBinding.query.filter_by(is_active=False).order_by(
        QCUserBinding.created_at.asc()
    ).all()

    return render_template(
        'qc/admin_pending.html',
        pending_qc_users=pending_qc_users,
        pending_qc_bindings=pending_qc_bindings,
    )


@qc_bp.route('/admin/pending/user/<int:user_id>/approve', methods=['POST'])
@login_required
def qc_admin_approve_user(user_id: int):
    """QC admin: approve QC user."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    user = UserService.get_user_by_id(user_id, include_qc=True)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('qc.qc_admin_pending'))

    AuthService.approve_user(user, g.current_user)
    flash(f'用户 {user.username} 审核通过', 'success')
    return redirect(url_for('qc.qc_admin_pending'))


@qc_bp.route('/admin/pending/user/<int:user_id>/reject', methods=['POST'])
@login_required
def qc_admin_reject_user(user_id: int):
    """QC admin: reject QC user."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    user = UserService.get_user_by_id(user_id, include_qc=True)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('qc.qc_admin_pending'))

    AuthService.reject_user(user)
    flash(f'已拒绝用户 {user.username} 的注册申请', 'success')
    return redirect(url_for('qc.qc_admin_pending'))


@qc_bp.route('/admin/pending/binding/<int:binding_id>/approve', methods=['POST'])
@login_required
def qc_admin_approve_binding(binding_id: int):
    """QC admin: approve ERP user QC binding."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    binding = QCUserBinding.query.get_or_404(binding_id)
    now = datetime.now()
    binding.is_active = True
    binding.approved_by = g.current_user.id
    binding.approved_at = now

    if not binding.user.is_active:
        binding.user.is_active = True
        binding.user.approved_by = g.current_user.id
        binding.user.approved_at = now

    db.session.commit()
    flash(f'已通过 {binding.user.username} 的 QC 角色申请', 'success')
    return redirect(url_for('qc.qc_admin_pending'))


@qc_bp.route('/admin/pending/binding/<int:binding_id>/reject', methods=['POST'])
@login_required
def qc_admin_reject_binding(binding_id: int):
    """QC admin: reject ERP user QC binding."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    binding = QCUserBinding.query.get_or_404(binding_id)
    username = binding.user.username
    user = binding.user
    db.session.delete(binding)
    if not user.is_active and user.role.code in ['qc_controller', 'qc_inspector']:
        db.session.delete(user)
    db.session.commit()
    flash(f'已拒绝 {username} 的 QC 角色申请', 'success')
    return redirect(url_for('qc.qc_admin_pending'))


@qc_bp.route('/admin/roles')
@login_required
def qc_admin_roles():
    """QC admin: role permissions overview."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    roles = Role.query.filter(Role.code.in_(QC_ADMIN_ROLE_CODES)).order_by(Role.level.desc()).all()
    import json
    permission_counts = {}
    for role in roles:
        if role.code == 'superadmin':
            permission_counts[role.id] = -1
            continue
        try:
            permission_counts[role.id] = len(json.loads(role.permissions or '[]'))
        except Exception:
            permission_counts[role.id] = 0
    return render_template('qc/admin_roles.html', roles=roles, permission_counts=permission_counts)


@qc_bp.route('/admin/roles/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
def qc_admin_edit_role(role_id: int):
    """QC admin: edit role permissions."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    role = Role.query.get_or_404(role_id)
    if role.code not in QC_ADMIN_ROLE_CODES:
        flash('该角色不属于 QC 系统管理范围', 'error')
        return redirect(url_for('qc.qc_admin_roles'))
    if role.code == 'superadmin':
        flash('超级管理员权限不可编辑', 'error')
        return redirect(url_for('qc.qc_admin_roles'))

    if request.method == 'POST':
        selected_permissions = request.form.getlist('permissions')
        success, message = UserService.update_role_permissions(role_id, selected_permissions)
        flash(message, 'success' if success else 'error')
        if success:
            return redirect(url_for('qc.qc_admin_roles'))

    import json
    try:
        current_permissions = json.loads(role.permissions or '[]')
    except Exception:
        current_permissions = []
    return render_template(
        'qc/admin_role_edit.html',
        role=role,
        permissions=PERMISSIONS,
        current_permissions=current_permissions,
    )


# ==================== 璐ㄩ噺鎺у埗妯″潡 ====================

@qc_bp.route('/quality-control/')
@login_required
def quality_control_list():
    """Quality control work order list."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    keyword = request.args.get('keyword', '')
    
    pagination = QCService.get_work_order_list(
        user=user,
        status=status or None,
        keyword=keyword or None,
        page=page
    )
    
    return render_template('qc/work_order_list.html',
                         orders=pagination.items,
                         pagination=pagination,
                         status=status,
                         keyword=keyword)


@qc_bp.route('/quality-control/new', methods=['GET', 'POST'])
@login_required
def quality_control_new():
    """Create a new work order."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    if user.role.code != 'qc_controller' or not user.has_permission('qc_work_order_create'):
        flash('没有权限创建工件订单', 'error')
        return redirect(url_for('qc.index'))
    
    # 鑾峰彇璐ㄦ鍛樺垪琛?    inspectors = User.query.join(Role).filter(Role.code == 'qc_inspector', User.is_active == True).all()
    inspectors = User.query.join(Role).filter(Role.code == 'qc_inspector', User.is_active == True).all()
    if request.method == 'POST':
        action = request.form.get('submit_action', '').strip()
        if action not in ['draft', 'complete']:
            flash('无效的提交流程，请重新操作', 'error')
            return render_template('qc/work_order_form.html', inspectors=inspectors)

        strict_complete = action == 'complete'
        inspector_id = request.form.get('inspector_id', type=int) if strict_complete else None

        point_indexes = _extract_dynamic_indexes(request.form, 'inspection_point_title_')
        point_items = []
        for idx in point_indexes:
            point_items.append(
                {
                    'title': request.form.get(f'inspection_point_title_{idx}', '').strip(),
                    'content': request.form.get(f'inspection_point_content_{idx}', '').strip(),
                    'file': request.files.get(f'inspection_point_file_{idx}'),
                }
            )

        remark_indexes = _extract_dynamic_indexes(request.form, 'remark_content_')
        remark_items = []
        for idx in remark_indexes:
            remark_items.append(
                {
                    'content': request.form.get(f'remark_content_{idx}', '').strip(),
                    'is_required': request.form.get(f'remark_required_{idx}') == '1',
                    'file': request.files.get(f'remark_file_{idx}'),
                }
            )

        non_empty_points = [
            item for item in point_items
            if item['title'] or item['content'] or (item['file'] and item['file'].filename)
        ]
        non_empty_remarks = [
            item for item in remark_items
            if item['content'] or item['is_required'] or (item['file'] and item['file'].filename)
        ]

        drawing_file = request.files.get('drawing')
        instruction_file = request.files.get('instruction')

        try:
            if strict_complete:
                if not inspector_id:
                    raise ValueError('璇烽€夋嫨璐ㄩ噺妫€娴嬪憳')
                if not drawing_file or not drawing_file.filename:
                    raise ValueError('请上传图纸')
                if not instruction_file or not instruction_file.filename:
                    raise ValueError('璇蜂笂浼犱綔涓氭寚瀵间功')
                if not non_empty_points:
                    raise ValueError('璇疯嚦灏戞坊鍔犱竴涓娴嬬偣')
                for item in non_empty_points:
                    if not item['title']:
                        raise ValueError('妫€娴嬬偣鍚嶇О涓嶈兘涓虹┖')
                    if not item['file'] or not item['file'].filename:
                        raise ValueError('璇蜂负姣忎釜妫€娴嬬偣涓婁紶鍥剧墖')
                for item in non_empty_remarks:
                    if item['is_required'] and (not item['content'] or not item['file'] or not item['file'].filename):
                        raise ValueError('必填备注必须包含文字和图片')

            data = {
                'batch_no': request.form.get('batch_no', '').strip(),
                'workpiece_name': request.form.get('workpiece_name', '').strip(),
                'quantity': request.form.get('quantity', '').strip(),
            }
            work_order = QCService.create_work_order(
                data=data,
                controller_id=user.id,
                status='draft' if action == 'draft' else 'qc_pending',
                allow_partial=(action == 'draft'),
                auto_commit=False,
            )

            if drawing_file and drawing_file.filename:
                QCService.add_attachment(
                    work_order.id, drawing_file, 'drawing',
                    title='鍥剧焊', is_required=True, user=user, auto_commit=False
                )

            if instruction_file and instruction_file.filename:
                QCService.add_attachment(
                    work_order.id, instruction_file, 'instruction',
                    title='作业指导书', is_required=True, user=user, auto_commit=False
                )

            for sort_order, item in enumerate(non_empty_points):
                if item['file'] and item['file'].filename:
                    QCService.add_attachment(
                        work_order.id,
                        item['file'],
                        'inspection_point',
                        title=item['title'] or f'妫€娴嬬偣{sort_order + 1}',
                        content=item['content'],
                        is_required=True,
                        sort_order=sort_order,
                        user=user,
                        auto_commit=False,
                    )
                else:
                    db.session.add(
                        QCWorkOrderAttachment(
                            work_order_id=work_order.id,
                            attach_type='inspection_point',
                            title=item['title'] or f'妫€娴嬬偣{sort_order + 1}',
                            content=item['content'],
                            file_path='',
                            file_type='',
                            is_required=True,
                            sort_order=sort_order,
                        )
                    )

            for sort_order, item in enumerate(non_empty_remarks):
                file = item['file']
                if file and file.filename:
                    QCService.add_attachment(
                        work_order.id,
                        file,
                        'remark',
                        content=item['content'],
                        is_required=item['is_required'],
                        sort_order=sort_order,
                        user=user,
                        auto_commit=False,
                    )
                else:
                    db.session.add(
                        QCWorkOrderAttachment(
                            work_order_id=work_order.id,
                            attach_type='remark',
                            content=item['content'],
                            file_path='',
                            file_type='',
                            is_required=item['is_required'],
                            sort_order=sort_order,
                        )
                    )

            if action == 'complete':
                QCService.complete_quality_control(work_order.id, inspector_id, user)
                flash('工件订单已完成并推送至质量检测模块', 'success')
                return redirect(url_for('qc.quality_inspection_detail', order_id=work_order.id))

            db.session.commit()
            flash('草稿已保存，仅您和系统管理员可见', 'success')
            return redirect(url_for('qc.quality_control_detail', order_id=work_order.id))
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'error')
            return render_template('qc/work_order_form.html', inspectors=inspectors)
    
    return render_template('qc/work_order_form.html', inspectors=inspectors)


@qc_bp.route('/quality-control/<int:order_id>')
@login_required
def quality_control_detail(order_id: int):
    """Quality control work order detail."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.quality_control_list'))
    
    inspectors = User.query.join(Role).filter(Role.code == 'qc_inspector', User.is_active == True).all()
    return render_template('qc/work_order_detail_qc.html',
                         order=work_order,
                         inspectors=inspectors,
                         inspection_records_by_attachment=_build_inspection_record_map(work_order))


@qc_bp.route('/quality-control/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def quality_control_edit(order_id: int):
    """Edit a work order."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.quality_control_list'))
    
    if not QCService.can_edit_work_order(user, work_order):
        flash('当前订单状态不允许编辑', 'error')
        return redirect(url_for('qc.quality_control_detail', order_id=order_id))
    
    inspectors = User.query.join(Role).filter(Role.code == 'qc_inspector', User.is_active == True).all()
    
    if request.method == 'POST':
        try:
            allow_partial = work_order.status == 'draft'
            data = {
                'batch_no': request.form.get('batch_no', '').strip(),
                'workpiece_name': request.form.get('workpiece_name', '').strip(),
                'quantity': request.form.get('quantity', '').strip(),
            }
            QCService.update_work_order(order_id, data, user, allow_partial=allow_partial)

            point_items = []
            point_indexes = _extract_dynamic_indexes(request.form, 'inspection_point_title_')
            for idx in point_indexes:
                item = {
                    'title': request.form.get(f'inspection_point_title_{idx}', ''),
                    'content': request.form.get(f'inspection_point_content_{idx}', ''),
                    'file': request.files.get(f'inspection_point_file_{idx}'),
                }
                if allow_partial:
                    has_any = (
                        (item['title'] or '').strip()
                        or (item['content'] or '').strip()
                        or (item['file'] and item['file'].filename)
                    )
                    if not has_any:
                        continue
                point_items.append(item)

            remark_items = []
            remark_indexes = _extract_dynamic_indexes(request.form, 'remark_content_')
            for idx in remark_indexes:
                item = {
                    'content': request.form.get(f'remark_content_{idx}', ''),
                    'is_required': request.form.get(f'remark_required_{idx}') == '1',
                    'file': request.files.get(f'remark_file_{idx}'),
                }
                if allow_partial:
                    has_any = (
                        (item['content'] or '').strip()
                        or item['is_required']
                        or (item['file'] and item['file'].filename)
                    )
                    if not has_any:
                        continue
                remark_items.append(item)

            QCService.sync_work_order_attachments(
                order_id=order_id,
                point_items=point_items,
                remark_items=remark_items,
                drawing_file=request.files.get('drawing'),
                instruction_file=request.files.get('instruction'),
                user=user,
                allow_partial=allow_partial,
            )

            flash('工件订单更新成功', 'success')
            return redirect(url_for('qc.quality_control_detail', order_id=order_id))
        except ValueError as e:
            flash(str(e), 'error')
    
    return render_template('qc/work_order_form.html',
                         order=work_order,
                         inspectors=inspectors,
                         is_edit=True)


@qc_bp.route('/quality-control/<int:order_id>/delete', methods=['POST'])
@login_required
def quality_control_delete(order_id: int):
    """Delete a work order."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    try:
        QCService.delete_work_order(order_id, user)
        flash('工件订单已删除', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(url_for('qc.quality_control_list'))


@qc_bp.route('/quality-control/<int:order_id>/complete', methods=['POST'])
@login_required
def quality_control_complete(order_id: int):
    """Complete quality control and assign an inspector."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    inspector_id = request.form.get('inspector_id', type=int)
    
    try:
        QCService.complete_quality_control(order_id, inspector_id, user)
        flash('质控完成，已推送至质量检测模块', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('qc.quality_control_detail', order_id=order_id))


@qc_bp.route('/quality-control/attachments/<int:attachment_id>/delete', methods=['POST'])
@login_required
def quality_control_delete_attachment(attachment_id: int):
    """Delete a work order attachment."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    try:
        QCService.delete_attachment(attachment_id, user)
        flash('附件已删除', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(request.referrer or url_for('qc.index'))


# ==================== 璐ㄩ噺妫€娴嬫ā鍧?====================

@qc_bp.route('/quality-inspection/')
@login_required
def quality_inspection_list():
    """Quality inspection list."""
    user = g.current_user
    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '')
    
    pagination = QCService.get_inspection_list(
        user=user,
        keyword=keyword or None,
        page=page
    )
    
    return render_template('qc/inspection_list.html',
                         orders=pagination.items,
                         pagination=pagination,
                         keyword=keyword)


@qc_bp.route('/quality-inspection/<int:order_id>', methods=['GET', 'POST'])
@login_required
def quality_inspection_detail(order_id: int):
    """Quality inspection detail."""
    user = g.current_user
    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.quality_inspection_list'))
    
    if request.method == 'POST':
        if not QCService.can_inspect_work_order(user, work_order):
            flash('没有权限提交质检结果', 'error')
            return redirect(url_for('qc.quality_inspection_detail', order_id=order_id))
        
        try:
            attachments = QCWorkOrderAttachment.query.filter_by(work_order_id=work_order.id).all()
            results = []
            for attach in attachments:
                result = request.form.get(f'result_{attach.id}')
                remark = request.form.get(f'remark_{attach.id}', '').strip()
                if result:
                    results.append({
                        'attachment_id': attach.id,
                        'result': result,
                        'remark': remark or None
                    })
            
            updated_order = QCService.submit_inspection(order_id, results, user)
            if updated_order.status == 'inspection_completed':
                flash('质检合格，已进入验收模块', 'success')
                return redirect(url_for('qc.acceptance_detail', order_id=order_id))

            flash('质检不合格，已退回质量控制流程', 'warning')
            if user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant', 'qc_controller']:
                return redirect(url_for('qc.quality_control_detail', order_id=order_id))
            return redirect(url_for('qc.quality_inspection_list'))
        except ValueError as e:
            flash(str(e), 'error')
    
    return render_template(
        'qc/work_order_detail_inspector.html',
        order=work_order,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
    )


# ==================== 楠屾敹妯″潡 ====================

@qc_bp.route('/acceptance/')
@login_required
def acceptance_list():
    """Acceptance list."""
    user = g.current_user
    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '')
    
    pagination = QCService.get_acceptance_list(
        user=user,
        keyword=keyword or None,
        page=page
    )
    
    return render_template('qc/acceptance_list.html',
                         orders=pagination.items,
                         pagination=pagination,
                         keyword=keyword)


@qc_bp.route('/acceptance/<int:order_id>')
@login_required
def acceptance_detail(order_id: int):
    """Acceptance detail."""
    user = g.current_user
    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.acceptance_list'))
    
    signatures = {s.signer_role: s for s in work_order.signatures}
    return render_template(
        'qc/acceptance_detail.html',
        order=work_order,
        signatures=signatures,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
    )


@qc_bp.route('/acceptance/<int:order_id>/sign', methods=['POST'])
@login_required
def acceptance_sign(order_id: int):
    """Acceptance sign action."""
    user = g.current_user
    try:
        result = QCService.sign_acceptance(order_id, user)
        flash(result['message'], 'success' if result['completed'] else 'info')
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(url_for('qc.acceptance_detail', order_id=order_id))


@qc_bp.route('/acceptance/<int:order_id>/rollback', methods=['POST'])
@login_required
def acceptance_rollback(order_id: int):
    """Rollback acceptance and return the workflow."""
    user = g.current_user
    target = request.form.get('target', '').strip()
    reason = request.form.get('reason', '').strip()
    
    try:
        QCService.rollback_acceptance(order_id, target, reason, user)
        flash('流程已回退', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('qc.acceptance_detail', order_id=order_id))


@qc_bp.route('/acceptance/<int:order_id>/print')
@login_required
def acceptance_print(order_id: int):
    """Printable acceptance sheet."""
    from datetime import datetime
    user = g.current_user
    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.acceptance_list'))
    
    signatures = {s.signer_role: s for s in work_order.signatures}
    return render_template(
        'qc/acceptance_print.html',
        order=work_order,
        signatures=signatures,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )

