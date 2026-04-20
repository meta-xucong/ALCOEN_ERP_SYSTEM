"""
认证服务类
"""
import json
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from app import db
from app.models import User, Role, VerificationCode, TrustedDevice, QCUserBinding
from app.services.email_service import EmailService


class AuthResult:
    """认证结果类"""
    
    def __init__(self, success: bool = False, user: User = None, 
                 message: str = None, require_verify: bool = False,
                 device_fingerprint: str = None):
        self.success = success
        self.user = user
        self.message = message
        self.require_verify = require_verify  # 是否需要验证码验证
        self.device_fingerprint = device_fingerprint


class AuthService:
    """认证服务"""

    DEFAULT_PASSWORD = '1234.abcd'
    QC_ROLE_DEFINITIONS = {
        'qc_controller': {
            'name': '\u8d28\u91cf\u63a7\u5236\u5458',
            'description': '\u8d1f\u8d23\u5de5\u4ef6\u8ba2\u5355\u521b\u5efa\u3001\u8d28\u63a7\u6d41\u7a0b\u53d1\u8d77\u53ca\u9a8c\u6536\u786e\u8ba4',
            'permissions': [
                'qc_dashboard',
                'qc_work_order_view',
                'qc_work_order_create',
                'qc_work_order_edit',
                'qc_work_order_delete',
                'qc_acceptance_perform',
                'qc_acceptance_rollback',
            ],
            'level': 55,
        },
        'qc_inspector': {
            'name': '\u8d28\u91cf\u68c0\u6d4b\u5458',
            'description': '\u8d1f\u8d23\u5de5\u4ef6\u8ba2\u5355\u5404\u680f\u76ee\u7684\u8d28\u91cf\u68c0\u6d4b',
            'permissions': [
                'qc_dashboard',
                'qc_work_order_view',
                'qc_inspection_perform',
            ],
            'level': 45,
        },
    }

    @staticmethod
    def ensure_qc_roles() -> list[Role]:
        """Ensure QC-specific roles exist before rendering QC auth flows."""
        role_codes = tuple(AuthService.QC_ROLE_DEFINITIONS.keys())
        existing_roles = Role.query.filter(Role.code.in_(role_codes)).all()
        existing_by_code = {role.code: role for role in existing_roles}

        created = False
        for role_code, definition in AuthService.QC_ROLE_DEFINITIONS.items():
            if role_code in existing_by_code:
                continue

            role = Role(
                name=definition['name'],
                code=role_code,
                description=definition['description'],
                permissions=json.dumps(definition['permissions'], ensure_ascii=False),
                level=definition['level'],
            )
            db.session.add(role)
            existing_roles.append(role)
            existing_by_code[role_code] = role
            created = True

        if created:
            db.session.commit()

        return sorted(existing_roles, key=lambda role: role.level, reverse=True)
    
    @staticmethod
    def register_user(username: str, real_name: str, role_code: str = 'sales_manager',
                     department_id: int = None, email: str = None, phone: str = None) -> tuple:
        """
        注册新用户
        
        Args:
            username: 用户名
            real_name: 真实姓名
            role_code: 角色代码（默认销售经理）
            department_id: 部门ID
            email: 邮箱（必填，用于登录验证）
            phone: 电话
            
        Returns:
            (user, error_message)
        """
        # 检查用户名是否已存在
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            # 支持“QC-only 用户重新注册 ERP”：以 ERP 信息覆盖
            if existing_user.role.code in ['qc_controller', 'qc_inspector']:
                return AuthService._upgrade_qc_user_to_erp(
                    existing_user=existing_user,
                    real_name=real_name,
                    role_code=role_code,
                    department_id=department_id,
                    email=email,
                    phone=phone,
                )
            return None, '用户名已存在'
        
        # [v1.5] 邮箱必填验证
        if not email:
            return None, '请填写邮箱地址，用于登录安全验证'
        
        # 验证邮箱格式
        if not EmailService.validate_email(email):
            return None, '邮箱格式不正确'
        
        # 检查邮箱是否已被使用
        if User.query.filter_by(email=email).first():
            return None, '该邮箱已被注册'
        
        # 获取角色
        role = Role.query.filter_by(code=role_code).first()
        if not role:
            return None, '角色不存在'
        
        # 总经理和物流经理不需要部门（全部部门）
        if role_code not in ['logistics_manager', 'general_manager'] and not department_id:
            return None, '请选择所属部门'
        
        # 创建用户
        user = User(
            username=username,
            password_hash=generate_password_hash(AuthService.DEFAULT_PASSWORD),
            real_name=real_name,
            role_id=role.id,
            department_id=department_id if role_code not in ['logistics_manager', 'general_manager'] else None,
            email=email,
            phone=phone,
            is_active=False,  # 需要审核
            require_password_change=True
        )
        
        db.session.add(user)
        db.session.commit()
        
        return user, None

    @staticmethod
    def _upgrade_qc_user_to_erp(
        existing_user: User,
        real_name: str,
        role_code: str,
        department_id: int = None,
        email: str = None,
        phone: str = None,
    ) -> tuple:
        """将 QC-only 用户升级为 ERP 注册用户（ERP 信息覆盖）。"""
        if role_code in ['qc_controller', 'qc_inspector']:
            return None, '请选择 ERP 角色进行注册'

        if not email:
            return None, '请填写邮箱地址，用于登录安全验证'

        if not EmailService.validate_email(email):
            return None, '邮箱格式不正确'

        email_owner = User.query.filter(User.email == email, User.id != existing_user.id).first()
        if email_owner:
            return None, '该邮箱已被注册'

        role = Role.query.filter_by(code=role_code).first()
        if not role:
            return None, '角色不存在'

        if role_code not in ['logistics_manager', 'general_manager'] and not department_id:
            return None, '请选择所属部门'

        existing_user.real_name = real_name or existing_user.real_name
        existing_user.role_id = role.id
        existing_user.department_id = (
            department_id if role_code not in ['logistics_manager', 'general_manager'] else None
        )
        existing_user.email = email
        existing_user.phone = phone

        # ERP 注册信息优先：覆盖原 QC 密码并要求首次登录改密
        existing_user.password_hash = generate_password_hash(AuthService.DEFAULT_PASSWORD)
        existing_user.is_active = False
        existing_user.require_password_change = True
        existing_user.approved_by = None
        existing_user.approved_at = None

        db.session.commit()
        return existing_user, None
    
    @staticmethod
    def authenticate(username: str, password: str, user_agent: str = None,
                     ip_address: str = None, require_2fa: bool = True) -> AuthResult:
        """
        验证用户登录（支持两步验证）
        
        Args:
            username: 用户名
            password: 密码
            user_agent: 浏览器User-Agent
            ip_address: 用户IP地址
            require_2fa: 是否需要两步验证
            
        Returns:
            AuthResult对象
        """
        # 生成设备指纹
        device_fingerprint = None
        if user_agent and ip_address:
            device_fingerprint = EmailService.generate_device_fingerprint(user_agent, ip_address)
        
        user = User.query.filter_by(username=username).first()
        
        if not user:
            return AuthResult(message='用户名或密码错误')
        
        if not check_password_hash(user.password_hash, password):
            return AuthResult(message='用户名或密码错误')
        
        if not user.is_active:
            return AuthResult(message='账号尚未通过审核，请联系管理员')
        
        # 检查是否需要两步验证
        if require_2fa:
            # 超级管理员强制二次验证：不允许通过受信任设备直接放行
            if user.is_superadmin:
                if not user.email:
                    return AuthResult(message='管理员账号未绑定邮箱，无法完成安全验证')
                return AuthResult(
                    success=True,
                    user=user,
                    require_verify=True,
                    device_fingerprint=device_fingerprint
                )

            # 普通账号也必须绑定邮箱，确保验证码链路一致
            if not user.email:
                return AuthResult(message='账号未绑定邮箱，无法完成登录验证，请联系管理员绑定邮箱')

            if device_fingerprint and EmailService.is_trusted_device(user.id, device_fingerprint):
                # 受信任设备，直接登录
                return AuthResult(success=True, user=user)

            # 需要验证码验证
            return AuthResult(
                success=True,
                user=user,
                require_verify=True,
                device_fingerprint=device_fingerprint
            )
        
        return AuthResult(success=True, user=user)
    
    @staticmethod
    def update_login_info(user: User, ip: str = None):
        """更新用户登录信息"""
        user.last_login_at = datetime.now()
        user.last_login_ip = ip
        user.login_count += 1
        db.session.commit()
    
    @staticmethod
    def change_password(user: User, old_password: str, new_password: str) -> tuple:
        """
        修改密码
        
        Args:
            user: 用户对象
            old_password: 原密码
            new_password: 新密码
            
        Returns:
            (success, message)
        """
        # 验证原密码
        if not check_password_hash(user.password_hash, old_password):
            return False, '原密码错误'
        
        # 验证新密码长度
        if len(new_password) < 6:
            return False, '新密码至少6位'
        
        # 更新密码
        user.password_hash = generate_password_hash(new_password)
        user.require_password_change = False
        db.session.commit()
        
        return True, '密码修改成功'
    
    @staticmethod
    def force_change_password(user: User, new_password: str) -> tuple:
        """
        强制修改密码（首次登录）
        
        Args:
            user: 用户对象
            new_password: 新密码
            
        Returns:
            (success, message)
        """
        if len(new_password) < 6:
            return False, '密码至少6位'
        
        user.password_hash = generate_password_hash(new_password)
        user.require_password_change = False
        db.session.commit()
        
        return True, '密码修改成功，请重新登录'
    
    @staticmethod
    def reset_password(user: User) -> bool:
        """
        重置密码为默认密码
        
        Args:
            user: 用户对象
            
        Returns:
            是否成功
        """
        user.password_hash = generate_password_hash(AuthService.DEFAULT_PASSWORD)
        user.require_password_change = True
        db.session.commit()
        return True
    
    @staticmethod
    def approve_user(user: User, approver: User) -> bool:
        """
        审核通过用户。同时激活该用户关联的 QC 绑定（如有）。
        
        Args:
            user: 待审核用户
            approver: 审核人
            
        Returns:
            是否成功
        """
        user.is_active = True
        user.approved_by = approver.id
        user.approved_at = datetime.now()
        
        # 同步激活 QC 绑定
        binding = QCUserBinding.query.filter_by(user_id=user.id).first()
        if binding:
            binding.is_active = True
            binding.approved_by = approver.id
            binding.approved_at = datetime.now()
        
        db.session.commit()
        return True
    
    @staticmethod
    def reject_user(user: User) -> bool:
        """
        审核拒绝用户（删除账号）。先清理关联的 QC 绑定。
        
        Args:
            user: 待审核用户
            
        Returns:
            是否成功
        """
        # 先删除关联 QC 绑定，避免外键约束错误
        QCUserBinding.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        return True
    
    @staticmethod
    def toggle_user_status(user: User) -> bool:
        """
        切换用户启用/禁用状态，同时同步 QC 绑定状态。
        
        Args:
            user: 用户对象
            
        Returns:
            是否成功
        """
        user.is_active = not user.is_active
        
        binding = QCUserBinding.query.filter_by(user_id=user.id).first()
        if binding:
            binding.is_active = user.is_active
        
        db.session.commit()
        return True


    @staticmethod
    def register_qc_user(username: str, real_name: str, role_code: str = 'qc_inspector',
                        email: str = None, phone: str = None) -> tuple:
        """Register a QC account or create a pending QC binding for an ERP user."""
        from app.models import QCUserBinding

        AuthService.ensure_qc_roles()
        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            existing_binding = QCUserBinding.query.filter_by(user_id=existing_user.id).first()
            if existing_binding:
                return None, '\u8be5\u8d26\u53f7\u5df2\u7533\u8bf7\u6216\u5df2\u7ed1\u5b9a QC \u7cfb\u7edf\uff0c\u8bf7\u52ff\u91cd\u590d\u6ce8\u518c'

            role = Role.query.filter_by(code=role_code).first()
            if not role:
                return None, '\u89d2\u8272\u4e0d\u5b58\u5728'

            binding = QCUserBinding(
                user_id=existing_user.id,
                role_id=role.id,
                is_active=False
            )
            db.session.add(binding)
            db.session.commit()
            return existing_user, None

        if not email:
            return None, '\u8bf7\u586b\u5199\u90ae\u7bb1\u5730\u5740\uff0c\u7528\u4e8e\u767b\u5f55\u5b89\u5168\u9a8c\u8bc1'

        if not EmailService.validate_email(email):
            return None, '\u90ae\u7bb1\u683c\u5f0f\u4e0d\u6b63\u786e'

        if User.query.filter_by(email=email).first():
            return None, '\u8be5\u90ae\u7bb1\u5df2\u88ab\u6ce8\u518c'

        role = Role.query.filter_by(code=role_code).first()
        if not role:
            return None, '\u89d2\u8272\u4e0d\u5b58\u5728'

        user = User(
            username=username,
            password_hash=generate_password_hash(AuthService.DEFAULT_PASSWORD),
            real_name=real_name,
            role_id=role.id,
            email=email,
            phone=phone,
            is_active=False,
            require_password_change=True
        )
        db.session.add(user)
        db.session.flush()

        binding = QCUserBinding(
            user_id=user.id,
            role_id=role.id,
            is_active=False
        )
        db.session.add(binding)
        db.session.commit()
        return user, None
