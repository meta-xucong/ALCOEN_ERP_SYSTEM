#!/usr/bin/env python
"""
[v1.4] 迁移脚本：创建 contract_files 表
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
        print("迁移：创建 contract_files 表")
        print("=" * 60)
        
        # 检查表是否已存在
        result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='contract_files'"))
        if result.fetchone():
            print("\n表 contract_files 已存在，跳过创建")
            return
        
        # 创建表
        create_sql = """
        CREATE TABLE contract_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            filename VARCHAR(255) NOT NULL,
            filepath VARCHAR(500) NOT NULL,
            file_type VARCHAR(50),
            file_size INTEGER,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (contract_id) REFERENCES contracts (id) ON DELETE CASCADE
        )
        """
        
        db.session.execute(text(create_sql))
        
        # 创建索引
        db.session.execute(text("CREATE INDEX ix_contract_files_contract_id ON contract_files(contract_id)"))
        
        db.session.commit()
        
        print("\n✓ 表 contract_files 创建成功")
        print("✓ 索引创建成功")
        
        print("\n" + "=" * 60)
        print("迁移完成！")
        print("=" * 60)

if __name__ == '__main__':
    migrate()
