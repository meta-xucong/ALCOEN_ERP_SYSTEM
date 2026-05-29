"""
系统设置路由
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from app.models import SystemSetting
from app.services.email_service import EmailService
from app.utils.decorators import login_required
from app import db

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


def _can_manage_email_settings() -> bool:
    """检查当前用户是否可管理验证码邮箱配置。"""
    return g.current_user.is_superadmin or g.current_user.has_permission('user_manage')


def _parse_smtp_port(value, default: int = 465) -> int:
    """安全解析 SMTP 端口，避免 undefined/空值导致 int 转换异常。"""
    if value is None:
        return default
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


@settings_bp.route('/')
@login_required
def index():
    """系统设置首页"""
    if not _can_manage_email_settings():
        flash('需要系统管理权限', 'error')
        return redirect(url_for('main.index'))
    
    return redirect(url_for('settings.email'))


@settings_bp.route('/email', methods=['GET', 'POST'])
@login_required
def email():
    """邮件服务器设置"""
    if not _can_manage_email_settings():
        flash('需要系统管理权限', 'error')
        return redirect(url_for('main.index'))
    
    # 获取当前配置
    config = SystemSetting.get_email_config()
    
    # 如果没有数据库配置，尝试从环境变量获取
    if not config['username']:
        import os
        config = {
            'server': os.environ.get('MAIL_SERVER', 'smtp.exmail.qq.com'),
            'port': _parse_smtp_port(os.environ.get('MAIL_PORT', '465')),
            'use_ssl': os.environ.get('MAIL_USE_SSL', 'true').lower() == 'true',
            'username': os.environ.get('MAIL_USERNAME', ''),
            'password': os.environ.get('MAIL_PASSWORD', ''),
            'sender_name': os.environ.get('MAIL_SENDER_NAME', 'ERP系统'),
        }
    
    if request.method == 'POST':
        action = request.form.get('action', 'save')
        
        if action == 'test':
            # 测试配置
            test_email = request.form.get('test_email', '').strip()
            if not test_email:
                flash('请输入测试邮箱地址', 'warning')
                return render_template('settings/email.html', config=config)
            
            # 使用当前表单数据测试
            test_config = {
                'server': request.form.get('smtp_server', 'smtp.exmail.qq.com'),
                'port': _parse_smtp_port(request.form.get('smtp_port', 465)),
                'use_ssl': request.form.get('smtp_use_ssl') == 'on',
                'username': request.form.get('smtp_username', ''),
                'password': request.form.get('smtp_password', ''),
                'sender_name': request.form.get('smtp_sender_name', 'ERP系统'),
            }
            
            # 临时使用测试配置发送
            code = EmailService.generate_verify_code(4)
            
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                from email.header import Header
                
                msg = MIMEMultipart('alternative')
                msg['Subject'] = Header('ERP系统 - 配置测试', 'utf-8')
                encoded_sender = Header(test_config['sender_name'], 'utf-8').encode()
                msg['From'] = f'{encoded_sender} <{test_config["username"]}>'
                msg['To'] = test_email
                
                html = f"""<html><body style="font-family:Arial;padding:20px;">
                <h2 style="color:#1e3a5f;">✅ 测试成功!</h2>
                <p>您的ERP系统邮件配置正确。</p>
                <p>验证码: <strong>{code}</strong></p>
                <p>配置信息:</p>
                <ul>
                    <li>服务器: {test_config['server']}:{test_config['port']}</li>
                    <li>账号: {test_config['username']}</li>
                </ul>
                </body></html>"""
                
                msg.attach(MIMEText(html.encode('utf-8'), 'html', 'utf-8'))
                
                if test_config['use_ssl']:
                    server = smtplib.SMTP_SSL(test_config['server'], test_config['port'], timeout=30)
                else:
                    server = smtplib.SMTP(test_config['server'], test_config['port'], timeout=30)
                    server.starttls()
                
                server.login(test_config['username'], test_config['password'])
                server.sendmail(test_config['username'], test_email, msg.as_string())
                server.quit()
                
                flash(f'✅ 测试邮件已发送至 {test_email}，请查收', 'success')
                
            except Exception as e:
                flash(f'❌ 测试失败: {str(e)}', 'error')
            
            # 返回表单数据
            config = test_config
            return render_template('settings/email.html', config=config)
        
        else:
            # 保存配置
            new_config = {
                'server': request.form.get('smtp_server', 'smtp.exmail.qq.com'),
                'port': _parse_smtp_port(request.form.get('smtp_port', 465)),
                'use_ssl': request.form.get('smtp_use_ssl') == 'on',
                'username': request.form.get('smtp_username', ''),
                'password': request.form.get('smtp_password', ''),
                'sender_name': request.form.get('smtp_sender_name', 'ERP系统'),
            }
            
            if not new_config['username']:
                flash('邮箱账号不能为空', 'error')
                return render_template('settings/email.html', config=config)
            
            if not new_config['password']:
                flash('邮箱密码不能为空', 'error')
                return render_template('settings/email.html', config=config)
            
            # 保存到数据库
            SystemSetting.set_email_config(new_config, g.current_user.id)
            
            flash('✅ 系统邮件配置已保存', 'success')
            config = new_config
    
    return render_template('settings/email.html', config=config)


@settings_bp.route('/clear', methods=['POST'])
@login_required
def clear_settings():
    """清除系统设置，恢复使用环境变量"""
    if not _can_manage_email_settings():
        flash('需要系统管理权限', 'error')
        return redirect(url_for('main.index'))
    
    # 删除所有邮件相关设置
    keys = ['mail_server', 'mail_port', 'mail_use_ssl', 'mail_username', 
            'mail_password', 'mail_sender_name']
    for key in keys:
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            db.session.delete(setting)
    db.session.commit()
    
    flash('已恢复使用环境变量配置', 'success')
    return redirect(url_for('settings.email'))
