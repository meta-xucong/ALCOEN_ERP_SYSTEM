#!/usr/bin/env python
"""
数据迁移脚本：v1.1 → v1.2
将现有交易记录转换为合同-交易记录模式
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from datetime import datetime
from app import create_app, db
from app.models import Transaction, Contract, ContractProduct
from app.services.contract_service import ContractService


def migrate():
    """执行数据迁移"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("ALCOEN ERP v1.1 to v1.2 Data Migration")
        print("=" * 60)
        
        # 检查是否已有合同数据
        existing_contracts = Contract.query.count()
        if existing_contracts > 0:
            print(f"\nFound {existing_contracts} existing contracts.")
            print("Migration already completed or has existing data.")
            print("Skip migration.")
            return
        
        # 获取所有现有交易记录
        transactions = Transaction.query.all()
        print(f"\nFound {len(transactions)} transactions to migrate.")
        
        if not transactions:
            print("No transactions to migrate.")
            return
        
        # 按公司分组
        company_groups = {}
        for trans in transactions:
            company = trans.company_name
            if company not in company_groups:
                company_groups[company] = []
            company_groups[company].append(trans)
        
        print(f"\nGrouped by {len(company_groups)} companies.")
        
        # 为每个公司创建一个合同
        for company, trans_list in company_groups.items():
            print(f"\nProcessing company: {company} ({len(trans_list)} transactions)")
            
            # 生成合同编号
            timestamp = datetime.now().strftime('%Y%m%d')
            contract_no = f"HT{timestamp}-{company[:4]}"
            
            # 收集产品
            products_data = []
            product_codes = set()
            
            for trans in trans_list:
                if trans.product_code not in product_codes:
                    product_codes.add(trans.product_code)
                    products_data.append({
                        'product_code': trans.product_code,
                        'product_name': trans.product_name,
                        'product_model': trans.product_model,
                        'product_type': trans.product_type,
                        'quantity': trans.quantity,
                        'unit': trans.unit,
                        'price': trans.price_with_tax
                    })
            
            # 创建合同
            contract_data = {
                'contract_no': contract_no,
                'company_name': company
            }
            
            try:
                contract = ContractService.create_contract(contract_data, products_data)
                print(f"  Created contract: {contract_no}")
                
                # 关联交易记录到合同
                for trans in trans_list:
                    trans.contract_id = contract.id
                    trans.contract_no = contract_no
                
                db.session.commit()
                print(f"  Migrated {len(trans_list)} transactions")
                
            except Exception as e:
                print(f"  Error: {e}")
                db.session.rollback()
        
        print("\n" + "=" * 60)
        print("Migration completed!")
        print("=" * 60)
        print(f"\nNew contracts: {Contract.query.count()}")
        print(f"Linked transactions: {Transaction.query.filter(Transaction.contract_id.isnot(None)).count()}")
        print("\nNext steps:")
        print("1. Start server: python run.py")
        print("2. Visit: http://localhost:8080")
        print("3. Use '交易合同' menu to manage contracts")


if __name__ == '__main__':
    migrate()
