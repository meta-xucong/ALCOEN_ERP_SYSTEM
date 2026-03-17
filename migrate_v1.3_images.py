#!/usr/bin/env python
"""
数据库迁移脚本：创建合同图片表 v1.3
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
        print("Database Migration: Create ContractImage Table")
        print("=" * 60)
        
        # 创建新表
        print("\n[1/1] Creating contract_images table...")
        try:
            db.create_all()
            print("OK - Tables created")
        except Exception as e:
            print(f"INFO - {e}")
        
        print("\n" + "=" * 60)
        print("Migration completed!")
        print("=" * 60)

if __name__ == '__main__':
    migrate()
