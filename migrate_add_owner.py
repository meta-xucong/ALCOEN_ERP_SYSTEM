#!/usr/bin/env python3
"""
[问题4] 数据库迁移脚本：添加归属人字段
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
        print("[问题4] 迁移：添加归属人字段")
        print("=" * 60)
        
        # 检查字段是否存在
        with db.engine.connect() as conn:
            # 获取contracts表的所有列
            result = conn.execute(text("PRAGMA table_info(contracts)"))
            columns = [row[1] for row in result.fetchall()]
            
            # 添加 owner 字段
            if 'owner' not in columns:
                print("\n1. 添加 owner 字段...")
                conn.execute(text(
                    "ALTER TABLE contracts ADD COLUMN owner VARCHAR(100)"
                ))
                conn.commit()
                print("   [OK] owner 字段已添加")
            else:
                print("\n1. owner 字段已存在，跳过")
        
        print("\n" + "=" * 60)
        print("迁移完成！")
        print("=" * 60)


if __name__ == '__main__':
    migrate()
