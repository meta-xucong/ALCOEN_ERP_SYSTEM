"""
v1.4 添加合同创建人字段迁移脚本
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app, db
from app.models import Contract

app = create_app()

def migrate():
    """添加 created_by_id 字段到 contracts 表"""
    with app.app_context():
        # 检查字段是否已存在
        from sqlalchemy import text
        try:
            db.session.execute(text("SELECT created_by_id FROM contracts LIMIT 1"))
            print("[OK] created_by_id 字段已存在，跳过迁移")
            return
        except:
            pass
        
        # 添加字段
        try:
            db.session.execute(text("""
                ALTER TABLE contracts 
                ADD COLUMN created_by_id INTEGER 
                REFERENCES users(id)
            """))
            db.session.commit()
            print("[OK] created_by_id 字段添加成功")
        except Exception as e:
            print(f"[ERROR] 迁移失败: {e}")
            db.session.rollback()

if __name__ == '__main__':
    migrate()
