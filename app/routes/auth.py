"""
认证路由 - 登录/注册/登出
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.services.auth_service import AuthService
from app.services.contract_service import ContractService
from app.models import Role, User, Department
from app.utils.decorators import login_required

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    # 如果已登录，跳转到首页
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    
    # 获取背景设置（优先使用用户设置，否则使用默认值）
    bg_type = 'video'  # 默认视频背景
    bg_image = 'bg-main.jpg'
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        remember = request.form.get('remember') == 'on'
        
        if not username or not password:
            flash('请输入用户名和密码', 'warning')
            return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image)
        
        # 验证登录
        user, error = AuthService.authenticate(username, password)
        
        if error:
            flash(error, 'error')
            return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image)
        
        # 设置session
        session['user_id'] = user.id
        session['username'] = user.username
        session.permanent = remember  # 记住我
        
        # 更新登录信息
        AuthService.update_login_info(user, request.remote_addr)
        
        # 检查是否需要修改密码
        if user.require_password_change:
            return redirect(url_for('auth.change_password'))
        
        # 跳转到next或首页
        next_url = request.args.get('next')
        if next_url:
            return redirect(next_url)
        return redirect(url_for('main.index'))
    
    return render_template('auth/login.html', bg_type=bg_type, bg_image=bg_image)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """注册页面"""
    # 如果已登录，跳转到首页
    if 'user_id' in session:
        return redirect(url_for('main.index'))
    
    # 获取背景设置（与登录页一致）
    bg_type = 'video'  # 默认视频背景
    bg_image = 'bg-main.jpg'
    
    # 获取部门和角色列表 - 从部门管理模块获取
    departments = Department.query.order_by(Department.name).all()
    roles = Role.query.filter(Role.code != 'superadmin').order_by(Role.level.desc()).all()
    
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            real_name = request.form.get('real_name', '').strip()
            role_id = request.form.get('role_id', '').strip()
            department_id = request.form.get('department_id', '').strip()
            email = request.form.get('email', '').strip() or None
            phone = request.form.get('phone', '').strip() or None
            
            # 验证
            if not username:
                flash('请输入用户名', 'warning')
                return render_template('auth/register.html', departments=departments, roles=roles, bg_type=bg_type, bg_image=bg_image)
            
            if not real_name:
                flash('请输入真实姓名', 'warning')
                return render_template('auth/register.html', departments=departments, roles=roles, bg_type=bg_type, bg_image=bg_image)
            
            if not role_id:
                flash('请选择角色', 'warning')
                return render_template('auth/register.html', departments=departments, roles=roles, bg_type=bg_type, bg_image=bg_image)
            
            # 获取角色代码
            role = Role.query.get(role_id)
            if not role:
                flash('角色不存在', 'error')
                return render_template('auth/register.html', departments=departments, roles=roles, bg_type=bg_type, bg_image=bg_image)
            
            # [v1.4] 处理部门选择
            # 总经理、物流经理、总经理助理可以选择"全部部门"（传'all'或空都表示全部部门）
            if role.code in ['general_manager', 'logistics_manager', 'gm_assistant']:
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
                    return render_template('auth/register.html', departments=departments, roles=roles, bg_type=bg_type, bg_image=bg_image)
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
                return render_template('auth/register.html', departments=departments, roles=roles, bg_type=bg_type, bg_image=bg_image)
            
            flash('注册成功！请等待管理员审核', 'success')
            return redirect(url_for('auth.pending'))
            
        except Exception as e:
            import traceback
            print(f"[ERROR] 注册异常: {str(e)}")
            traceback.print_exc()
            flash(f'注册失败: {str(e)}', 'error')
            return render_template('auth/register.html', departments=departments, roles=roles, bg_type=bg_type, bg_image=bg_image)
    
    return render_template('auth/register.html', departments=departments, roles=roles, bg_type=bg_type, bg_image=bg_image)


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
