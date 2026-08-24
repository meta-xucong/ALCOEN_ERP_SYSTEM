"""
璁よ瘉璺敱 - 鐧诲綍/娉ㄥ唽/鐧诲嚭
"""
from datetime import datetime
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, jsonify, g
from app import db
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.models import (
    AI_CATS_IDENTITY_DEFINITIONS,
    AI_CATS_LEGACY_ROLE_IDENTITY_MAP,
    AI_CATS_TECHNICAL_ROLE_CODE,
    AICatsUserIdentity,
    Role,
    User,
    Department,
    VerificationCode,
    QCUserBinding,
    QC_ROLE_CODES,
)
from app.services.ai_cats_access_service import AICatsAccessService
from app.utils.decorators import login_required

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _safe_local_next(next_url: str | None) -> str | None:
    """Return a local redirect path and reject absolute or scheme-relative URLs."""
    if not next_url:
        return None
    next_url = next_url.strip()
    if not next_url.startswith('/') or next_url.startswith('//'):
        return None
    return next_url


def _get_client_ip() -> str:
    """Description."""
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()

    x_real_ip = request.headers.get('X-Real-IP', '').strip()
    if x_real_ip:
        return x_real_ip

    return request.remote_addr or ''


def _get_qc_roles():
    """Load QC role options, auto-creating the two system roles when missing."""
    return AuthService.ensure_qc_roles()


