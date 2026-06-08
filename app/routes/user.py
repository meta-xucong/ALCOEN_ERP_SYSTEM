"""用户管理路由。"""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.models import Department
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.utils.decorators import login_required, user_manage_required

user_bp = Blueprint('user', __name__, url_prefix='/user')


def _redirect_qc_review_entry():
    """Send ERP-side QC approval attempts back to the QC admin module."""
    if g.current_user and (g.current_user.is_superadmin or g.current_user.role.code == 'general_manager'):
        return redirect(url_for('qc.qc_admin_pending'))
    return redirect(url_for('user.pending_users'))


@user_bp.route('/')
@user_manage_required
def list_users():
    """ERP 用户列表。"""
    page = request.args.get('page', 1, type=int)
    role_code = request.args.get('role', '').strip()
    status = request.args.get('status', '').strip()
    keyword = request.args.get('keyword', '').strip()

    pagination = UserService.get_user_list(
        page=page,
        role_code=role_code or None,
        status=status or None,
        keyword=keyword or None,
    )
    roles = UserService.get_all_roles()

    return render_template(
        'user/list.html',
        users=pagination.items,
        pagination=pagination,
        roles=roles,
        role=role_code,
        status=status,
        keyword=keyword,
    )


@user_bp.route('/pending')
@login_required
def pending_users():
    """ERP 待审核用户列表，仅包含 ERP 注册申请。"""
    if not g.current_user.has_permission('user_approve'):
        flash('需要用户审核权限', 'error')
        return redirect(url_for('main.index'))

    page = request.args.get('page', 1, type=int)
    pagination = UserService.get_pending_users(page=page)

    return render_template(
        'user/pending.html',
        users=pagination.items,
        pagination=pagination,
    )


@user_bp.route('/<int:user_id>')
@login_required
def view_user(user_id: int):
    """查看 ERP 用户详情。"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))

    if user_id != g.current_user.id and not g.current_user.has_permission('user_manage'):
        flash('没有权限查看该用户', 'error')
        return redirect(url_for('main.index'))

    return render_template('user/detail.html', user=user)


@user_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@user_manage_required
def edit_user(user_id: int):
    """编辑 ERP 用户。"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))

    if user.is_superadmin and not g.current_user.is_superadmin:
        flash('不能编辑超级管理员账号', 'error')
        return redirect(url_for('user.list_users'))

    departments = Department.query.order_by(Department.name).all()
    roles = UserService.get_all_roles()

    if request.method == 'POST':
        real_name = request.form.get('real_name', '').strip()
        email = request.form.get('email', '').strip() or None
        phone = request.form.get('phone', '').strip() or None
        role_id = request.form.get('role_id', type=int)
        department_ids = []
        for raw_value in request.form.getlist('department_ids'):
            try:
                department_id = int(raw_value)
            except (TypeError, ValueError):
                continue
            if department_id not in department_ids:
                department_ids.append(department_id)

        if role_id:
            role = UserService.get_role_by_id(role_id)
            if role and role.code == 'logistics_manager':
                department_ids = []

        success, message = UserService.update_user(
            user_id,
            {
                'real_name': real_name,
                'email': email,
                'phone': phone,
                'role_id': role_id,
                'department_ids': department_ids,
            },
        )
        flash(message, 'success' if success else 'error')
        if success:
            return redirect(url_for('user.list_users'))

    return render_template(
        'user/form.html',
        user=user,
        roles=roles,
        departments=departments,
    )


@user_bp.route('/<int:user_id>/approve', methods=['POST'])
@login_required
def approve_user(user_id: int):
    """审核通过 ERP 用户。"""
    if not g.current_user.has_permission('user_approve'):
        flash('需要用户审核权限', 'error')
        return redirect(url_for('main.index'))

    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.pending_users'))

    success = AuthService.approve_user(user, g.current_user)
    flash(
        f'用户 {user.username} 审核通过' if success else '审核失败',
        'success' if success else 'error',
    )
    return redirect(url_for('user.pending_users'))


@user_bp.route('/<int:user_id>/reject', methods=['POST'])
@login_required
def reject_user(user_id: int):
    """拒绝 ERP 用户注册申请。"""
    if not g.current_user.has_permission('user_approve'):
        flash('需要用户审核权限', 'error')
        return redirect(url_for('main.index'))

    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.pending_users'))

    success = AuthService.reject_user(user)
    flash(
        f'已拒绝用户 {user.username} 的注册申请' if success else '操作失败',
        'success' if success else 'error',
    )
    return redirect(url_for('user.pending_users'))


@user_bp.route('/qc-binding/<int:binding_id>/approve', methods=['POST'])
@login_required
def approve_qc_binding(binding_id: int):
    """ERP 侧不再处理 QC 角色申请。"""
    flash('QC 角色申请仅能在 QC 系统管理中审核', 'warning')
    return _redirect_qc_review_entry()


@user_bp.route('/qc-binding/<int:binding_id>/reject', methods=['POST'])
@login_required
def reject_qc_binding(binding_id: int):
    """ERP 侧不再处理 QC 角色申请。"""
    flash('QC 角色申请仅能在 QC 系统管理中审核', 'warning')
    return _redirect_qc_review_entry()


@user_bp.route('/<int:user_id>/toggle', methods=['POST'])
@user_manage_required
def toggle_user(user_id: int):
    """启用或禁用 ERP 用户。"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))

    if user.is_superadmin:
        flash('不能禁用超级管理员账号', 'error')
        return redirect(url_for('user.list_users'))

    success = AuthService.toggle_user_status(user)
    if success:
        status = '启用' if user.is_active else '禁用'
        flash(f'用户 {user.username} 已{status}', 'success')
    else:
        flash('操作失败', 'error')
    return redirect(url_for('user.list_users'))


@user_bp.route('/<int:user_id>/reset-password', methods=['POST'])
@user_manage_required
def reset_password(user_id: int):
    """重置 ERP 用户密码。"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))

    success = AuthService.reset_password(user)
    flash(
        f'用户 {user.username} 密码已重置为 1234.abcd，下次登录需修改' if success else '重置失败',
        'success' if success else 'error',
    )
    return redirect(url_for('user.list_users'))


@user_bp.route('/<int:user_id>/delete', methods=['POST'])
@user_manage_required
def delete_user(user_id: int):
    """删除 ERP 用户。"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))

    if user_id == g.current_user.id:
        flash('不能删除自己的账号', 'error')
        return redirect(url_for('user.list_users'))

    success, message = UserService.delete_user(user_id)
    flash(message, 'success' if success else 'error')
    return redirect(url_for('user.list_users'))


@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    """个人资料。"""
    user = g.current_user

    if request.method == 'POST':
        real_name = request.form.get('real_name', '').strip()
        email = request.form.get('email', '').strip() or None
        phone = request.form.get('phone', '').strip() or None

        success, message = UserService.update_user(
            user.id,
            {
                'real_name': real_name,
                'email': email,
                'phone': phone,
            },
            include_qc=True,
        )
        flash('个人资料更新成功' if success else message, 'success' if success else 'error')
        return redirect(url_for('user.user_profile'))

    return render_template('user/profile.html', user=user)
