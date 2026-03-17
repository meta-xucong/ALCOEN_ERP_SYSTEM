#!/usr/bin/env python
"""
数据库迁移脚本：v1.2 -> v1.3
主要变更：
1. 添加 PaymentRecord 回款记录表
2. Transaction 表添加 handler（经手人）字段
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, date
from app import create_app, db
from app.models import Transaction, PaymentRecord
from sqlalchemy import text

def migrate():
    """执行迁移"""
    app = create_app('development')
    
    with app.app_context():
        print("=" * 60)
        print("Database Migration: v1.2 -> v1.3")
        print("=" * 60)
        
        # 1. 创建 PaymentRecord 表
        print("\n[1/3] Creating payment_records table...")
        try:
            db.create_all()
            print("OK - payment_records table created")
        except Exception as e:
            print(f"INFO - {e}")
        
        # 2. 添加 handler 字段到 transactions 表
        print("\n[2/3] Checking transactions table structure...")
        try:
            # 使用 SQL 直接检查字段是否存在
            result = db.session.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions'")
            ).fetchone()
            
            if result and 'handler' not in result[0]:
                print("  - Adding handler column")
                # SQLite 不直接支持 ADD COLUMN，需要使用表重建
                print("  - Rebuilding table...")
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
                
                # 复制数据（不复制handler，使用默认值）
                db.session.execute(text("""
                    INSERT INTO transactions_new (
                        id, contract_id, contract_product_id, company_name,
                        product_id, product_code, product_name, product_model, product_type,
                        quantity, unit, price_with_tax, total_price_with_tax,
                        handler, delivery_date, invoice_date, contract_no, remark,
                        created_at, updated_at
                    )
                    SELECT 
                        id, contract_id, contract_product_id, company_name,
                        product_id, product_code, product_name, product_model, product_type,
                        quantity, unit, price_with_tax, total_price_with_tax,
                        '', delivery_date, invoice_date, contract_no, remark,
                        created_at, updated_at
                    FROM transactions
                """))
                
                # 删除旧表，重命名新表
                db.session.execute(text("DROP TABLE transactions"))
                db.session.execute(text("ALTER TABLE transactions_new RENAME TO transactions"))
                db.session.commit()
                print("OK - handler column added")
            else:
                print("OK - handler column already exists")
                
        except Exception as e:
            print(f"ERROR - Failed to modify transactions table: {e}")
            db.session.rollback()
        
        # 3. 将原有的回款数据迁移到 PaymentRecord 表
        print("\n[3/3] Migrating payment data...")
        try:
            # 检查是否已有数据
            existing_count = PaymentRecord.query.count()
            if existing_count > 0:
                print(f"  - Found {existing_count} existing payment records, skipping migration")
            else:
                # 查询有回款金额的交易记录
                result = db.session.execute(
                    text("SELECT * FROM transactions WHERE payment_amount IS NOT NULL AND payment_amount > 0")
                )
                transactions_with_payment = result.fetchall()
                
                if transactions_with_payment:
                    print(f"  - Found {len(transactions_with_payment)} records with payment_amount")
                    
                    for trans in transactions_with_payment:
                        # 转换日期字符串为date对象
                        payment_date = trans.payment_date
                        if isinstance(payment_date, str):
                            payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
                        elif payment_date is None:
                            # 使用发货日期
                            if isinstance(trans.delivery_date, str):
                                payment_date = datetime.strptime(trans.delivery_date, '%Y-%m-%d').date()
                            else:
                                payment_date = trans.delivery_date
                        
                        # 创建回款记录
                        payment = PaymentRecord(
                            contract_id=trans.contract_id,
                            company_name=trans.company_name,
                            payment_amount=float(trans.payment_amount),
                            payment_date=payment_date,
                            transaction_id=trans.id,
                            remark=f"Migrated from transaction #{trans.id}"
                        )
                        db.session.add(payment)
                    
                    db.session.commit()
                    print(f"OK - Migrated {len(transactions_with_payment)} payment records")
                else:
                    print("  - No payment data to migrate")
                
        except Exception as e:
            print(f"ERROR - Failed to migrate payment data: {e}")
            db.session.rollback()
        
        print("\n" + "=" * 60)
        print("Migration completed!")
        print("=" * 60)
        print("\nNote:")
        print("1. The payment_amount and payment_date columns in transactions")
        print("   table are no longer used. You can manually drop them later.")
        print("=" * 60)

if __name__ == '__main__':
    migrate()
