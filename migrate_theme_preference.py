#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库迁移脚本: 添加用户主题偏好字段
"""

import sqlite3
import os

def migrate():
    db_path = os.path.join('data', 'erp.db')
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'theme_preference' in columns:
            print("字段 'theme_preference' 已存在，跳过")
        else:
            # 添加字段
            cursor.execute("ALTER TABLE users ADD COLUMN theme_preference VARCHAR(500) DEFAULT '{\"background\": \"glass\", \"theme\": \"light\", \"style\": \"glass\"}'")
            print("已添加字段 'theme_preference'")
        
        conn.commit()
        print("迁移完成!")
        
    except Exception as e:
        conn.rollback()
        print(f"迁移失败: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
