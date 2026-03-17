#!/usr/bin/env python
"""
数据库迁移脚本：创建部门和负责人表 v1.3
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

def migrate():
    """执行迁移"""
    app = create_app('development')
    
    with app.app_context():
        print("=" * 60)
        print("Database Migration: Create Department/Manager Tables")
        print("=" * 60)
        
        # 创建新表
        print("\n[1/2] Creating departments table...")
        try:
            db.create_all()
            print("OK - Tables created")
        except Exception as e:
            print(f"INFO - {e}")
        
        # 检查contracts表是否需要添加department和manager字段
        print("\n[2/2] Checking contracts table...")
        try:
            result = db.session.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='contracts'")
            ).fetchone()
            
            if result and 'department' not in result[0]:
                print("  - Adding department and manager columns")
                db.session.execute(text("ALTER TABLE contracts ADD COLUMN department VARCHAR(100)"))
                db.session.execute(text("ALTER TABLE contracts ADD COLUMN manager VARCHAR(100)"))
                db.session.commit()
                print("OK - Columns added")
            else:
                print("OK - Columns already exist")
        except Exception as e:
            print(f"ERROR - {e}")
            db.session.rollback()
        
        print("\n" + "=" * 60)
        print("Migration completed!")
        print("=" * 60)

if __name__ == '__main__':
    migrate()
