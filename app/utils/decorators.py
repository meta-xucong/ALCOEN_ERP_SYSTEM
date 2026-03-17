"""
认证与权限装饰器
"""
from functools import wraps
from flask import session, redirect, url_for, flash, request, g


def login_required(f):
    """要求用户必须登录"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        
        # 加载当前用户到 g
        from app.models import User
        g.current_user = User.query.get(session['user_id'])
        
        if not g.current_user:
            session.clear()
            return redirect(url_for('auth.login', next=request.url))
        
        # 检查账号是否激活
        if not g.current_user.is_active:
            flash('您的账号尚未通过审核，请联系管理员', 'warning')
            session.clear()
            return redirect(url_for('auth.login'))
        
        # 检查是否需要修改密码
        if g.current_user.require_password_change and request.endpoint != 'auth.change_password':
            return redirect(url_for('auth.change_password'))
        
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission_code):
    """要求用户拥有指定权限"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login', next=request.url))
            
            from app.models import User
            user = User.query.get(session['user_id'])
            
            if not user or not user.has_permission(permission_code):
                flash('您没有权限执行此操作', 'error')
                return redirect(url_for('main.index'))
            
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """要求用户必须是超级管理员"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        
        from app.models import User
        user = User.query.get(session['user_id'])
        
        if not user or not user.is_superadmin:
            flash('需要超级管理员权限', 'error')
            return redirect(url_for('main.index'))
        
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def user_manage_required(f):
    """要求用户必须有用户管理权限"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        
        from app.models import User
        user = User.query.get(session['user_id'])
        
        if not user or not user.has_permission('user_manage'):
            flash('需要用户管理权限', 'error')
            return redirect(url_for('main.index'))
        
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function
