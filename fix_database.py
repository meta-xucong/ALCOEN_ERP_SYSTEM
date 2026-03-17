#!/usr/bin/env python
"""
修复数据库表结构 - 添加 handler 字段到 transactions 表
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

def fix_database():
    """修复数据库"""
    app = create_app('development')
    
    with app.app_context():
        print("=" * 60)
        print("Fixing Database Schema")
        print("=" * 60)
        
        # 检查 transactions 表结构
        print("\nChecking transactions table...")
        result = db.session.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions'")
        ).fetchone()
        
        if result:
            print("Current table schema:")
            print(result[0][:200] + "...")
            
            if 'handler' in result[0]:
                print("\nOK - handler column already exists!")
                return
        
        # 需要重建表
        print("\nRebuilding transactions table with handler column...")
        
        # 删除已存在的临时表
        try:
            db.session.execute(text("DROP TABLE IF EXISTS transactions_new"))
            db.session.commit()
        except:
            pass
        
        # 创建新表
        db.session.execute(text("""
            CREATE TABLE transactions_new (
                id INTEGER PRIMARY KEY,
                contract_id INTEGER,
                contract_product_id INTEGER,
                company_name VARCHAR(100) NOT NULL,
                product_id INTEGER,
                product_code VARCHAR(50) NOT NULL,
                product_name VARCHAR(100),
                product_model VARCHAR(100),
                product_type VARCHAR(50),
                quantity FLOAT NOT NULL,
                unit VARCHAR(20) NOT NULL,
                price_with_tax FLOAT NOT NULL,
                total_price_with_tax FLOAT NOT NULL,
                handler VARCHAR(50) NOT NULL DEFAULT '',
                delivery_date DATE NOT NULL,
                invoice_date DATE,
                contract_no VARCHAR(100),
                remark TEXT,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
        
        # 获取原表的所有列
        result = db.session.execute(text("PRAGMA table_info(transactions)"))
        columns = result.fetchall()
        column_names = [col[1] for col in columns]
        print(f"\nOriginal columns: {column_names}")
        
        # 构建插入语句
        common_columns = []
        for col in column_names:
            if col in ['id', 'contract_id', 'contract_product_id', 'company_name', 
                       'product_id', 'product_code', 'product_name', 'product_model',
                       'product_type', 'quantity', 'unit', 'price_with_tax', 
                       'total_price_with_tax', 'delivery_date', 'invoice_date',
                       'contract_no', 'remark', 'created_at', 'updated_at']:
                common_columns.append(col)
        
        cols_str = ', '.join(common_columns)
        print(f"\nCopying columns: {cols_str}")
        
        # 复制数据
        db.session.execute(text(f"""
            INSERT INTO transactions_new (
                {cols_str}, handler
            )
            SELECT 
                {cols_str}, ''
            FROM transactions
        """))
        
        # 删除旧表，重命名新表
        db.session.execute(text("DROP TABLE transactions"))
        db.session.execute(text("ALTER TABLE transactions_new RENAME TO transactions"))
        db.session.commit()
        
        # 验证
        result = db.session.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions'")
        ).fetchone()
        
        if result and 'handler' in result[0]:
            print("\nOK - Table fixed successfully!")
            print("New schema includes handler column.")
        else:
            print("\nERROR - Failed to fix table!")
        
        print("=" * 60)

if __name__ == '__main__':
    fix_database()
