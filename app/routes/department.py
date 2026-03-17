"""
部门管理路由 - 超级管理员专用
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from app.services.contract_service import ContractService
from app.models import Department, Manager, User, Contract
from app import db
from app.utils.decorators import admin_required

department_bp = Blueprint('department', __name__, url_prefix='/department')


@department_bp.route('/')
@admin_required
def list_departments():
    """部门列表"""
    departments = Department.query.order_by(Department.name).all()
    
    # 统计每个部门的合同数和负责人
    dept_stats = {}
    for dept in departments:
        contract_count = Contract.query.filter_by(department=dept.name).count()
        manager_count = Manager.query.filter_by(department_id=dept.id).count()
        # 获取部门下的用户（销售经理和PM）
        users = User.query.join(User.role).filter(
            User.department_id == dept.id,
            User.role.has(code='sales_manager') | User.role.has(code='department_pm')
        ).all()
        dept_stats[dept.id] = {
            'contract_count': contract_count,
            'manager_count': manager_count,
            'users': users
        }
    
    return render_template('department/list.html', 
                         departments=departments,
                         dept_stats=dept_stats)


@department_bp.route('/new', methods=['POST'])
@admin_required
def new_department():
    """新增部门"""
    name = request.form.get('name', '').strip()
    
    if not name:
        flash('部门名称不能为空', 'warning')
        return redirect(url_for('department.list_departments'))
    
    # 检查是否已存在
    existing = Department.query.filter_by(name=name).first()
    if existing:
        flash(f'部门 "{name}" 已存在', 'warning')
        return redirect(url_for('department.list_departments'))
    
    try:
        dept = Department(name=name)
        db.session.add(dept)
        db.session.commit()
        flash(f'部门 "{name}" 创建成功', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'创建失败: {str(e)}', 'error')
    
    return redirect(url_for('department.list_departments'))


@department_bp.route('/<int:dept_id>/edit', methods=['POST'])
@admin_required
def edit_department(dept_id):
    """编辑部门名称"""
    dept = Department.query.get_or_404(dept_id)
    new_name = request.form.get('name', '').strip()
    
    if not new_name:
        flash('部门名称不能为空', 'warning')
        return redirect(url_for('department.list_departments'))
    
    # 检查新名称是否已被其他部门使用
    existing = Department.query.filter(Department.name == new_name, Department.id != dept_id).first()
    if existing:
        flash(f'部门名称 "{new_name}" 已被使用', 'warning')
        return redirect(url_for('department.list_departments'))
    
    try:
        old_name = dept.name
        dept.name = new_name
        
        # 更新所有相关合同的部门名称
        Contract.query.filter_by(department=old_name).update({'department': new_name})
        
        db.session.commit()
        flash(f'部门名称已更新为 "{new_name}"', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'更新失败: {str(e)}', 'error')
    
    return redirect(url_for('department.list_departments'))


@department_bp.route('/<int:dept_id>/delete', methods=['POST'])
@admin_required
def delete_department(dept_id):
    """删除部门"""
    dept = Department.query.get_or_404(dept_id)
    
    # 检查是否有关联的用户
    user_count = User.query.filter_by(department_id=dept_id).count()
    if user_count > 0:
        flash(f'无法删除：该部门下还有 {user_count} 个用户', 'error')
        return redirect(url_for('department.list_departments'))
    
    try:
        # 先删除部门下的负责人
        Manager.query.filter_by(department_id=dept_id).delete()
        
        name = dept.name
        db.session.delete(dept)
        db.session.commit()
        flash(f'部门 "{name}" 已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除失败: {str(e)}', 'error')
    
    return redirect(url_for('department.list_departments'))


@department_bp.route('/<int:dept_id>/managers')
@admin_required
def get_managers(dept_id):
    """获取部门的负责人列表（API）"""
    dept = Department.query.get_or_404(dept_id)
    managers = Manager.query.filter_by(department_id=dept_id).all()
    return jsonify({
        'managers': [{'id': m.id, 'name': m.name} for m in managers]
    })


@department_bp.route('/<int:dept_id>/managers/add', methods=['POST'])
@admin_required
def add_manager(dept_id):
    """添加负责人"""
    dept = Department.query.get_or_404(dept_id)
    name = request.form.get('name', '').strip()
    
    if not name:
        flash('负责人姓名不能为空', 'warning')
        return redirect(url_for('department.list_departments'))
    
    try:
        manager = Manager(name=name, department_id=dept_id)
        db.session.add(manager)
        db.session.commit()
        flash(f'负责人 "{name}" 已添加', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'添加失败: {str(e)}', 'error')
    
    return redirect(url_for('department.list_departments'))


@department_bp.route('/managers/<int:manager_id>/delete', methods=['POST'])
@admin_required
def delete_manager(manager_id):
    """删除负责人"""
    manager = Manager.query.get_or_404(manager_id)
    
    try:
        name = manager.name
        db.session.delete(manager)
        db.session.commit()
        flash(f'负责人 "{name}" 已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除失败: {str(e)}', 'error')
    
    return redirect(url_for('department.list_departments'))
