"""用户管理服务类。"""

from __future__ import annotations

import json

from app import db
from app.models import (
    ERP_PERMISSIONS,
    QC_ADMIN_ROLE_CODES,
    QC_PERMISSIONS,
    QC_ROLE_CODES as QC_ONLY_ROLE_CODES,
    QC_ROLE_EDITABLE_PERMISSIONS,
    Role,
    User,
)


class UserService:
    """用户管理服务。"""

    QC_ROLE_CODES = QC_ONLY_ROLE_CODES

    @staticmethod
    def is_qc_role_code(role_code: str | None) -> bool:
        """Whether the role code belongs to the QC-only role set."""
        return role_code in UserService.QC_ROLE_CODES

    @staticmethod
    def is_qc_only_user(user: User | None) -> bool:
        """Whether the user should stay hidden from ERP system-management views."""
        return bool(user and user.role and UserService.is_qc_role_code(user.role.code))

    @staticmethod
    def _apply_erp_scope(query, include_qc: bool = False):
        """Hide QC-only rows from ERP-facing queries unless explicitly requested."""
        if include_qc:
            return query
        return query.filter(~Role.code.in_(UserService.QC_ROLE_CODES))

    @staticmethod
    def get_user_list(page=1, per_page=20, role_code=None, status=None, keyword=None, include_qc=False):
        """获取用户列表。"""
        query = UserService._apply_erp_scope(User.query.join(Role), include_qc=include_qc)

        if role_code:
            role = Role.query.filter_by(code=role_code).first()
            if not role:
                query = query.filter(db.text('1=0'))
            elif include_qc or not UserService.is_qc_role_code(role.code):
                query = query.filter(User.role_id == role.id)
            else:
                query = query.filter(db.text('1=0'))

        if status == 'active':
            query = query.filter(User.is_active.is_(True))
        elif status == 'inactive':
            query = query.filter(User.is_active.is_(False))
        elif status == 'pending':
            query = query.filter(User.is_active.is_(False), User.approved_at.is_(None))

        if keyword:
            query = query.filter(
                db.or_(
                    User.username.contains(keyword),
                    User.real_name.contains(keyword),
                    User.email.contains(keyword),
                )
            )

        return query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_pending_users(page=1, per_page=20, include_qc=False):
        """获取待审核用户列表。"""
        query = UserService._apply_erp_scope(User.query.join(Role), include_qc=include_qc).filter(
            User.is_active.is_(False),
            User.approved_at.is_(None),
        )
        return query.order_by(User.created_at.asc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_user_by_id(user_id, include_qc=False):
        """根据 ID 获取用户。"""
        user = User.query.get(user_id)
        if not include_qc and UserService.is_qc_only_user(user):
            return None
        return user

    @staticmethod
    def update_user(user_id, data, include_qc=False):
        """更新用户信息。"""
        user = User.query.get(user_id)
        if not user:
            return False, '用户不存在'
        if not include_qc and UserService.is_qc_only_user(user):
            return False, '该账号仅属于 QC 系统，请在 QC 系统中管理'

        try:
            if 'real_name' in data:
                user.real_name = data['real_name']
            if 'email' in data:
                user.email = data['email']
            if 'phone' in data:
                user.phone = data['phone']
            if 'role_id' in data:
                role = Role.query.get(data['role_id'])
                if not role:
                    return False, '角色不存在'
                if not include_qc and UserService.is_qc_role_code(role.code):
                    return False, 'QC 专属角色不能在 ERP 系统中分配'
                user.role_id = data['role_id']
            if 'department_id' in data:
                user.department_id = data['department_id']

            db.session.commit()
            return True, '更新成功'
        except Exception as exc:
            db.session.rollback()
            return False, f'更新失败: {exc}'

    @staticmethod
    def delete_user(user_id, include_qc=False):
        """删除用户。"""
        user = User.query.get(user_id)
        if not user:
            return False, '用户不存在'
        if not include_qc and UserService.is_qc_only_user(user):
            return False, '该账号仅属于 QC 系统，请在 QC 系统中删除'
        if user.is_superadmin:
            return False, '不能删除超级管理员账号'

        try:
            db.session.delete(user)
            db.session.commit()
            return True, '删除成功'
        except Exception as exc:
            db.session.rollback()
            return False, f'删除失败: {exc}'

    @staticmethod
    def get_all_roles(include_qc=False):
        """获取角色列表。"""
        query = Role.query
        if not include_qc:
            query = query.filter(~Role.code.in_(UserService.QC_ROLE_CODES))
        return query.order_by(Role.level.desc()).all()

    @staticmethod
    def get_role_by_id(role_id, include_qc=False):
        """根据 ID 获取角色。"""
        role = Role.query.get(role_id)
        if role and not include_qc and UserService.is_qc_role_code(role.code):
            return None
        return role

    @staticmethod
    def update_role_permissions(role_id, permissions, scope='erp'):
        """更新角色权限。"""
        role = Role.query.get(role_id)
        if not role:
            return False, '角色不存在'
        if role.code == 'superadmin':
            return False, '不能修改超级管理员权限'

        try:
            current_permissions = role.get_permission_codes()

            if scope == 'qc':
                allowed_permissions = set(QC_ROLE_EDITABLE_PERMISSIONS.get(role.code, {}).keys())
                preserved_permissions = [
                    permission_code for permission_code in current_permissions
                    if permission_code not in QC_PERMISSIONS
                ]
            else:
                allowed_permissions = set(ERP_PERMISSIONS.keys())
                preserved_permissions = [
                    permission_code for permission_code in current_permissions
                    if permission_code in QC_PERMISSIONS
                ]

            normalized_permissions = []
            for permission_code in permissions:
                if permission_code in allowed_permissions and permission_code not in normalized_permissions:
                    normalized_permissions.append(permission_code)

            role.permissions = json.dumps(preserved_permissions + normalized_permissions, ensure_ascii=False)
            db.session.commit()
            return True, '权限更新成功'
        except Exception as exc:
            db.session.rollback()
            return False, f'更新失败: {exc}'
