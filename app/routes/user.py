"""
用户管理路由
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from app.services.user_service import UserService
from app.services.auth_service import AuthService
from app.services.contract_service import ContractService
from app.models import User, Role, Department
from app.utils.decorators import login_required, user_manage_required

user_bp = Blueprint('user', __name__, url_prefix='/user')


@user_bp.route('/')
@user_manage_required
def list_users():
    """用户列表"""
    page = request.args.get('page', 1, type=int)
    role_code = request.args.get('role', '')
    status = request.args.get('status', '')
    keyword = request.args.get('keyword', '')
    
    pagination = UserService.get_user_list(
        page=page,
        role_code=role_code or None,
        status=status or None,
        keyword=keyword or None
    )
    
    roles = UserService.get_all_roles()
    
    return render_template('user/list.html',
                         users=pagination.items,
                         pagination=pagination,
                         roles=roles,
                         role=role_code,
                         status=status,
                         keyword=keyword)


@user_bp.route('/pending')
@login_required
def pending_users():
    """待审核用户列表"""
    # 检查权限
    if not g.current_user.has_permission('user_approve'):
        flash('需要用户审核权限', 'error')
        return redirect(url_for('main.index'))
    
    page = request.args.get('page', 1, type=int)
    pagination = UserService.get_pending_users(page=page)
    
    return render_template('user/pending.html',
                         users=pagination.items,
                         pagination=pagination)


@user_bp.route('/<int:user_id>')
@login_required
def view_user(user_id):
    """查看用户详情"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))
    
    # 只能查看自己或有管理权限
    if user_id != g.current_user.id and not g.current_user.has_permission('user_manage'):
        flash('没有权限查看此用户', 'error')
        return redirect(url_for('main.index'))
    
    return render_template('user/detail.html', user=user)


@user_bp.route('/<int:user_id>/edit', methods=['GET', 'POST'])
@user_manage_required
def edit_user(user_id):
    """编辑用户"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))
    
    # 不能编辑超级管理员（除非是超级管理员自己）
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
        department_id = request.form.get('department_id', type=int) or None
        
        # 获取角色代码
        role = Role.query.get(role_id)
        if role and role.code == 'logistics_manager':
            department_id = None  # 物流经理不需要部门
        
        success, message = UserService.update_user(user_id, {
            'real_name': real_name,
            'email': email,
            'phone': phone,
            'role_id': role_id,
            'department_id': department_id
        })
        
        if success:
            flash(message, 'success')
            return redirect(url_for('user.list_users'))
        else:
            flash(message, 'error')
    
    return render_template('user/form.html',
                         user=user,
                         roles=roles,
                         departments=departments)


@user_bp.route('/<int:user_id>/approve', methods=['POST'])
@login_required
def approve_user(user_id):
    """审核通过用户"""
    if not g.current_user.has_permission('user_approve'):
        flash('需要用户审核权限', 'error')
        return redirect(url_for('main.index'))
    
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.pending_users'))
    
    success = AuthService.approve_user(user, g.current_user)
    if success:
        flash(f'用户 {user.username} 审核通过', 'success')
    else:
        flash('审核失败', 'error')
    
    return redirect(url_for('user.pending_users'))


@user_bp.route('/<int:user_id>/reject', methods=['POST'])
@login_required
def reject_user(user_id):
    """审核拒绝用户（删除）"""
    if not g.current_user.has_permission('user_approve'):
        flash('需要用户审核权限', 'error')
        return redirect(url_for('main.index'))
    
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.pending_users'))
    
    success = AuthService.reject_user(user)
    if success:
        flash(f'已拒绝用户 {user.username} 的注册申请', 'success')
    else:
        flash('操作失败', 'error')
    
    return redirect(url_for('user.pending_users'))


@user_bp.route('/<int:user_id>/toggle', methods=['POST'])
@user_manage_required
def toggle_user(user_id):
    """启用/禁用用户"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))
    
    # 不能禁用超级管理员
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
def reset_password(user_id):
    """重置用户密码"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))
    
    success = AuthService.reset_password(user)
    if success:
        flash(f'用户 {user.username} 密码已重置为 1234.abcd，下次登录需修改', 'success')
    else:
        flash('重置失败', 'error')
    
    return redirect(url_for('user.list_users'))


@user_bp.route('/<int:user_id>/delete', methods=['POST'])
@user_manage_required
def delete_user(user_id):
    """删除用户"""
    user = UserService.get_user_by_id(user_id)
    if not user:
        flash('用户不存在', 'error')
        return redirect(url_for('user.list_users'))
    
    # 不能删除自己
    if user_id == g.current_user.id:
        flash('不能删除自己的账号', 'error')
        return redirect(url_for('user.list_users'))
    
    success, message = UserService.delete_user(user_id)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(url_for('user.list_users'))


@user_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    """个人资料"""
    user = g.current_user
    
    if request.method == 'POST':
        real_name = request.form.get('real_name', '').strip()
        email = request.form.get('email', '').strip() or None
        phone = request.form.get('phone', '').strip() or None
        
        success, message = UserService.update_user(user.id, {
            'real_name': real_name,
            'email': email,
            'phone': phone
        })
        
        if success:
            flash('个人资料更新成功', 'success')
        else:
            flash(message, 'error')
        
        return redirect(url_for('user.user_profile'))
    
    return render_template('user/profile.html', user=user)
