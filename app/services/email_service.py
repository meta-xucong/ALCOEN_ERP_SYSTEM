"""
邮件服务类 - 处理邮件发送
"""
import smtplib
import random
import re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, render_template_string
from app import db
from app.models import User, VerificationCode, TrustedDevice


class EmailService:
    """邮件服务"""
    
    @staticmethod
    def send_email(to_email: str, subject: str, html_content: str) -> tuple:
        """
        发送邮件
        
        Args:
            to_email: 收件人邮箱
            subject: 邮件主题
            html_content: HTML内容
            
        Returns:
            (success, error_message)
        """
        try:
            mail_server = current_app.config.get('MAIL_SERVER')
            mail_port = current_app.config.get('MAIL_PORT', 465)
            mail_use_ssl = current_app.config.get('MAIL_USE_SSL', True)
            mail_username = current_app.config.get('MAIL_USERNAME')
            mail_password = current_app.config.get('MAIL_PASSWORD')
            mail_sender = current_app.config.get('MAIL_DEFAULT_SENDER', mail_username)
            
            # 检查配置
            if not all([mail_server, mail_username, mail_password]):
                return False, '邮件服务未配置，请联系管理员'
            
            # 解析发件人
            if isinstance(mail_sender, tuple):
                sender_name, sender_email = mail_sender
            else:
                sender_name, sender_email = 'ERP系统', mail_sender
            
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f'{sender_name} <{sender_email}>'
            msg['To'] = to_email
            
            # 添加HTML内容
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 连接SMTP服务器并发送
            if mail_use_ssl:
                server = smtplib.SMTP_SSL(mail_server, mail_port)
            else:
                server = smtplib.SMTP(mail_server, mail_port)
                server.starttls()
            
            server.login(mail_username, mail_password)
            server.sendmail(sender_email, to_email, msg.as_string())
            server.quit()
            
            return True, None
            
        except Exception as e:
            current_app.logger.error(f'邮件发送失败: {str(e)}')
            return False, f'邮件发送失败: {str(e)}'
    
    @staticmethod
    def generate_verify_code(length: int = 4) -> str:
        """
        生成数字验证码
        
        Args:
            length: 验证码长度
            
        Returns:
            数字验证码字符串
        """
        return ''.join([str(random.randint(0, 9)) for _ in range(length)])
    
    @staticmethod
    def create_verification_code(user: User, purpose: str = 'login',
                                  device_fingerprint: str = None,
                                  ip_address: str = None) -> tuple:
        """
        创建新的验证码
        
        Args:
            user: 用户对象
            purpose: 用途
            device_fingerprint: 设备指纹
            ip_address: IP地址
            
        Returns:
            (code, error_message)
        """
        # 清除该用户该用途的旧验证码
        VerificationCode.query.filter_by(
            user_id=user.id,
            purpose=purpose
        ).delete()
        
        # 生成新验证码
        code_length = current_app.config.get('VERIFY_CODE_LENGTH', 4)
        code = EmailService.generate_verify_code(code_length)
        
        # 计算过期时间
        expire_minutes = current_app.config.get('VERIFY_CODE_EXPIRE_MINUTES', 15)
        expires_at = datetime.now() + timedelta(minutes=expire_minutes)
        
        # 保存到数据库
        verify_code = VerificationCode(
            user_id=user.id,
            code=code,
            purpose=purpose,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            expires_at=expires_at
        )
        db.session.add(verify_code)
        db.session.commit()
        
        return code, None
    
    @staticmethod
    def send_verify_code_email(user: User, code: str, purpose: str = 'login') -> tuple:
        """
        发送验证码邮件
        
        Args:
            user: 用户对象
            code: 验证码
            purpose: 用途
            
        Returns:
            (success, error_message)
        """
        if not user.email:
            return False, '用户未绑定邮箱'
        
        # 验证邮箱格式
        if not EmailService.validate_email(user.email):
            return False, '用户邮箱格式不正确'
        
        # 根据用途确定邮件内容
        purpose_text = {
            'login': '登录验证',
            'reset_password': '密码重置',
            'register': '注册验证'
        }.get(purpose, '安全验证')
        
        expire_minutes = current_app.config.get('VERIFY_CODE_EXPIRE_MINUTES', 15)
        
        # HTML邮件模板
        html_template = '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: "Microsoft YaHei", Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
                .container { max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }
                .header h1 { margin: 0; font-size: 24px; }
                .content { padding: 30px; }
                .code-box { background: #f8f9fa; border: 2px dashed #667eea; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0; }
                .code { font-size: 36px; font-weight: bold; color: #667eea; letter-spacing: 8px; }
                .info { color: #666; font-size: 14px; line-height: 1.6; }
                .warning { background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; color: #856404; }
                .footer { background: #f8f9fa; padding: 20px; text-align: center; color: #999; font-size: 12px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔐 ERP系统 - {{ purpose_text }}</h1>
                </div>
                <div class="content">
                    <p class="info">您好，<strong>{{ user.real_name or user.username }}</strong>：</p>
                    <p class="info">您正在进行 <strong>{{ purpose_text }}</strong> 操作，请使用以下验证码完成验证：</p>
                    
                    <div class="code-box">
                        <div class="code">{{ code }}</div>
                    </div>
                    
                    <div class="warning">
                        <strong>⏰ 有效期：</strong>该验证码将在 <strong>{{ expire_minutes }} 分钟</strong> 后过期，请尽快使用。<br>
                        <strong>🔒 安全提示：</strong>请勿将验证码告知他人，工作人员不会向您索要验证码。
                    </div>
                    
                    <p class="info">如果这不是您本人的操作，请忽略此邮件或联系管理员。</p>
                </div>
                <div class="footer">
                    <p>此邮件由 ERP系统自动发送，请勿回复</p>
                    <p>发送时间：{{ send_time }}</p>
                </div>
            </div>
        </body>
        </html>
        '''
        
        html_content = render_template_string(
            html_template,
            user=user,
            code=code,
            purpose_text=purpose_text,
            expire_minutes=expire_minutes,
            send_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        
        subject = f'ERP系统 - {purpose_text} - 验证码: {code}'
        
        return EmailService.send_email(user.email, subject, html_content)
    
    @staticmethod
    def verify_code(user_id: int, code: str, purpose: str = 'login') -> tuple:
        """
        验证验证码
        
        Args:
            user_id: 用户ID
            code: 用户输入的验证码
            purpose: 用途
            
        Returns:
            (success, error_message)
        """
        # 查找验证码记录
        record = VerificationCode.query.filter_by(
            user_id=user_id,
            code=code,
            purpose=purpose
        ).order_by(VerificationCode.created_at.desc()).first()
        
        if not record:
            return False, '验证码错误'
        
        if record.is_used:
            return False, '验证码已使用，请重新获取'
        
        if record.is_expired:
            return False, '验证码已过期，请重新获取'
        
        # 标记为已使用
        record.mark_as_used()
        db.session.commit()
        
        return True, None
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """
        验证邮箱格式
        
        Args:
            email: 邮箱地址
            
        Returns:
            是否有效
        """
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def generate_device_fingerprint(user_agent: str, ip_address: str) -> str:
        """
        生成设备指纹
        
        Args:
            user_agent: User-Agent字符串
            ip_address: IP地址
            
        Returns:
            设备指纹（SHA256哈希的前16位）
        """
        import hashlib
        fingerprint_str = f"{user_agent}:{ip_address}"
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:32]
    
    @staticmethod
    def is_trusted_device(user_id: int, device_fingerprint: str) -> bool:
        """
        检查是否为受信任设备
        
        Args:
            user_id: 用户ID
            device_fingerprint: 设备指纹
            
        Returns:
            是否受信任
        """
        device = TrustedDevice.query.filter_by(
            user_id=user_id,
            device_fingerprint=device_fingerprint
        ).first()
        
        if not device:
            return False
        
        if device.is_expired:
            # 删除过期记录
            db.session.delete(device)
            db.session.commit()
            return False
        
        # 更新最后使用时间
        device.update_last_used()
        db.session.commit()
        
        return True
    
    @staticmethod
    def add_trusted_device(user_id: int, device_fingerprint: str,
                           device_name: str = None, ip_address: str = None) -> TrustedDevice:
        """
        添加受信任设备
        
        Args:
            user_id: 用户ID
            device_fingerprint: 设备指纹
            device_name: 设备名称
            ip_address: IP地址
            
        Returns:
            TrustedDevice对象
        """
        # 检查是否已存在
        existing = TrustedDevice.query.filter_by(
            user_id=user_id,
            device_fingerprint=device_fingerprint
        ).first()
        
        trusted_days = current_app.config.get('TRUSTED_DEVICE_DAYS', 30)
        expires_at = datetime.now() + timedelta(days=trusted_days)
        
        if existing:
            existing.expires_at = expires_at
            existing.last_used_at = datetime.now()
            db.session.commit()
            return existing
        
        # 创建新记录
        device = TrustedDevice(
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            device_name=device_name,
            ip_address=ip_address,
            expires_at=expires_at
        )
        db.session.add(device)
        db.session.commit()
        
        return device
    
    @staticmethod
    def get_user_trusted_devices(user_id: int) -> list:
        """
        获取用户的受信任设备列表
        
        Args:
            user_id: 用户ID
            
        Returns:
            设备列表
        """
        devices = TrustedDevice.query.filter_by(user_id=user_id).all()
        
        # 清理过期设备
        result = []
        for device in devices:
            if device.is_expired:
                db.session.delete(device)
            else:
                result.append(device)
        
        db.session.commit()
        return result
    
    @staticmethod
    def remove_trusted_device(device_id: int, user_id: int) -> bool:
        """
        移除受信任设备
        
        Args:
            device_id: 设备ID
            user_id: 用户ID（用于权限验证）
            
        Returns:
            是否成功
        """
        device = TrustedDevice.query.filter_by(id=device_id, user_id=user_id).first()
        if device:
            db.session.delete(device)
            db.session.commit()
            return True
        return False
