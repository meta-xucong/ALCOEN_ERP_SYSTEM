#!/usr/bin/env python
"""
数据迁移脚本：v1.0 → v1.1

迁移内容：
1. 创建 products 表
2. 创建默认产品 product_code="0"
3. 将所有交易记录的 product_code 设为 "0"
4. 建立 product_id 关联

注意：
- 原有 product_name 数据保留在 transaction.product_name
- product_model 和 product_type 初始为空
- 后续请手动进入产品库修改产品编码信息
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app, db
from app.models import Transaction, Product, Company


def migrate():
    """执行数据迁移"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("ALCOEN ERP v1.0 to v1.1 Data Migration")
        print("=" * 60)
        
        # Step 1: 创建表（如果不存在）
        print("\n[1/4] Checking and creating database tables...")
        db.create_all()
        print("OK - Database tables checked")
        
        # Step 2: 检查是否已有产品数据
        existing_products = Product.query.count()
        if existing_products > 0:
            print(f"\n[2/4] Found {existing_products} existing products, skip default product creation")
        else:
            print("\n[2/4] Creating default product (code: 0)...")
            default_product = Product(
                product_code="0",
                product_name="Migrated from v1.0",
                product_model=None,
                product_type=None,
                default_price=0,
                remark="Migrated from v1.0, please update product code manually"
            )
            db.session.add(default_product)
            db.session.flush()
            print(f"OK - Default product created (ID: {default_product.id})")
        
        # Step 3: Migrate transactions
        print("\n[3/4] Migrating transactions...")
        transactions = Transaction.query.all()
        
        if not transactions:
            print("  No transactions to migrate")
        else:
            # Get default product
            default_product = Product.query.filter_by(product_code="0").first()
            if not default_product:
                print("  ERROR: Default product not found")
                return
            
            updated_count = 0
            skipped_count = 0
            
            for trans in transactions:
                # Check if already migrated
                if hasattr(trans, 'product_code') and trans.product_code and trans.product_code != '':
                    skipped_count += 1
                    continue
                
                # Set product_code to "0"
                trans.product_code = "0"
                trans.product_id = default_product.id
                updated_count += 1
            
            db.session.commit()
            print(f"OK - Transactions migrated")
            print(f"  - Updated: {updated_count}")
            print(f"  - Skipped: {skipped_count}")
        
        # Step 4: Verify
        print("\n[4/4] Verifying migration...")
        product_count = Product.query.count()
        transaction_count = Transaction.query.count()
        
        print(f"OK - Products: {product_count}")
        print(f"OK - Transactions: {transaction_count}")
        
        # Check for null product_code
        null_code_count = Transaction.query.filter(
            (Transaction.product_code == None) | (Transaction.product_code == '')
        ).count()
        
        if null_code_count > 0:
            print(f"WARNING: {null_code_count} transactions still missing product_code")
        else:
            print("OK - All transactions have product_code")
        
        print("\n" + "=" * 60)
        print("Migration completed!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Start system: python run.py")
        print("2. Visit product page to add new product codes")
        print("3. Select correct product code when adding new transactions")
        print("4. Edit existing transactions to update product codes")
        print("\nNote: Existing transactions product_code set to '0'")
        print("      Please update product codes manually later")
        print("=" * 60)


def rollback():
    """回滚迁移（仅用于测试）"""
    app = create_app()
    
    with app.app_context():
        print("⚠ 回滚迁移...")
        
        # 删除所有产品（会级联删除关联）
        Product.query.delete()
        
        # 重置交易记录的产品编码
        transactions = Transaction.query.all()
        for trans in transactions:
            trans.product_code = None
            trans.product_id = None
        
        db.session.commit()
        print("✓ 回滚完成")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='ALCOEN ERP 数据迁移工具')
    parser.add_argument('--rollback', action='store_true', help='回滚迁移')
    
    args = parser.parse_args()
    
    if args.rollback:
        confirm = input("确定要回滚迁移吗？这将删除所有产品数据！(yes/no): ")
        if confirm.lower() == 'yes':
            rollback()
        else:
            print("取消回滚")
    else:
        migrate()
