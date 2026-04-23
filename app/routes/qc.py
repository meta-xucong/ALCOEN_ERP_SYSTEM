"""QC routes."""

from __future__ import annotations

import re
from datetime import datetime

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_

from app import db
from app.models import (
    QC_ADMIN_ROLE_CODES,
    QC_MANAGER_ROLE_CODES,
    QC_ROLE_CODES,
    QC_ROLE_EDITABLE_PERMISSIONS,
    QCAcceptanceSignature,
    QCUserBinding,
    QCWorkOrder,
    QCWorkOrderAttachment,
    QCWorkpiece,
    Role,
    User,
)
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


def _active_suppliers() -> list[User]:
    """Return active supplier users."""
    return User.query.join(Role).filter(Role.code == 'qc_inspector', User.is_active.is_(True)).all()


def _build_guide_items(form_data, files, title_prefix: str = 'guide_title_', content_prefix: str = 'guide_content_', file_prefix: str = 'guide_file_') -> list[dict]:
    """Build guide items from dynamic form inputs."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, title_prefix):
        item = {
            'title': form_data.get(f'{title_prefix}{idx}', '').strip(),
            'content': form_data.get(f'{content_prefix}{idx}', '').strip(),
            'file': files.get(f'{file_prefix}{idx}'),
        }
        if item['title'] or item['content'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_legacy_point_items(form_data, files) -> list[dict]:
    """Build legacy inspection-point items for backward-compatible handlers."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, 'inspection_point_title_'):
        item = {
            'title': form_data.get(f'inspection_point_title_{idx}', '').strip(),
            'content': form_data.get(f'inspection_point_content_{idx}', '').strip(),
            'file': files.get(f'inspection_point_file_{idx}'),
        }
        if item['title'] or item['content'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_remark_items(form_data, files) -> list[dict]:
    """Build remark items from dynamic form inputs."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, 'remark_content_'):
        item = {
            'content': form_data.get(f'remark_content_{idx}', '').strip(),
            'is_required': form_data.get(f'remark_required_{idx}') == '1',
            'file': files.get(f'remark_file_{idx}'),
        }
        if item['content'] or item['is_required'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_inspection_record_map(work_order: QCWorkOrder) -> dict[int, object]:
    """Build an attachment-to-record mapping for templates."""
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


def _block_workpiece_access(user):
    """Redirect users without workpiece-library access."""
    if QCService.can_access_workpiece_library(user):
        return None

    flash('您没有权限访问工件库模块', 'warning')
    if QCService.can_access_quality_control(user):
        return redirect(url_for('qc.quality_control_list'))
    if QCService.can_access_inspection(user):
        return redirect(url_for('qc.quality_inspection_list'))
    if QCService.can_access_acceptance(user):
        return redirect(url_for('qc.acceptance_list'))
    return redirect(url_for('qc.index'))


def _block_quality_control_for_inspector(user):
    """Redirect users without quality-control access."""
    if QCService.can_access_quality_control(user):
        return None

    flash('您没有权限访问质量控制模块', 'warning')
    if QCService.can_access_workpiece_library(user):
        return redirect(url_for('qc.workpiece_list'))
    if QCService.can_access_inspection(user):
        return redirect(url_for('qc.quality_inspection_list'))
    if QCService.can_access_acceptance(user):
        return redirect(url_for('qc.acceptance_list'))
    return redirect(url_for('qc.index'))


def _require_qc_inspection_access(user):
    """Redirect users without inspection access."""
    if QCService.can_access_inspection(user):
        return None

    flash('您没有权限访问质量检测模块', 'warning')
    if QCService.can_access_quality_control(user):
        return redirect(url_for('qc.quality_control_list'))
    if QCService.can_access_acceptance(user):
        return redirect(url_for('qc.acceptance_list'))
    return redirect(url_for('qc.index'))


def _require_qc_acceptance_access(user):
    """Redirect users without acceptance access."""
    if QCService.can_access_acceptance(user):
        return None

    flash('您没有权限访问验收模块', 'warning')
    if QCService.can_access_inspection(user):
        return redirect(url_for('qc.quality_inspection_list'))
    if QCService.can_access_quality_control(user):
        return redirect(url_for('qc.quality_control_list'))
    return redirect(url_for('qc.index'))


@qc_bp.route('/')
@login_required
def index():
    """QC dashboard."""
    user = g.current_user

    if not user.is_superadmin and user.role.code not in QC_MANAGER_ROLE_CODES:
        binding = QCUserBinding.query.filter_by(user_id=user.id, is_active=True).first()
        if not binding:
            flash('您尚未获得 QC 系统访问权限', 'warning')
            return redirect(url_for('auth.qc_login'))

    stats = QCService.get_dashboard_stats(user)
    recent_orders = QCService.get_recent_work_orders(user, limit=5)
    inspectors = _active_suppliers()

    return render_template(
        'qc/dashboard.html',
        stats=stats,
        recent_orders=recent_orders,
        inspectors=inspectors,
    )


# ==================== QC 系统管理 ====================

QC_ADMIN_MANAGED_ROLE_CODES = ('superadmin',) + QC_ADMIN_ROLE_CODES


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
        or_(Role.code.in_(QC_ADMIN_MANAGED_ROLE_CODES), QCUserBinding.id.isnot(None))
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
    roles = Role.query.filter(Role.code.in_(QC_ADMIN_MANAGED_ROLE_CODES)).order_by(Role.level.desc()).all()
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
    if not user.is_active and user.role.code in QC_ROLE_CODES:
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

    roles = Role.query.filter(Role.code.in_(QC_ADMIN_MANAGED_ROLE_CODES)).order_by(Role.level.desc()).all()
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
    if role.code not in QC_ADMIN_MANAGED_ROLE_CODES:
        flash('该角色不属于 QC 系统管理范围', 'error')
        return redirect(url_for('qc.qc_admin_roles'))
    if role.code == 'superadmin':
        flash('超级管理员权限不可编辑', 'error')
        return redirect(url_for('qc.qc_admin_roles'))

    if request.method == 'POST':
        selected_permissions = request.form.getlist('permissions')
        success, message = UserService.update_role_permissions(role_id, selected_permissions, scope='qc')
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
        permissions=QC_ROLE_EDITABLE_PERMISSIONS.get(role.code, {}),
        current_permissions=current_permissions,
    )


# ==================== 工件库模块 ====================

@qc_bp.route('/workpieces/')
@login_required
def workpiece_list():
    """Workpiece-library list."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    pagination = QCService.get_workpiece_list(user=user, keyword=keyword or None, page=page)
    return render_template(
        'qc/workpiece_list.html',
        workpieces=pagination.items,
        pagination=pagination,
        keyword=keyword,
    )


@qc_bp.route('/workpieces/new', methods=['GET', 'POST'])
@login_required
def workpiece_new():
    """Create a new workpiece."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    if not QCService.can_create_workpiece(user):
        flash('没有权限新增工件', 'error')
        return redirect(url_for('qc.workpiece_list'))

    if request.method == 'POST':
        guide_items = _build_guide_items(request.form, request.files)
        remark_items = _build_remark_items(request.form, request.files)
        drawing_file = request.files.get('drawing')

        try:
            workpiece = QCService.create_workpiece(
                data={
                    'workpiece_code': request.form.get('workpiece_code', '').strip(),
                    'workpiece_name': request.form.get('workpiece_name', '').strip(),
                },
                creator_id=user.id,
                auto_commit=False,
            )
            QCService.sync_workpiece_attachments(
                workpiece_id=workpiece.id,
                guide_items=guide_items,
                remark_items=remark_items,
                drawing_file=drawing_file,
                user=user,
            )
            flash('工件已创建', 'success')
            return redirect(url_for('qc.workpiece_detail', workpiece_id=workpiece.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template('qc/workpiece_form.html')


@qc_bp.route('/workpieces/<int:workpiece_id>')
@login_required
def workpiece_detail(workpiece_id: int):
    """Workpiece detail."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    workpiece = QCService.get_workpiece(workpiece_id, user)
    if not workpiece:
        flash('工件不存在或没有权限查看', 'error')
        return redirect(url_for('qc.workpiece_list'))

    return render_template('qc/workpiece_detail.html', workpiece=workpiece)


@qc_bp.route('/workpieces/<int:workpiece_id>/edit', methods=['GET', 'POST'])
@login_required
def workpiece_edit(workpiece_id: int):
    """Edit a workpiece."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    workpiece = QCService.get_workpiece(workpiece_id, user)
    if not workpiece:
        flash('工件不存在或没有权限查看', 'error')
        return redirect(url_for('qc.workpiece_list'))
    if not QCService.can_edit_workpiece(user, workpiece):
        flash('没有权限编辑该工件', 'error')
        return redirect(url_for('qc.workpiece_detail', workpiece_id=workpiece_id))

    if request.method == 'POST':
        guide_items = _build_guide_items(request.form, request.files)
        remark_items = _build_remark_items(request.form, request.files)
        drawing_file = request.files.get('drawing')
        try:
            QCService.update_workpiece(
                workpiece_id=workpiece_id,
                data={
                    'workpiece_code': request.form.get('workpiece_code', '').strip(),
                    'workpiece_name': request.form.get('workpiece_name', '').strip(),
                },
                user=user,
            )
            QCService.sync_workpiece_attachments(
                workpiece_id=workpiece_id,
                guide_items=guide_items,
                remark_items=remark_items,
                drawing_file=drawing_file,
                user=user,
            )
            flash('工件更新成功', 'success')
            return redirect(url_for('qc.workpiece_detail', workpiece_id=workpiece_id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template('qc/workpiece_form.html', workpiece=workpiece, is_edit=True)


@qc_bp.route('/workpieces/<int:workpiece_id>/delete', methods=['POST'])
@login_required
def workpiece_delete(workpiece_id: int):
    """Delete a workpiece."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    try:
        QCService.delete_workpiece(workpiece_id, user)
        flash('工件已删除', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.workpiece_list'))


@qc_bp.route('/workpieces/<int:workpiece_id>/snapshot')
@login_required
def workpiece_snapshot(workpiece_id: int):
    """Return workpiece preview data for the order form."""
    user = g.current_user
    workpiece = QCService.get_workpiece(workpiece_id, user)
    if not workpiece:
        return jsonify({'success': False, 'message': '工件不存在或没有权限查看'}), 404
    return jsonify({'success': True, 'workpiece': QCService.serialize_workpiece_preview(workpiece)})


# ==================== 质量控制模块 ====================

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
        page=page,
    )

    return render_template(
        'qc/work_order_list.html',
        orders=pagination.items,
        pagination=pagination,
        status=status,
        keyword=keyword,
    )


@qc_bp.route('/quality-control/new', methods=['GET', 'POST'])
@login_required
def quality_control_new():
    """Create a new work order."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    if not QCService.can_create_work_order(user):
        flash('没有权限创建工件订单', 'error')
        return redirect(url_for('qc.index'))

    suppliers = _active_suppliers()
    workpieces = QCService.get_workpiece_choices(user)

    if request.method == 'POST':
        action = request.form.get('submit_action', '').strip()
        if action not in ['draft', 'complete']:
            flash('无效的提交流程，请重新操作', 'error')
            return render_template('qc/work_order_form.html', workpieces=workpieces, suppliers=suppliers)

        strict_complete = action == 'complete'
        inspector_id = request.form.get('inspector_id', type=int) if strict_complete else None
        workpiece_id = request.form.get('workpiece_id', type=int)

        try:
            if strict_complete and not inspector_id:
                raise ValueError('请选择目标供应商')

            work_order = QCService.create_work_order(
                data={
                    'batch_no': request.form.get('batch_no', '').strip(),
                    'workpiece_id': workpiece_id,
                    'workpiece_name': request.form.get('workpiece_name', '').strip(),
                    'quantity': request.form.get('quantity', '').strip(),
                },
                controller_id=user.id,
                status='draft' if action == 'draft' else 'qc_pending',
                allow_partial=(action == 'draft'),
                auto_commit=False,
            )

            if workpiece_id:
                QCService.apply_workpiece_to_order(work_order.id, workpiece_id, user)
            else:
                legacy_points = _build_legacy_point_items(request.form, request.files)
                legacy_remarks = _build_remark_items(request.form, request.files)
                drawing_file = request.files.get('drawing')
                instruction_file = request.files.get('instruction')
                has_legacy_payload = any([
                    drawing_file and drawing_file.filename,
                    instruction_file and instruction_file.filename,
                    legacy_points,
                    legacy_remarks,
                ])

                if has_legacy_payload:
                    QCService.sync_work_order_attachments(
                        order_id=work_order.id,
                        point_items=legacy_points,
                        remark_items=legacy_remarks,
                        drawing_file=drawing_file,
                        instruction_file=instruction_file,
                        user=user,
                        allow_partial=(action == 'draft'),
                    )
                elif strict_complete:
                    raise ValueError('请选择工件后再完成质控')
                else:
                    db.session.commit()

            QCService.sync_order_section_files(
                order_id=work_order.id,
                drawing_note_file=request.files.get('drawing_note_file'),
                guide_certificate_file=request.files.get('guide_certificate_file'),
                remark_note_file=request.files.get('remark_note_file'),
                user=user,
            )

            if action == 'complete':
                QCService.complete_quality_control(work_order.id, inspector_id, user)
                flash('工件订单已完成并推送至质量检测模块', 'success')
                return redirect(url_for('qc.quality_inspection_detail', order_id=work_order.id))

            flash('草稿已保存，仅您和系统管理员可见', 'success')
            return redirect(url_for('qc.quality_control_detail', order_id=work_order.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template('qc/work_order_form.html', workpieces=workpieces, suppliers=suppliers)


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

    suppliers = _active_suppliers()
    return render_template(
        'qc/work_order_detail_qc.html',
        order=work_order,
        suppliers=suppliers,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
    )


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

    suppliers = _active_suppliers()
    workpieces = QCService.get_workpiece_choices(user)

    if request.method == 'POST':
        try:
            allow_partial = work_order.status == 'draft'
            workpiece_id = request.form.get('workpiece_id', type=int)
            previous_workpiece_id = work_order.workpiece_id
            had_attachments = bool(work_order.attachments)

            QCService.update_work_order(
                order_id=order_id,
                data={
                    'batch_no': request.form.get('batch_no', '').strip(),
                    'workpiece_id': workpiece_id,
                    'workpiece_name': request.form.get('workpiece_name', '').strip(),
                    'quantity': request.form.get('quantity', '').strip(),
                },
                user=user,
                allow_partial=allow_partial,
            )

            if workpiece_id:
                if previous_workpiece_id != workpiece_id or not had_attachments:
                    QCService.apply_workpiece_to_order(order_id, workpiece_id, user)
            else:
                QCService.sync_work_order_attachments(
                    order_id=order_id,
                    point_items=_build_legacy_point_items(request.form, request.files),
                    remark_items=_build_remark_items(request.form, request.files),
                    drawing_file=request.files.get('drawing'),
                    instruction_file=request.files.get('instruction'),
                    user=user,
                    allow_partial=allow_partial,
                )

            QCService.sync_order_section_files(
                order_id=order_id,
                drawing_note_file=request.files.get('drawing_note_file'),
                guide_certificate_file=request.files.get('guide_certificate_file'),
                remark_note_file=request.files.get('remark_note_file'),
                user=user,
            )

            flash('工件订单更新成功', 'success')
            return redirect(url_for('qc.quality_control_detail', order_id=order_id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/work_order_form.html',
        order=work_order,
        suppliers=suppliers,
        workpieces=workpieces,
        is_edit=True,
    )


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
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.quality_control_list'))


@qc_bp.route('/quality-control/<int:order_id>/complete', methods=['POST'])
@login_required
def quality_control_complete(order_id: int):
    """Complete quality control and assign a supplier."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    inspector_id = request.form.get('inspector_id', type=int)

    try:
        QCService.complete_quality_control(order_id, inspector_id, user)
        flash('质控完成，已推送至质量检测模块', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')

    return redirect(url_for('qc.quality_control_detail', order_id=order_id))


@qc_bp.route('/quality-control/attachments/<int:attachment_id>/delete', methods=['POST'])
@login_required
def quality_control_delete_attachment(attachment_id: int):
    """Delete a legacy work-order attachment."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    try:
        QCService.delete_attachment(attachment_id, user)
        flash('附件已删除', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(request.referrer or url_for('qc.index'))


# ==================== 质量检测模块 ====================

@qc_bp.route('/quality-inspection/')
@login_required
def quality_inspection_list():
    """Quality inspection list."""
    user = g.current_user
    blocked = _require_qc_inspection_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '')

    pagination = QCService.get_inspection_list(
        user=user,
        keyword=keyword or None,
        page=page,
    )

    return render_template(
        'qc/inspection_list.html',
        orders=pagination.items,
        pagination=pagination,
        keyword=keyword,
    )


@qc_bp.route('/quality-inspection/<int:order_id>', methods=['GET', 'POST'])
@login_required
def quality_inspection_detail(order_id: int):
    """Quality inspection detail."""
    user = g.current_user
    blocked = _require_qc_inspection_access(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.quality_inspection_list'))

    if request.method == 'POST':
        if not QCService.can_inspect_work_order(user, work_order):
            flash('没有权限提交质检结果', 'error')
            return redirect(url_for('qc.quality_inspection_detail', order_id=order_id))

        action = request.form.get('submit_action', 'submit').strip()
        final_submit = action != 'draft'
        try:
            results = []
            for attachment in work_order.attachments:
                result = request.form.get(f'result_{attachment.id}', '').strip()
                remark = request.form.get(f'remark_{attachment.id}', '').strip()
                report_file = request.files.get(f'report_file_{attachment.id}')
                has_payload = bool(result or remark or (report_file and report_file.filename))
                if final_submit or has_payload:
                    results.append(
                        {
                            'attachment_id': attachment.id,
                            'result': result,
                            'remark': remark or None,
                            'report_file': report_file,
                        }
                    )

            updated_order = QCService.submit_inspection(
                order_id=order_id,
                results=results,
                user=user,
                final_submit=final_submit,
            )

            if not final_submit:
                flash('质检草稿已保存', 'success')
                return redirect(url_for('qc.quality_inspection_detail', order_id=order_id))

            if updated_order.status == 'inspection_completed':
                flash('质检合格，已进入验收模块', 'success')
                return redirect(url_for('qc.acceptance_detail', order_id=order_id))

            flash('质检不合格，已退回质量控制流程', 'warning')
            if QCService.can_access_quality_control(user):
                return redirect(url_for('qc.quality_control_detail', order_id=order_id))
            return redirect(url_for('qc.quality_inspection_list'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/work_order_detail_inspector.html',
        order=work_order,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
    )


# ==================== 验收模块 ====================

@qc_bp.route('/acceptance/')
@login_required
def acceptance_list():
    """Acceptance list."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '')

    pagination = QCService.get_acceptance_list(
        user=user,
        keyword=keyword or None,
        page=page,
    )

    return render_template(
        'qc/acceptance_list.html',
        orders=pagination.items,
        pagination=pagination,
        keyword=keyword,
    )


@qc_bp.route('/acceptance/<int:order_id>')
@login_required
def acceptance_detail(order_id: int):
    """Acceptance detail."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.acceptance_list'))

    signatures = {signature.signer_role: signature for signature in work_order.signatures}
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
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    try:
        result = QCService.sign_acceptance(order_id, user)
        flash(result['message'], 'success' if result['completed'] else 'info')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.acceptance_detail', order_id=order_id))


@qc_bp.route('/acceptance/<int:order_id>/rollback', methods=['POST'])
@login_required
def acceptance_rollback(order_id: int):
    """Rollback acceptance and return the workflow."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    target = request.form.get('target', '').strip()
    reason = request.form.get('reason', '').strip()

    try:
        QCService.rollback_acceptance(order_id, target, reason, user)
        flash('流程已回退', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')

    return redirect(url_for('qc.acceptance_detail', order_id=order_id))


@qc_bp.route('/acceptance/<int:order_id>/print')
@login_required
def acceptance_print(order_id: int):
    """Printable acceptance sheet."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.acceptance_list'))

    signatures = {signature.signer_role: signature for signature in work_order.signatures}
    return render_template(
        'qc/acceptance_print.html',
        order=work_order,
        signatures=signatures,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
