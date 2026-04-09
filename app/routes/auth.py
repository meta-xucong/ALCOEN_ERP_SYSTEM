"""
认证路由 - 登录/注册/登出
"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.models import Role, User, Department, VerificationCode
from app.utils.decorators import login_required

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _get_client_ip() -> str:
    """Get real client IP behind reverse proxy."""
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')
    if x_forwarded_for:
        # XFF format: client, proxy1, proxy2...
        return x_forwarded_for.split(',')[0].strip()

    x_real_ip = request.headers.get('X-Real-IP', '').strip()
    if x_real_ip:
        return x_real_ip

    return request.remote_addr or ''


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面 - 支持两步验证"""
    # 如果已登录，跳转到首页
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    
    # 获取背景设置（优先使用用户设置，否则使用默认值）
    bg_type = 'video'  # 默认视频背景
    bg_image = 'bg-main.jpg'
    
    # 检查是否处于验证码验证阶段
    pending_verify_user_id = session.get('pending_verify_user_id')
    if pending_verify_user_id:
        return redirect(url_for('auth.verify_code'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        remember = request.form.get('remember') == 'on'
        
        if not username or not password:
            flash('请输入用户名和密码', 'warning')
            return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image)
        
        # 获取设备信息
        user_agent = request.headers.get('User-Agent', '')
        ip_address = _get_client_ip()
        
        # 验证登录（支持两步验证）
        result = AuthService.authenticate(
            username=username,
            password=password,
            user_agent=user_agent,
            ip_address=ip_address,
            require_2fa=True
        )
        
        if not result.success:
            flash(result.message, 'error')
            return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image)
        
        user = result.user
        
        # 检查是否需要验证码验证（两步验证）
        if result.require_verify:
            # 生成并发送验证码
            code, error = EmailService.create_verification_code(
                user=user,
                purpose='login',
                device_fingerprint=result.device_fingerprint,
                ip_address=ip_address
            )
            
            if error:
                flash(f'验证码生成失败: {error}', 'error')
                return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image)
            
            # 发送验证码邮件
            success, error = EmailService.send_verify_code_email(user, code, 'login')
            
            if not success:
                flash(f'验证码发送失败: {error}', 'error')
                return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image)
            
            # 保存验证状态到session
            session['pending_verify_user_id'] = user.id
            session['pending_verify_fingerprint'] = result.device_fingerprint
            session['pending_verify_remember'] = remember
            session['pending_verify_purpose'] = 'login'
            
            flash('验证码已发送至您的邮箱，请查收', 'success')
            return redirect(url_for('auth.verify_code'))
        
        # 直接登录（受信任设备或无邮箱）
        next_url = request.args.get('next')
        return _do_login(user, remember, ip_address, next_url)
    
    return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image)


@auth_bp.route('/verify-code', methods=['GET', 'POST'])
def verify_code():
    """验证码验证页面 - 两步验证"""
    # 检查是否有待验证的登录
    pending_user_id = session.get('pending_verify_user_id')
    if not pending_user_id:
        return redirect(url_for('auth.login'))
    
    user = User.query.get(pending_user_id)
    if not user:
        session.pop('pending_verify_user_id', None)
        flash('验证会话已过期，请重新登录', 'warning')
        return redirect(url_for('auth.login'))
    
    # 获取背景设置
    bg_type = 'video'
    bg_image = 'bg-main.jpg'
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        trust_device = request.form.get('trust_device') == 'on'
        
        if not code:
            flash('请输入验证码', 'warning')
            return render_template('auth/verify_code.html', user=user, bg_type=bg_type, bg_image=bg_image)
        
        # 验证验证码
        purpose = session.get('pending_verify_purpose', 'login')
        success, error = EmailService.verify_code(user.id, code, purpose)
        
        if not success:
            flash(error, 'error')
            return render_template('auth/verify_code.html', user=user, bg_type=bg_type, bg_image=bg_image)
        
        # 验证码正确，完成登录
        remember = session.get('pending_verify_remember', False)
        fingerprint = session.get('pending_verify_fingerprint')
        
        # 如果用户选择信任此设备，添加到信任列表
        if trust_device and fingerprint:
            device_name = _get_device_name(request.headers.get('User-Agent', ''))
            EmailService.add_trusted_device(
                user_id=user.id,
                device_fingerprint=fingerprint,
                device_name=device_name,
                ip_address=_get_client_ip()
            )
        
        # 清除验证状态
        session.pop('pending_verify_user_id', None)
        session.pop('pending_verify_fingerprint', None)
        session.pop('pending_verify_remember', None)
        session.pop('pending_verify_purpose', None)
        
        # 执行登录
        return _do_login(user, remember, _get_client_ip())
    
    return render_template('auth/verify_code.html', user=user, bg_type=bg_type, bg_image=bg_image)


