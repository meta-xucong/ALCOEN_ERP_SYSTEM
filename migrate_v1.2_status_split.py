#!/usr/bin/env python3
"""
[LOGIC-7] 数据库迁移脚本：拆分合同完成状态
添加 delivery_status 和 payment_status 字段
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Contract
from app.services.contract_service import ContractService
from sqlalchemy import text


def migrate():
    """执行迁移"""
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("[LOGIC-7] 迁移：拆分合同完成状态")
        print("=" * 60)
        
        # 检查字段是否存在
        with db.engine.connect() as conn:
            # 获取contracts表的所有列
            result = conn.execute(text("PRAGMA table_info(contracts)"))
            columns = [row[1] for row in result.fetchall()]
            
            # 添加 delivery_status 字段
            if 'delivery_status' not in columns:
                print("\n1. 添加 delivery_status 字段...")
                conn.execute(text(
                    "ALTER TABLE contracts ADD COLUMN delivery_status VARCHAR(20) DEFAULT 'pending'"
                ))
                conn.commit()
                print("   [OK] delivery_status 字段已添加")
            else:
                print("\n1. delivery_status 字段已存在，跳过")
            
            # 添加 payment_status 字段
            if 'payment_status' not in columns:
                print("\n2. 添加 payment_status 字段...")
                conn.execute(text(
                    "ALTER TABLE contracts ADD COLUMN payment_status VARCHAR(20) DEFAULT 'pending'"
                ))
                conn.commit()
                print("   [OK] payment_status 字段已添加")
            else:
                print("\n2. payment_status 字段已存在，跳过")
        
        # 初始化现有合同的状态
        print("\n3. 初始化现有合同的状态...")
        contracts = Contract.query.all()
        updated_count = 0
        
        for contract in contracts:
            # 直接计算统计数据
            total_planned_qty = sum(cp.quantity for cp in contract.contract_products)
            total_delivered_qty = sum(cp.get_delivered_quantity() for cp in contract.contract_products)
            total_planned_value = sum(cp.total for cp in contract.contract_products)
            total_paid = sum((t.payment_amount or 0) for t in contract.transactions)
            
            # 计算发货状态
            if total_planned_qty == 0:
                delivery_status = 'pending'
            elif total_delivered_qty >= total_planned_qty:
                delivery_status = 'completed'
            elif total_delivered_qty > 0:
                delivery_status = 'partial'
            else:
                delivery_status = 'pending'
            
            # 计算回款状态
            if total_planned_value == 0:
                payment_status = 'pending'
            elif total_paid >= total_planned_value:
                payment_status = 'completed'
            elif total_paid > 0:
                payment_status = 'partial'
            else:
                payment_status = 'pending'
            
            contract.delivery_status = delivery_status
            contract.payment_status = payment_status
            updated_count += 1
        
        db.session.commit()
        print(f"   [OK] 已更新 {updated_count} 个合同的状态")
        
        print("\n" + "=" * 60)
        print("迁移完成！")
        print("=" * 60)


if __name__ == '__main__':
    migrate()
