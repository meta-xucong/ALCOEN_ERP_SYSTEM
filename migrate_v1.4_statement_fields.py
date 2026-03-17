#!/usr/bin/env python
"""
[v1.4] 迁移脚本：为Statement表添加created_by_id和department字段
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

def migrate():
    """执行迁移"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("迁移：为 statements 表添加字段")
        print("=" * 60)
        
        # 检查字段是否已存在
        result = db.session.execute(text("PRAGMA table_info(statements)"))
        columns = [row[1] for row in result]
        
        if 'created_by_id' not in columns:
            print("\n添加 created_by_id 字段...")
            db.session.execute(text("ALTER TABLE statements ADD COLUMN created_by_id INTEGER"))
            print("✓ created_by_id 添加成功")
        else:
            print("\n✓ created_by_id 字段已存在")
        
        if 'department' not in columns:
            print("\n添加 department 字段...")
            db.session.execute(text("ALTER TABLE statements ADD COLUMN department VARCHAR(100)"))
            print("✓ department 添加成功")
        else:
            print("\n✓ department 字段已存在")
        
        # 创建索引
        try:
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_statements_department ON statements(department)"))
            print("✓ department 索引创建成功")
        except Exception as e:
            print(f"索引已存在或创建失败: {e}")
        
        db.session.commit()
        
        print("\n" + "=" * 60)
        print("迁移完成！")
        print("=" * 60)

if __name__ == '__main__':
    migrate()
