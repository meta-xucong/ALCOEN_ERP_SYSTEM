import os
from flask import Flask, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect
from config import config

# 尝试加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"[INFO] 已加载环境变量文件: {env_path}")
except ImportError:
    pass  # python-dotenv 未安装，忽略

db = SQLAlchemy()


def _run_lightweight_schema_upgrades():
    """Apply additive QC schema upgrades for SQLite deployments without Alembic."""
    inspector = inspect(db.engine)

    if inspector.has_table('qc_work_orders'):
        order_columns = {column['name'] for column in inspector.get_columns('qc_work_orders')}
        alter_statements = []
        if 'workpiece_id' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN workpiece_id INTEGER')
        if 'drawing_note_file_path' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN drawing_note_file_path VARCHAR(500)')
        if 'drawing_note_file_type' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN drawing_note_file_type VARCHAR(50)')
        if 'drawing_note_original_name' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN drawing_note_original_name VARCHAR(255)')
        if 'guide_certificate_file_path' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN guide_certificate_file_path VARCHAR(500)')
        if 'guide_certificate_file_type' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN guide_certificate_file_type VARCHAR(50)')
        if 'guide_certificate_original_name' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN guide_certificate_original_name VARCHAR(255)')
        if 'remark_note_file_path' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN remark_note_file_path VARCHAR(500)')
        if 'remark_note_file_type' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN remark_note_file_type VARCHAR(50)')
        if 'remark_note_original_name' not in order_columns:
            alter_statements.append('ALTER TABLE qc_work_orders ADD COLUMN remark_note_original_name VARCHAR(255)')
        if alter_statements:
            with db.engine.begin() as connection:
                for statement in alter_statements:
                    connection.exec_driver_sql(statement)

    if inspector.has_table('qc_inspection_records'):
        inspection_columns = {column['name'] for column in inspector.get_columns('qc_inspection_records')}
        alter_statements = []
        if 'report_file_path' not in inspection_columns:
            alter_statements.append(
                'ALTER TABLE qc_inspection_records ADD COLUMN report_file_path VARCHAR(500)'
            )
        if 'report_file_type' not in inspection_columns:
            alter_statements.append(
                'ALTER TABLE qc_inspection_records ADD COLUMN report_file_type VARCHAR(50)'
            )
        if 'report_original_name' not in inspection_columns:
            alter_statements.append(
                'ALTER TABLE qc_inspection_records ADD COLUMN report_original_name VARCHAR(255)'
            )
        if alter_statements:
            with db.engine.begin() as connection:
                for statement in alter_statements:
                    connection.exec_driver_sql(statement)


def create_app(config_name='default'):
    """创建Flask应用实例"""
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')

    uploads_root = os.path.join(app.static_folder, 'uploads')
    
    # 加载配置
    app.config.from_object(config[config_name])
    
    # 初始化扩展
    db.init_app(app)
    
    # 注册蓝图
    from app.routes.main import main_bp, portal_bp
    from app.routes.transaction import transaction_bp
    from app.routes.statement import statement_bp
    from app.routes.product import product_bp
    from app.routes.contract import contract_bp
    from app.routes.auth import auth_bp
    from app.routes.user import user_bp
    from app.routes.role import role_bp
    from app.routes.department import department_bp
    from app.routes.theme import theme_bp
    from app.routes.settings import settings_bp
    from app.routes.backup import backup_bp
    from app.routes.qc import qc_bp
    app.register_blueprint(portal_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(qc_bp)
    app.register_blueprint(transaction_bp, url_prefix='/transaction')
    app.register_blueprint(statement_bp, url_prefix='/statement')
    app.register_blueprint(product_bp, url_prefix='/product')
    app.register_blueprint(contract_bp, url_prefix='/contract')
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(role_bp)
    app.register_blueprint(department_bp)
    app.register_blueprint(theme_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(backup_bp)
    
    # [v1.5.2] 禁用缓存，确保合同状态更新后立即显示
    @app.after_request
    def disable_caching(response):
        if 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        """Serve uploaded files stored under the static/uploads directory."""
        return send_from_directory(uploads_root, filename)
    
    # 注册模板全局变量
    @app.context_processor
    def inject_user():
        """注入当前用户到模板"""
        from flask import session
        from app.models import User
        
        user = None
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
        
        return dict(current_user=user)
    
    # 注册主题偏好上下文处理器
    @app.context_processor
    def inject_theme():
        """注入用户主题偏好到模板"""
        from flask import session
        from app.models import User
        import os
        
        default_theme = {'bg_type': 'video', 'bg_image': 'bg-main.jpg', 'theme': 'light', 'style': 'glass'}
        
        if 'user_id' in session:
            user = User.query.get(session['user_id'])
            if user:
                theme = user.get_theme_preference()
                # 添加背景图片URL
                if theme.get('bg_type') == 'image' and theme.get('bg_image'):
                    theme['bg_image_url'] = f"static/img/backgrounds/{theme['bg_image']}"
                return dict(theme=theme)
        
        return dict(theme=default_theme)
    
    # 注册模板过滤器
    from datetime import datetime
    
    @app.template_filter('format_date')
    def format_date(value):
        """格式化日期"""
        if value is None:
            return ''
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, '%Y-%m-%d')
            except:
                return value
        return value.strftime('%Y-%m-%d')
    
    @app.template_filter('format_money')
    def format_money(value):
        """格式化金额"""
        if value is None:
            return '0.00'
        return f"{float(value):,.2f}"
    
    # 创建数据库表
    with app.app_context():
        db.create_all()
        _run_lightweight_schema_upgrades()
        from app.services.auth_service import AuthService
        AuthService.ensure_qc_roles()
    
    return app
