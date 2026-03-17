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
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Session 配置（记住我功能）
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)  # 30天


class DevelopmentConfig(Config):
    """开发环境"""
    DEBUG = True


class ProductionConfig(Config):
    """生产环境"""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
