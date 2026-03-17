"""
用户管理服务类
"""
from datetime import datetime
from app import db
from app.models import User, Role


class UserService:
    """用户管理服务"""
    
    @staticmethod
    def get_user_list(page=1, per_page=20, role_code=None, status=None, keyword=None):
        """
        获取用户列表
        
        Args:
            page: 页码
            per_page: 每页数量
            role_code: 角色筛选
            status: 状态筛选 (active/inactive/pending)
            keyword: 关键词搜索
            
        Returns:
            Pagination 对象
        """
        query = User.query
        
        # 角色筛选
        if role_code:
            role = Role.query.filter_by(code=role_code).first()
            if role:
                query = query.filter(User.role_id == role.id)
        
        # 状态筛选
        if status == 'active':
            query = query.filter(User.is_active == True)
        elif status == 'inactive':
            query = query.filter(User.is_active == False)
        elif status == 'pending':
            query = query.filter(User.is_active == False, User.approved_at.is_(None))
        
        # 关键词搜索
        if keyword:
            query = query.filter(
                db.or_(
                    User.username.contains(keyword),
                    User.real_name.contains(keyword),
                    User.email.contains(keyword)
                )
            )
        
        return query.order_by(User.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    
    @staticmethod
    def get_pending_users(page=1, per_page=20):
        """
        获取待审核用户列表
        
        Returns:
            Pagination 对象
        """
        return User.query.filter(
            User.is_active == False,
            User.approved_at.is_(None)
        ).order_by(User.created_at.asc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    
    @staticmethod
    def get_user_by_id(user_id):
        """根据ID获取用户"""
        return User.query.get(user_id)
    
    @staticmethod
    def update_user(user_id, data):
        """
        更新用户信息
        
        Args:
            user_id: 用户ID
            data: 更新数据字典
            
        Returns:
            (success, message)
        """
        user = User.query.get(user_id)
        if not user:
            return False, '用户不存在'
        
        try:
            # 更新字段
            if 'real_name' in data:
                user.real_name = data['real_name']
            if 'email' in data:
                user.email = data['email']
            if 'phone' in data:
                user.phone = data['phone']
            if 'role_id' in data:
                user.role_id = data['role_id']
            if 'department_id' in data:
                user.department_id = data['department_id']
            
            db.session.commit()
            return True, '更新成功'
        except Exception as e:
            db.session.rollback()
            return False, f'更新失败: {str(e)}'
    
    @staticmethod
    def delete_user(user_id):
        """
        删除用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            (success, message)
        """
        user = User.query.get(user_id)
        if not user:
            return False, '用户不存在'
        
        # 不能删除超级管理员
        if user.is_superadmin:
            return False, '不能删除超级管理员账号'
        
        try:
            db.session.delete(user)
            db.session.commit()
            return True, '删除成功'
        except Exception as e:
            db.session.rollback()
            return False, f'删除失败: {str(e)}'
    
    @staticmethod
    def get_all_roles():
        """获取所有角色列表"""
        return Role.query.order_by(Role.level.desc()).all()
    
    @staticmethod
    def get_role_by_id(role_id):
        """根据ID获取角色"""
        return Role.query.get(role_id)
    
    @staticmethod
    def update_role_permissions(role_id, permissions):
        """
        更新角色权限
        
        Args:
            role_id: 角色ID
            permissions: 权限列表
            
        Returns:
            (success, message)
        """
        import json
        
        role = Role.query.get(role_id)
        if not role:
            return False, '角色不存在'
        
        # 不能修改超级管理员权限
        if role.code == 'superadmin':
            return False, '不能修改超级管理员权限'
        
        try:
            role.permissions = json.dumps(permissions)
            db.session.commit()
            return True, '权限更新成功'
        except Exception as e:
            db.session.rollback()
            return False, f'更新失败: {str(e)}'