def _get_erp_roles():
    """Load ERP registration roles, excluding superadmin and QC-only roles."""
    return Role.query.filter(
        Role.code.notin_(('superadmin', AI_CATS_TECHNICAL_ROLE_CODE) + QC_ROLE_CODES)
    ).order_by(Role.level.desc()).all()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Description."""
    is_qc = request.args.get('sub') == 'qc'
    
    # 如果用户点击取消验证，清除 pending 状态
    if request.args.get('cancel'):
        session.pop('pending_verify_user_id', None)
        session.pop('pending_verify_fingerprint', None)
        session.pop('pending_verify_remember', None)
        session.pop('pending_verify_purpose', None)
        session.pop('pending_verify_subsystem', None)
    
    # 如果已登录，跳转到对应首页
    if 'user_id' in session:
        if session.get('subsystem') == 'qc':
            return redirect(url_for('qc.index'))
        return redirect(url_for('main.index'))
    
    bg_type = 'video'
    bg_image = 'bg-main.jpg'
    
    pending_verify_user_id = session.get('pending_verify_user_id')
    if pending_verify_user_id:
        return redirect(url_for('auth.verify_code'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        remember = request.form.get('remember') == 'on'
        
        if not username or not password:
            flash('请输入用户名和密码', 'warning')
            return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image, is_qc=is_qc)
        
        user_agent = request.headers.get('User-Agent', '')
        ip_address = _get_client_ip()
        
        result = AuthService.authenticate(
            username=username,
            password=password,
            user_agent=user_agent,
            ip_address=ip_address,
            require_2fa=True
        )
        
        if not result.success:
            flash(result.message, 'error')
            return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image, is_qc=is_qc)
        
        user = result.user
        if result.require_verify:
            trace_id = f'login-{user.id}-{uuid4().hex[:8]}'
            session['pending_verify_user_id'] = user.id
            session['pending_verify_fingerprint'] = result.device_fingerprint
            session['pending_verify_remember'] = remember
            session['pending_verify_purpose'] = 'login'
            if is_qc:
                session['pending_verify_subsystem'] = 'qc'

            current_app.logger.info(
                '[2FA][%s] verify required username=%s user_id=%s subsystem=%s ip=%s fp=%s',
                trace_id,
                user.username,
                user.id,
                'qc' if is_qc else 'erp',
                ip_address,
                (result.device_fingerprint or '')[:12]
            )

            recent_code = VerificationCode.query.filter(
                VerificationCode.user_id == user.id,
                VerificationCode.purpose == 'login',
                VerificationCode.used_at.is_(None),
                VerificationCode.expires_at > datetime.now()
            ).order_by(VerificationCode.created_at.desc()).first()

            if recent_code and (datetime.now() - recent_code.created_at).total_seconds() < 20:
                current_app.logger.info(
                    '[2FA][%s] deduplicated recent code username=%s user_id=%s code_id=%s',
                    trace_id,
                    user.username,
                    user.id,
                    recent_code.id
                )
                flash('验证码已发送，请直接查收并输入', 'info')
                return redirect(url_for('auth.verify_code'))

            code, error = EmailService.create_verification_code(
                user=user,
                purpose='login',
                device_fingerprint=result.device_fingerprint,
                ip_address=ip_address,
                trace_id=trace_id
            )

            if error:
                current_app.logger.error(
                    '[2FA][%s] code create failed username=%s user_id=%s err=%s',
                    trace_id,
                    user.username,
                    user.id,
                    error
                )
                flash(f'验证码生成失败: {error}', 'error')
                return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image, is_qc=is_qc)

            success, error = EmailService.send_verify_code_email(user, code, 'login', trace_id=trace_id)

            if not success:
                VerificationCode.query.filter(
                    VerificationCode.user_id == user.id,
                    VerificationCode.purpose == 'login',
                    VerificationCode.code == code,
                    VerificationCode.used_at.is_(None)
                ).delete()
                db.session.commit()
                current_app.logger.error(
                    '[2FA][%s] verify mail failed username=%s user_id=%s err=%s',
                    trace_id,
                    user.username,
                    user.id,
                    error
                )
                flash(f'验证码发送失败: {error}', 'error')
                return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image, is_qc=is_qc)

            current_app.logger.info(
                '[2FA][%s] verify mail sent username=%s user_id=%s to=%s',
                trace_id,
                user.username,
                user.id,
                EmailService._mask_email(user.email)
            )
            flash('验证码已发送至您的邮箱，请查收', 'success')
            return redirect(url_for('auth.verify_code'))
        next_url = request.args.get('next')
        subsystem = 'qc' if is_qc else ''
        return _do_login(user, remember, ip_address, next_url, subsystem)
    
    return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image, is_qc=is_qc)


@auth_bp.route('/login/qc')
def qc_login():
    """Description."""
    return redirect(url_for('auth.login', sub='qc'))


@auth_bp.route('/verify-code', methods=['GET', 'POST'])
def verify_code():
    """Description."""
    pending_user_id = session.get('pending_verify_user_id')
    if not pending_user_id:
        return redirect(url_for('auth.login'))
    
    user = User.query.get(pending_user_id)
    if not user:
        session.pop('pending_verify_user_id', None)
        flash('验证会话已过期，请重新登录', 'warning')
        return redirect(url_for('auth.login'))
    
    bg_type = 'video'
    bg_image = 'bg-main.jpg'
    
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        trust_device = request.form.get('trust_device') == 'on'
        
        if not code:
            flash('请输入验证码', 'warning')
            return render_template('auth/verify_code.html', user=user, bg_type=bg_type, bg_image=bg_image)
        
        purpose = session.get('pending_verify_purpose', 'login')
        success, error = EmailService.verify_code(user.id, code, purpose)
        
        if not success:
            flash(error, 'error')
            return render_template('auth/verify_code.html', user=user, bg_type=bg_type, bg_image=bg_image)
        
        remember = session.get('pending_verify_remember', False)
        fingerprint = session.get('pending_verify_fingerprint')
        subsystem = session.pop('pending_verify_subsystem', None)
        
        if trust_device and fingerprint:
            device_name = _get_device_name(request.headers.get('User-Agent', ''))
            EmailService.add_trusted_device(
                user_id=user.id,
                device_fingerprint=fingerprint,
                device_name=device_name,
                ip_address=_get_client_ip()
            )
        
        session.pop('pending_verify_user_id', None)
        session.pop('pending_verify_fingerprint', None)
        session.pop('pending_verify_remember', None)
        session.pop('pending_verify_purpose', None)
        
        return _do_login(user, remember, _get_client_ip(), subsystem=subsystem)
    
    return render_template('auth/verify_code.html', user=user, bg_type=bg_type, bg_image=bg_image)


@auth_bp.route('/resend-code', methods=['POST'])
def resend_code():
    """Description."""
    pending_user_id = session.get('pending_verify_user_id')
    if not pending_user_id:
        return jsonify({'success': False, 'message': '验证会话已过期'})
    
    user = User.query.get(pending_user_id)
    if not user or not user.email:
        return jsonify({'success': False, 'message': '鐢ㄦ埛淇℃伅鏃犳晥'})
    
    last_sent = VerificationCode.query.filter_by(
        user_id=user.id,
        purpose='login'
    ).order_by(VerificationCode.created_at.desc()).first()
    
    if last_sent:
        seconds_since_last = (datetime.now() - last_sent.created_at).total_seconds()
        if seconds_since_last < 60:
            wait_seconds = int(60 - seconds_since_last)
            return jsonify({'success': False, 'message': f'请等待 {wait_seconds} 秒后重试'})
    
    fingerprint = session.get('pending_verify_fingerprint')
    ip_address = _get_client_ip()
    trace_id = f'resend-{user.id}-{uuid4().hex[:8]}'

    code, error = EmailService.create_verification_code(
        user=user,
        purpose='login',
        device_fingerprint=fingerprint,
        ip_address=ip_address,
        trace_id=trace_id
    )

    if error:
        current_app.logger.error(
            '[2FA][%s] resend code create failed username=%s user_id=%s err=%s',
            trace_id,
            user.username,
            user.id,
            error
        )
        return jsonify({'success': False, 'message': f'验证码生成失败: {error}'})

    success, error = EmailService.send_verify_code_email(user, code, 'login', trace_id=trace_id)

    if not success:
        current_app.logger.error(
            '[2FA][%s] resend verify mail failed username=%s user_id=%s err=%s',
            trace_id,
            user.username,
            user.id,
            error
        )
        return jsonify({'success': False, 'message': f'验证码发送失败: {error}'})

    current_app.logger.info(
        '[2FA][%s] resend verify mail sent username=%s user_id=%s to=%s',
        trace_id,
        user.username,
        user.id,
        EmailService._mask_email(user.email)
    )
    return jsonify({'success': True, 'message': '验证码已重新发送'})


def _get_device_name(user_agent: str) -> str:
    """Description."""
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


def _do_login(user, remember: bool, ip_address: str, next_url: str = None, subsystem: str = None):
    """Description."""
    next_url = _safe_local_next(next_url)
    # QC-only 璐﹀彿涓嶈兘閫氳繃 ERP 鍏ュ彛鐧诲綍
    if subsystem != 'qc' and AICatsAccessService.is_ai_cats_only(user):
        session.clear()
        flash('该账号仅可用于 AI CATS 登录；如需使用 ERP，请联系管理员开通 ERP 账号。', 'warning')
        return redirect(url_for('auth.login'))

    session['user_id'] = user.id
    session['username'] = user.username
    session.permanent = remember
    
    AuthService.update_login_info(user, ip_address)
    
    if user.require_password_change:
        flash('登录成功！请修改初始密码', 'success')
        return redirect(url_for('auth.change_password'))
    
    flash('登录成功！', 'success')
    
    if subsystem == 'qc':
        if AICatsAccessService.can_enter(user):
            session['subsystem'] = 'qc'
            if next_url:
                return redirect(next_url)
            return redirect(url_for('qc.index'))

        identities = AICatsUserIdentity.query.filter_by(user_id=user.id).all()
        if not identities:
            session['pending_qc_user_id'] = user.id
            return redirect(url_for('auth.qc_role_apply'))
        flash('您的 AI CATS 身份尚未通过审核或账号已停用，请联系管理员', 'warning')
        session.clear()
        return redirect(url_for('auth.qc_login'))
    
    if next_url:
        return redirect(next_url)
    return redirect(url_for('main.index'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Description."""
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    
    departments = Department.query.order_by(Department.name).all()
    roles = _get_erp_roles()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        real_name = request.form.get('real_name', '').strip()
        role_id = request.form.get('role_id', '').strip()
        department_id = request.form.get('department_id', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip() or None
        
        if not username:
            flash('请输入用户名', 'warning')
            return render_template('auth/register.html', departments=departments, roles=roles)
        
        if not real_name:
            flash('请输入真实姓名', 'warning')
            return render_template('auth/register.html', departments=departments, roles=roles)
        
        if not role_id:
            flash('请选择角色', 'warning')
            return render_template('auth/register.html', departments=departments, roles=roles)
        
        role = Role.query.get(role_id)
        if not role or role.code in ('superadmin',) + QC_ROLE_CODES:
            flash('角色不存在', 'error')
            return render_template('auth/register.html', departments=departments, roles=roles)
        
        if role.code in AuthService.DEPARTMENT_OPTIONAL_ROLE_CODES:
            final_department_id = None
        else:
            if not department_id or not department_id.isdigit():
                flash('请选择所属部门', 'warning')
                return render_template('auth/register.html', departments=departments, roles=roles)
            final_department_id = int(department_id)
        
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


@auth_bp.route('/register/qc', methods=['GET', 'POST'])
def register_qc():
    """Register an AI CATS-only account with multiple requested identities."""
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            return redirect(url_for('auth.qc_login'))

        if AICatsAccessService.can_enter(user):
            return redirect(url_for('qc.index'))
        return redirect(url_for('auth.qc_role_apply'))

    roles = _get_qc_roles()
    identity_definitions = AICatsAccessService.identity_definitions()
    selected_identity_codes = request.form.getlist('identity_codes')
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        real_name = request.form.get('real_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip() or None

        # Compatibility for older clients that still submit one legacy role ID.
        legacy_role_code = None
        if not selected_identity_codes:
            role_id = request.form.get('role_id', '').strip()
            role = Role.query.get(role_id) if role_id.isdigit() else None
            if role and role.code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP:
                legacy_role_code = role.code
                selected_identity_codes = list(
                    AI_CATS_LEGACY_ROLE_IDENTITY_MAP[legacy_role_code]
                )
            elif role_id:
                flash('角色不存在或无效', 'warning')
                return render_template(
                    'auth/register_qc.html',
                    roles=roles,
                    identity_definitions=identity_definitions,
                    selected_identity_codes=selected_identity_codes,
                )
        
        if not username:
            flash('请输入用户名', 'warning')
            return render_template(
                'auth/register_qc.html',
                roles=roles,
                identity_definitions=identity_definitions,
                selected_identity_codes=selected_identity_codes,
            )
        
        if not real_name:
            flash('请输入真实姓名', 'warning')
            return render_template(
                'auth/register_qc.html',
                roles=roles,
                identity_definitions=identity_definitions,
                selected_identity_codes=selected_identity_codes,
            )

        try:
            selected_identity_codes = AICatsAccessService.normalize_identity_codes(
                selected_identity_codes
            )
        except ValueError as exc:
            flash(str(exc), 'warning')
            return render_template(
                'auth/register_qc.html',
                roles=roles,
                identity_definitions=identity_definitions,
                selected_identity_codes=selected_identity_codes,
            )
        
        user, error = AuthService.register_qc_user(
            username=username,
            real_name=real_name,
            role_code=legacy_role_code,
            identity_codes=selected_identity_codes,
            email=email,
            phone=phone
        )
        
        if error:
            flash(error, 'error')
            return render_template(
                'auth/register_qc.html',
                roles=roles,
                identity_definitions=identity_definitions,
                selected_identity_codes=selected_identity_codes,
            )
        
        flash('注册成功！请等待管理员审核', 'success')
        return redirect(url_for('auth.pending'))
    
    return render_template(
        'auth/register_qc.html',
        roles=roles,
        identity_definitions=identity_definitions,
        selected_identity_codes=selected_identity_codes,
    )


@auth_bp.route('/qc-role-apply', methods=['GET', 'POST'])
@login_required
def qc_role_apply():
    """Allow ERP users to incrementally request multiple AI CATS identities."""
    user = g.current_user

    if AICatsAccessService.is_manager(user):
        flash('您已拥有 AI CATS 全部权限', 'success')
        return redirect(url_for('qc.index'))

    identity_definitions = AICatsAccessService.identity_definitions()
    current_identities = AICatsUserIdentity.query.filter_by(user_id=user.id).order_by(
        AICatsUserIdentity.id.asc()
    ).all()
    unavailable_codes = {
        identity.identity_code
        for identity in current_identities
        if identity.status in {'active', 'pending'}
    }
    selected_identity_codes = request.form.getlist('identity_codes')

    if request.method == 'POST':
        try:
            selected_identity_codes = AICatsAccessService.normalize_identity_codes(
                selected_identity_codes
            )
            if any(code in unavailable_codes for code in selected_identity_codes):
                raise ValueError('所选身份中包含已经生效或正在审核的身份')
            AICatsAccessService.ensure_profile(user, 'shared', is_enabled=True)
            AICatsAccessService.request_identities(
                user,
                selected_identity_codes,
                source='erp_apply',
                status='pending',
            )
            db.session.commit()
            flash('AI CATS 身份申请已提交，请等待管理员审核', 'success')
            return redirect(url_for('auth.qc_role_apply'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'auth/qc_role_apply.html',
        identity_definitions=identity_definitions,
        current_identities=current_identities,
        unavailable_codes=unavailable_codes,
        selected_identity_codes=selected_identity_codes,
    )


@auth_bp.route('/pending')
def pending():
    """Description."""
    return render_template('auth/pending.html')


@auth_bp.route('/logout')
def logout():
    """Description."""
    session.clear()
    flash('已成功退出登录', 'success')
    return redirect(url_for('portal.portal'))


@auth_bp.route('/switch/erp')
@login_required
def switch_to_erp():
    """Switch current session to ERP subsystem."""
    user = g.current_user
    if AICatsAccessService.is_ai_cats_only(user):
        flash('当前账号仅可用于 AI CATS，不能切换到 ERP 系统', 'warning')
        return redirect(url_for('qc.index'))

    session['subsystem'] = 'erp'
    return redirect(url_for('main.index'))


@auth_bp.route('/switch/qc')
@login_required
def switch_to_qc():
    """Switch current session to QC subsystem."""
    user = g.current_user

    if not AICatsAccessService.can_enter(user):
        flash('您当前没有可用的 AI CATS 身份', 'warning')
        return redirect(url_for('main.index'))

    session['subsystem'] = 'qc'
    return redirect(url_for('qc.index'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Description."""
    user = g.current_user
    is_forced = user.require_password_change
    
    if request.method == 'POST':
        if is_forced:
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
                session.clear()
                return redirect(url_for('auth.login'))
            else:
                flash(message, 'error')
                return render_template('auth/change_password.html', is_forced=is_forced)
        else:
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
                # 根据当前子系统决定跳转
                if session.get('subsystem') == 'qc':
                    return redirect(url_for('qc.index'))
                return redirect(url_for('main.index'))
            else:
                flash(message, 'error')
                return render_template('auth/change_password.html', is_forced=is_forced)
    
    return render_template('auth/change_password.html', is_forced=is_forced)
