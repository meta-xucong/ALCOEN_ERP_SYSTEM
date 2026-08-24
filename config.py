import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'exports'), exist_ok=True)


class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'alcoden-erp-secret-key-2024'
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{os.path.join(DATA_DIR, "erp.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 分页配置
    ITEMS_PER_PAGE = 20
    
    # 文件上传/导出
    EXPORT_FOLDER = os.path.join(BASE_DIR, 'exports')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB, aligned with nginx client_max_body_size
    OFFICIAL_CONTRACT_TEMPLATE_FOLDER = os.path.join(
        DATA_DIR,
        'official_contract_templates',
    )
    OFFICIAL_CONTRACT_EXPORT_FOLDER = os.path.join(
        BASE_DIR,
        'exports',
        'official_contracts',
    )
    
    # Session 配置（记住我功能）
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)  # 30天
    
    # 邮件配置 (腾讯企业邮箱)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.exmail.qq.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 465)
    MAIL_USE_SSL = True
    MAIL_USE_TLS = False
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or ''  # 邮箱地址，如: erp@yourcompany.com
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or ''  # 邮箱密码或授权码
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or ('ERP系统', MAIL_USERNAME)
    
    # 验证码配置
    VERIFY_CODE_LENGTH = 4  # 验证码长度
    VERIFY_CODE_EXPIRE_MINUTES = 15  # 验证码有效期（分钟）
    TRUSTED_DEVICE_DAYS = 30  # 受信任设备有效期（天）

    # Legacy emergency switch. Production and tests use explicit AI CATS identities by default.
    AI_CATS_TEST_OPEN_ACCESS = os.environ.get('AI_CATS_TEST_OPEN_ACCESS', '0').lower() not in ('0', 'false', 'no')


class DevelopmentConfig(Config):
    """开发环境"""
    DEBUG = True


class ProductionConfig(Config):
    """生产环境"""
    DEBUG = False
    # Formal operation must never inherit the legacy all-user test override.
    AI_CATS_TEST_OPEN_ACCESS = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
