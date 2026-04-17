"""
閭欢鏈嶅姟绫?- 澶勭悊閭欢鍙戦€?"""
import smtplib
import random
import re
from datetime import datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from flask import current_app, render_template_string
from app import db
from app.models import User, VerificationCode, TrustedDevice, SystemSetting


class EmailService:
    """閭欢鏈嶅姟"""

    @staticmethod
    def _mask_email(email: str) -> str:
        """Mask email for logs."""
        if not email or '@' not in email:
            return email or ''
        local, domain = email.split('@', 1)
        if len(local) <= 2:
            masked_local = f'{local[:1]}*'
        else:
            masked_local = f'{local[:2]}***{local[-1:]}'
        return f'{masked_local}@{domain}'

    @staticmethod
    def _resolve_mail_config() -> dict:
        """Resolve mail config from app config, fallback to DB system settings."""
        mail_server = current_app.config.get('MAIL_SERVER')
        mail_port = current_app.config.get('MAIL_PORT', 465)
        mail_use_ssl = current_app.config.get('MAIL_USE_SSL', True)
        mail_username = current_app.config.get('MAIL_USERNAME')
        mail_password = current_app.config.get('MAIL_PASSWORD')
        mail_sender = current_app.config.get('MAIL_DEFAULT_SENDER')

        # Fallback to DB settings when env/config is missing.
        if not all([mail_server, mail_username, mail_password]):
            db_cfg = SystemSetting.get_email_config()
            mail_server = mail_server or db_cfg.get('server')
            mail_port = mail_port or db_cfg.get('port', 465)
            mail_use_ssl = db_cfg.get('use_ssl') if db_cfg.get('use_ssl') is not None else mail_use_ssl
            mail_username = mail_username or db_cfg.get('username')
            mail_password = mail_password or db_cfg.get('password')
            sender_missing = False
            if isinstance(mail_sender, tuple):
                sender_missing = len(mail_sender) < 2 or not mail_sender[1]
            else:
                sender_missing = not mail_sender

            if sender_missing:
                sender_name = db_cfg.get('sender_name') or 'ERP绯荤粺'
                sender_email = mail_username or ''
                mail_sender = (sender_name, sender_email)

        if isinstance(mail_use_ssl, str):
            mail_use_ssl = mail_use_ssl.lower() == 'true'

        return {
            'server': mail_server,
            'port': int(mail_port or 465),
            'use_ssl': bool(mail_use_ssl),
            'username': mail_username,
            'password': mail_password,
            'sender': mail_sender
        }
    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        html_content: str,
        trace_id: str = None,
        context: str = None
    ) -> tuple:
        """
        发送邮件。

        Returns:
            (success, error_message)
        """
        trace = trace_id or 'n/a'
        context_text = context or 'generic'

        try:
            cfg = EmailService._resolve_mail_config()
            mail_server = cfg['server']
            mail_port = cfg['port']
            mail_use_ssl = cfg['use_ssl']
            mail_username = cfg['username']
            mail_password = cfg['password']
            mail_sender = cfg['sender'] or mail_username

            if not all([mail_server, mail_username, mail_password]):
                current_app.logger.error(
                    '[MAIL][%s] missing config context=%s to=%s',
                    trace,
                    context_text,
                    EmailService._mask_email(to_email)
                )
                return False, '邮件服务未配置，请联系管理员'

            if isinstance(mail_sender, tuple):
                sender_name, sender_email = mail_sender
            else:
                sender_name, sender_email = 'ERP系统', mail_sender

            if not sender_email:
                sender_email = mail_username or ''

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            # RFC-compliant From header: encode display name and build address safely.
            encoded_sender = str(Header(str(sender_name or 'ERP系统'), 'utf-8'))
            msg['From'] = formataddr((encoded_sender, sender_email))
            msg['To'] = to_email
            if trace_id:
                msg['X-Trace-ID'] = trace_id
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))

            if mail_use_ssl:
                server = smtplib.SMTP_SSL(mail_server, mail_port)
            else:
                server = smtplib.SMTP(mail_server, mail_port)
                server.starttls()

            server.login(mail_username, mail_password)
            refused = server.sendmail(sender_email, to_email, msg.as_string())
            server.quit()

            if refused:
                current_app.logger.error(
                    '[MAIL][%s] sendmail refused recipients context=%s to=%s refused=%s',
                    trace,
                    context_text,
                    EmailService._mask_email(to_email),
                    refused
                )
                return False, f'收件人被拒绝: {refused}'

            current_app.logger.info(
                '[MAIL][%s] accepted by SMTP context=%s server=%s:%s ssl=%s from=%s to=%s',
                trace,
                context_text,
                mail_server,
                mail_port,
                mail_use_ssl,
                sender_email,
                EmailService._mask_email(to_email)
            )
            return True, None

        except Exception as e:
            current_app.logger.error(
                '[MAIL][%s] send failed context=%s to=%s err=%s',
                trace,
                context_text,
                EmailService._mask_email(to_email),
                str(e)
            )
            return False, f'邮件发送失败: {str(e)}'
    @staticmethod
    def generate_verify_code(length: int = 4) -> str:
        """
        鐢熸垚鏁板瓧楠岃瘉鐮?        
        Args:
            length: 楠岃瘉鐮侀暱搴?            
        Returns:
            鏁板瓧楠岃瘉鐮佸瓧绗︿覆
        """
        return ''.join([str(random.randint(0, 9)) for _ in range(length)])
    @staticmethod
    def create_verification_code(user: User, purpose: str = 'login',
                                  device_fingerprint: str = None,
                                  ip_address: str = None,
                                  trace_id: str = None) -> tuple:
        """创建新的验证码并写库。"""
        VerificationCode.query.filter_by(
            user_id=user.id,
            purpose=purpose
        ).delete()

        code_length = current_app.config.get('VERIFY_CODE_LENGTH', 4)
        code = EmailService.generate_verify_code(code_length)

        expire_minutes = current_app.config.get('VERIFY_CODE_EXPIRE_MINUTES', 15)
        expires_at = datetime.now() + timedelta(minutes=expire_minutes)

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

        current_app.logger.info(
            '[2FA][%s] code created user_id=%s username=%s purpose=%s ip=%s fp=%s code_id=%s expires_at=%s',
            trace_id or 'n/a',
            user.id,
            user.username,
            purpose,
            ip_address,
            (device_fingerprint or '')[:12],
            verify_code.id,
            expires_at
        )

        return code, None
    @staticmethod
    def send_verify_code_email(
        user: User,
        code: str,
        purpose: str = 'login',
        trace_id: str = None
    ) -> tuple:
        """发送验证码邮件。"""
        if not user.email:
            return False, '用户未绑定邮箱'

        if not EmailService.validate_email(user.email):
            return False, '用户邮箱格式不正确'

        purpose_text = {
            'login': '登录验证',
            'reset_password': '密码重置',
            'register': '注册验证'
        }.get(purpose, '安全验证')

        expire_minutes = current_app.config.get('VERIFY_CODE_EXPIRE_MINUTES', 15)

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
                    <h1>📨 ERP系统 - {{ purpose_text }}</h1>
                </div>
                <div class="content">
                    <p class="info">您好，<strong>{{ user.real_name or user.username }}</strong>：</p>
                    <p class="info">您正在进行 <strong>{{ purpose_text }}</strong> 操作，请使用以下验证码完成验证：</p>

                    <div class="code-box">
                        <div class="code">{{ code }}</div>
                    </div>

                    <div class="warning">
                        <strong>有效期：</strong>该验证码将在 <strong>{{ expire_minutes }} 分钟</strong> 后过期，请尽快使用。<br>
                        <strong>安全提示：</strong>请勿将验证码告知他人，工作人员不会向您索要验证码。
                    </div>

                    <p class="info">如果这不是您本人的操作，请忽略此邮件或联系管理员。</p>
                </div>
                <div class="footer">
                    <p>此邮件由 ERP系统 自动发送，请勿回复</p>
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

        subject = f'ERP系统 - {purpose_text} - 验证码 {code}'

        current_app.logger.info(
            '[2FA][%s] sending verify mail user_id=%s username=%s purpose=%s to=%s',
            trace_id or 'n/a',
            user.id,
            user.username,
            purpose,
            EmailService._mask_email(user.email)
        )

        return EmailService.send_email(
            user.email,
            subject,
            html_content,
            trace_id=trace_id,
            context=f'verify_code:{purpose}'
        )
    @staticmethod
    def verify_code(user_id: int, code: str, purpose: str = 'login') -> tuple:
        """验证验证码。"""
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

        record.mark_as_used()
        db.session.commit()
        return True, None
    @staticmethod
    def validate_email(email: str) -> bool:
        """
        楠岃瘉閭鏍煎紡
        
        Args:
            email: 閭鍦板潃
            
        Returns:
            鏄惁鏈夋晥
        """
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def generate_device_fingerprint(user_agent: str, ip_address: str) -> str:
        """
        鐢熸垚璁惧鎸囩汗
        
        Args:
            user_agent: User-Agent瀛楃涓?            ip_address: IP鍦板潃
            
        Returns:
            璁惧鎸囩汗锛圫HA256鍝堝笇鐨勫墠16浣嶏級
        """
        import hashlib
        fingerprint_str = f"{user_agent}:{ip_address}"
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:32]
    @staticmethod
    def is_trusted_device(user_id: int, device_fingerprint: str) -> bool:
        """检查设备是否为受信任设备。"""
        device = TrustedDevice.query.filter_by(
            user_id=user_id,
            device_fingerprint=device_fingerprint
        ).first()

        if not device:
            return False

        if device.is_expired:
            db.session.delete(device)
            db.session.commit()
            return False

        device.update_last_used()
        db.session.commit()
        return True
    @staticmethod
    def add_trusted_device(user_id: int, device_fingerprint: str,
                           device_name: str = None, ip_address: str = None) -> TrustedDevice:
        """添加受信任设备。"""
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
        鑾峰彇鐢ㄦ埛鐨勫彈淇′换璁惧鍒楄〃
        
        Args:
            user_id: 鐢ㄦ埛ID
            
        Returns:
            璁惧鍒楄〃
        """
        devices = TrustedDevice.query.filter_by(user_id=user_id).all()
        
        # 娓呯悊杩囨湡璁惧
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
        绉婚櫎鍙椾俊浠昏澶?        
        Args:
            device_id: 璁惧ID
            user_id: 鐢ㄦ埛ID锛堢敤浜庢潈闄愰獙璇侊級
            
        Returns:
            鏄惁鎴愬姛
        """
        device = TrustedDevice.query.filter_by(id=device_id, user_id=user_id).first()
        if device:
            db.session.delete(device)
            db.session.commit()
            return True
        return False


