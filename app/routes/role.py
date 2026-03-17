"""
角色权限管理路由
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from app.services.user_service import UserService
from app.models import Role, PERMISSIONS
from app.utils.decorators import login_required

role_bp = Blueprint('role', __name__, url_prefix='/role')


@role_bp.route('/')
@login_required
def list_roles():
    """角色列表"""
    # 检查权限
    if not g.current_user.has_permission('role_manage'):
        flash('需要角色管理权限', 'error')
        return redirect(url_for('main.index'))
    
    roles = UserService.get_all_roles()
    return render_template('role/list.html', roles=roles, permissions=PERMISSIONS)


@role_bp.route('/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_role(role_id):
    """编辑角色权限"""
    # 检查权限
    if not g.current_user.has_permission('role_manage'):
        flash('需要角色管理权限', 'error')
        return redirect(url_for('main.index'))
    
    role = UserService.get_role_by_id(role_id)
    if not role:
        flash('角色不存在', 'error')
        return redirect(url_for('role.list_roles'))
    
    # 不能修改超级管理员权限
    if role.code == 'superadmin':
        flash('不能修改超级管理员权限', 'error')
        return redirect(url_for('role.list_roles'))
    
    if request.method == 'POST':
        # 获取选中的权限
        selected_permissions = request.form.getlist('permissions')
        
        success, message = UserService.update_role_permissions(role_id, selected_permissions)
        if success:
            flash(message, 'success')
            return redirect(url_for('role.list_roles'))
        else:
            flash(message, 'error')
    
    # 解析当前权限
    import json
    current_permissions = []
    if role.permissions:
        try:
            current_permissions = json.loads(role.permissions)
        except:
            pass
    
    return render_template('role/edit.html',
                         role=role,
                         permissions=PERMISSIONS,
                         current_permissions=current_permissions)
