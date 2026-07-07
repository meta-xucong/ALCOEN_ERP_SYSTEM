"""部门管理路由。"""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import or_

from app import db
from app.models import Contract, Department, User, UserDepartment
from app.utils.decorators import admin_required


department_bp = Blueprint('department', __name__, url_prefix='/department')


@department_bp.route('/')
@admin_required
def list_departments():
    """部门列表。"""
    departments = Department.query.order_by(Department.name).all()

    dept_stats = {}
    for dept in departments:
        contract_count = Contract.query.filter_by(department=dept.name).count()
        users = (
            User.query.outerjoin(UserDepartment, UserDepartment.user_id == User.id)
            .join(User.role)
            .filter(
                or_(User.department_id == dept.id, UserDepartment.department_id == dept.id),
                User.role.has(code='sales_manager') | User.role.has(code='department_pm'),
            )
            .distinct()
            .all()
        )
        dept_stats[dept.id] = {
            'contract_count': contract_count,
            'users': users,
        }

    return render_template('department/list.html', departments=departments, dept_stats=dept_stats)


@department_bp.route('/new', methods=['POST'])
@admin_required
def new_department():
    """新增部门。"""
    name = request.form.get('name', '').strip()

    if not name:
        flash('部门名称不能为空', 'warning')
        return redirect(url_for('department.list_departments'))

    existing = Department.query.filter_by(name=name).first()
    if existing:
        flash(f'部门 "{name}" 已存在', 'warning')
        return redirect(url_for('department.list_departments'))

    try:
        dept = Department(name=name)
        db.session.add(dept)
        db.session.commit()
        flash(f'部门 "{name}" 创建成功', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'创建失败: {exc}', 'error')

    return redirect(url_for('department.list_departments'))


@department_bp.route('/<int:dept_id>/edit', methods=['POST'])
@admin_required
def edit_department(dept_id):
    """编辑部门名称。"""
    dept = Department.query.get_or_404(dept_id)
    new_name = request.form.get('name', '').strip()

    if not new_name:
        flash('部门名称不能为空', 'warning')
        return redirect(url_for('department.list_departments'))

    existing = Department.query.filter(Department.name == new_name, Department.id != dept_id).first()
    if existing:
        flash(f'部门名称 "{new_name}" 已被使用', 'warning')
        return redirect(url_for('department.list_departments'))

    try:
        old_name = dept.name
        dept.name = new_name
        Contract.query.filter_by(department=old_name).update({'department': new_name})
        db.session.commit()
        flash(f'部门名称已更新为 "{new_name}"', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'更新失败: {exc}', 'error')

    return redirect(url_for('department.list_departments'))


@department_bp.route('/<int:dept_id>/delete', methods=['POST'])
@admin_required
def delete_department(dept_id):
    """删除部门。"""
    dept = Department.query.get_or_404(dept_id)

    user_count = (
        User.query.outerjoin(UserDepartment, UserDepartment.user_id == User.id)
        .filter(or_(User.department_id == dept_id, UserDepartment.department_id == dept_id))
        .distinct()
        .count()
    )
    if user_count > 0:
        flash(f'无法删除：该部门下还有 {user_count} 个用户', 'error')
        return redirect(url_for('department.list_departments'))

    contract_count = Contract.query.filter_by(department=dept.name).count()
    if contract_count > 0:
        flash(f'无法删除：该部门下还有 {contract_count} 个合同', 'error')
        return redirect(url_for('department.list_departments'))

    try:
        name = dept.name
        db.session.delete(dept)
        db.session.commit()
        flash(f'部门 "{name}" 已删除', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'删除失败: {exc}', 'error')

    return redirect(url_for('department.list_departments'))


@department_bp.route('/<int:dept_id>/users')
@admin_required
def get_department_users(dept_id):
    """获取部门用户列表，用于 PM 选择负责人。"""
    Department.query.get_or_404(dept_id)
    users = (
        User.query.outerjoin(UserDepartment, UserDepartment.user_id == User.id)
        .filter(
            or_(User.department_id == dept_id, UserDepartment.department_id == dept_id),
            User.is_active.is_(True),
        )
        .distinct()
        .all()
    )
    return jsonify(
        {
            'users': [
                {
                    'id': user.id,
                    'name': user.real_name or user.username,
                    'username': user.username,
                    'role': user.role.name if user.role else None,
                    'role_code': user.role.code if user.role else None,
                }
                for user in users
            ]
        }
    )