@auth_bp.route('/resend-code', methods=['POST'])
def resend_code():
    """重新发送验证码"""
    pending_user_id = session.get('pending_verify_user_id')
    if not pending_user_id:
        return jsonify({'success': False, 'message': '验证会话已过期'})
    
    user = User.query.get(pending_user_id)
    if not user or not user.email:
        return jsonify({'success': False, 'message': '用户信息无效'})
    
    # 检查发送频率限制（60秒内只能发送一次）
    last_sent = VerificationCode.query.filter_by(
        user_id=user.id,
        purpose='login'
    ).order_by(VerificationCode.created_at.desc()).first()
    
    if last_sent:
        seconds_since_last = (datetime.now() - last_sent.created_at).total_seconds()
        if seconds_since_last < 60:
            wait_seconds = int(60 - seconds_since_last)
            return jsonify({'success': False, 'message': f'请等待 {wait_seconds} 秒后重试'})
    
    # 生成并发送新验证码
    fingerprint = session.get('pending_verify_fingerprint')
    ip_address = _get_client_ip()
    
    code, error = EmailService.create_verification_code(
        user=user,
        purpose='login',
        device_fingerprint=fingerprint,
        ip_address=ip_address
    )
    
    if error:
        return jsonify({'success': False, 'message': f'验证码生成失败: {error}'})
    
    success, error = EmailService.send_verify_code_email(user, code, 'login')
    
    if not success:
        return jsonify({'success': False, 'message': f'验证码发送失败: {error}'})
    
    return jsonify({'success': True, 'message': '验证码已重新发送'})


def _get_device_name(user_agent: str) -> str:
    """从User-Agent获取设备名称"""
    import re
    
    # 简单解析
    if 'Windows' in user_agent:
        os_name = 'Windows'
    elif 'Mac OS' in user_agent or 'Macintosh' in user_agent:
        os_name = 'Mac'
    elif 'Linux' in user_agent:
        os_name = 'Linux'
    elif 'Android' in user_agent:
        os_name = 'Android'
    elif 'iPhone' in user_agent or 'iPad' in user_agent:
        os_name = 'iOS'
    else:
        os_name = 'Unknown'
    
    if 'Chrome' in user_agent:
        browser = 'Chrome'
    elif 'Firefox' in user_agent:
        browser = 'Firefox'
    elif 'Safari' in user_agent:
        browser = 'Safari'
    elif 'Edge' in user_agent:
        browser = 'Edge'
    else:
        browser = 'Browser'
    
    return f"{browser} on {os_name}"


