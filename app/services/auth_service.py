"""
认证服务类
"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from app import db
from app.models import User, Role, VerificationCode, TrustedDevice
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
        if User.query.filter_by(username=username).first():
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
        if require_2fa and device_fingerprint:
            # 检查是否为受信任设备
            if EmailService.is_trusted_device(user.id, device_fingerprint):
                # 受信任设备，直接登录
                return AuthResult(success=True, user=user)
            
            # 检查用户是否绑定了邮箱
            if not user.email:
                # 没有邮箱，直接登录（记录警告日志）
                current_app.logger.warning(f'用户 {user.username} 未绑定邮箱，跳过两步验证')
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
        审核通过用户
        
        Args:
            user: 待审核用户
            approver: 审核人
            
        Returns:
            是否成功
        """
        user.is_active = True
        user.approved_by = approver.id
        user.approved_at = datetime.now()
        db.session.commit()
        return True
    
    @staticmethod
    def reject_user(user: User) -> bool:
        """
        审核拒绝用户（删除账号）
        
        Args:
            user: 待审核用户
            
        Returns:
            是否成功
        """
        db.session.delete(user)
        db.session.commit()
        return True
    
    @staticmethod
    def toggle_user_status(user: User) -> bool:
        """
        切换用户启用/禁用状态
        
        Args:
            user: 用户对象
            
        Returns:
            是否成功
        """
        user.is_active = not user.is_active
        db.session.commit()
        return True
