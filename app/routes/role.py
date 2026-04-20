"""角色权限管理路由。"""

import json

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.models import PERMISSIONS
from app.services.user_service import UserService
from app.utils.decorators import login_required

role_bp = Blueprint('role', __name__, url_prefix='/role')


@role_bp.route('/')
@login_required
def list_roles():
    """ERP 角色列表。"""
    if not g.current_user.has_permission('role_manage'):
        flash('需要角色管理权限', 'error')
        return redirect(url_for('main.index'))

    roles = UserService.get_all_roles()
    return render_template('role/list.html', roles=roles, permissions=PERMISSIONS)


@role_bp.route('/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_role(role_id: int):
    """编辑 ERP 角色权限。"""
    if not g.current_user.has_permission('role_manage'):
        flash('需要角色管理权限', 'error')
        return redirect(url_for('main.index'))

    role = UserService.get_role_by_id(role_id)
    if not role:
        flash('角色不存在', 'error')
        return redirect(url_for('role.list_roles'))

    if role.code == 'superadmin':
        flash('不能修改超级管理员权限', 'error')
        return redirect(url_for('role.list_roles'))

    if request.method == 'POST':
        selected_permissions = request.form.getlist('permissions')
        success, message = UserService.update_role_permissions(role_id, selected_permissions)
        flash(message, 'success' if success else 'error')
        if success:
            return redirect(url_for('role.list_roles'))

    current_permissions = []
    if role.permissions:
        try:
            current_permissions = json.loads(role.permissions)
        except Exception:
            current_permissions = []

    return render_template(
        'role/edit.html',
        role=role,
        permissions=PERMISSIONS,
        current_permissions=current_permissions,
    )