def _do_login(user, remember: bool, ip_address: str, next_url: str = None):
    """执行登录操作"""
    # 设置session
    session['user_id'] = user.id
    session['username'] = user.username
    session.permanent = remember
    
    # 更新登录信息
    AuthService.update_login_info(user, ip_address)
    
    # 检查是否需要修改密码
    if user.require_password_change:
        flash('登录成功！请修改初始密码', 'success')
        return redirect(url_for('auth.change_password'))
    
    flash('登录成功！', 'success')
    
    # 跳转到next或首页
    if next_url:
        return redirect(next_url)
    return redirect(url_for('main.index'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """注册页面"""
    # 如果已登录，跳转到首页
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    
    # 获取部门和角色列表 - 从部门管理模块获取
    departments = Department.query.order_by(Department.name).all()
    roles = Role.query.filter(Role.code != 'superadmin').order_by(Role.level.desc()).all()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        real_name = request.form.get('real_name', '').strip()
        role_id = request.form.get('role_id', '').strip()
        department_id = request.form.get('department_id', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip() or None
        
        # 验证
        if not username:
            flash('请输入用户名', 'warning')
            return render_template('auth/register.html', departments=departments, roles=roles)
        
        if not real_name:
            flash('请输入真实姓名', 'warning')
            return render_template('auth/register.html', departments=departments, roles=roles)
        
        if not role_id:
            flash('请选择角色', 'warning')
            return render_template('auth/register.html', departments=departments, roles=roles)
        
        # 获取角色代码
        role = Role.query.get(role_id)
        if not role:
            flash('角色不存在', 'error')
            return render_template('auth/register.html', departments=departments, roles=roles)
        
        # [v1.4] 处理部门选择
        # 总经理和物流经理可以选择"全部部门"（传'all'或空都表示全部部门）
        if role.code in ['general_manager', 'logistics_manager']:
            # 总经理、物流经理：部门可选，'all'或空值都表示全部部门
            if department_id == 'all':
                final_department_id = None
            elif department_id and department_id.isdigit():
                final_department_id = int(department_id)
            else:
                final_department_id = None  # 默认为全部部门
        else:
            # 其他角色：必须选择具体部门
            if not department_id or not department_id.isdigit():
                flash('请选择所属部门', 'warning')
                return render_template('auth/register.html', departments=departments, roles=roles)
            final_department_id = int(department_id)
        
        # 创建用户
        user, error = AuthService.register_user(
            username=username,
            real_name=real_name,
            role_code=role.code,
            department_id=final_department_id,
            email=email,
            phone=phone
        )
        
        if error:
            flash(error, 'error')
            return render_template('auth/register.html', departments=departments, roles=roles)
        
        flash('注册成功！请等待管理员审核', 'success')
        return redirect(url_for('auth.pending'))
    
    return render_template('auth/register.html', departments=departments, roles=roles)


@auth_bp.route('/pending')
def pending():
    """注册等待审核页面"""
    return render_template('auth/pending.html')


@auth_bp.route('/logout')
def logout():
    """登出"""
    session.clear()
    flash('已成功退出登录', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """修改密码（首次登录强制修改）"""
    from flask import g
    user = g.current_user
    
    # 如果不是强制修改密码，显示正常修改页面
    is_forced = user.require_password_change
    
    if request.method == 'POST':
        if is_forced:
            # 强制修改密码
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            if not new_password:
                flash('请输入新密码', 'warning')
                return render_template('auth/change_password.html', is_forced=is_forced)
            
            if new_password != confirm_password:
                flash('两次输入的密码不一致', 'error')
                return render_template('auth/change_password.html', is_forced=is_forced)
            
            success, message = AuthService.force_change_password(user, new_password)
            if success:
                flash(message, 'success')
                session.clear()  # 清除session，要求重新登录
                return redirect(url_for('auth.login'))
            else:
                flash(message, 'error')
                return render_template('auth/change_password.html', is_forced=is_forced)
        else:
            # 正常修改密码
            old_password = request.form.get('old_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            if not old_password or not new_password:
                flash('请输入完整信息', 'warning')
                return render_template('auth/change_password.html', is_forced=is_forced)
            
            if new_password != confirm_password:
                flash('两次输入的密码不一致', 'error')
                return render_template('auth/change_password.html', is_forced=is_forced)
            
            success, message = AuthService.change_password(user, old_password, new_password)
            if success:
                flash(message, 'success')
                return redirect(url_for('main.index'))
            else:
                flash(message, 'error')
                return render_template('auth/change_password.html', is_forced=is_forced)
    
    return render_template('auth/change_password.html', is_forced=is_forced)
