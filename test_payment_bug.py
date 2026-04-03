#!/usr/bin/env python
"""
测试回款记录添加问题
模拟用户在编辑合同时添加新的回款记录
"""

import sys
sys.path.insert(0, '.')

from app import create_app, db
from app.models import Contract, PaymentRecord

app = create_app()

def test_payment_add():
    """测试添加回款记录"""
    print("=" * 60)
    print("测试: 编辑合同时添加回款记录")
    print("=" * 60)
    
    with app.app_context():
        contract = Contract.query.get(2)
        print(f"\n1. 合同: {contract.contract_no}")
        print(f"   当前回款记录数: {len(contract.payment_records)}")
        for p in contract.payment_records:
            print(f"   - Payment {p.id}: {p.payment_amount}元")
        
        # 获取表单需要的数据
        product = contract.contract_products[0]
        payment = contract.payment_records[0]
        
        form_data = {
            'contract_no': contract.contract_no,
            'company_name': contract.company_name,
            'product_count': '1',
            'product_0_code': product.product_code,
            'product_0_name': product.product_name or '',
            'product_0_quantity': str(product.quantity),
            'product_0_unit': product.unit,
            'product_0_price': str(product.price),
            'transaction_count': '0',
            'payment_count': '2',  # 1条已有 + 1条新增
            # 已有记录
            'payment_0_id': str(payment.id),
            'payment_0_amount': str(payment.payment_amount),
            'payment_0_date': str(payment.payment_date),
            'payment_0_handler': payment.handler or '',
            # 新增记录 (payment_1 没有 id)
            'payment_1_amount': '2000',
            'payment_1_date': '2026-04-03',
            'payment_1_handler': 'Test',
            'payment_1_remark': 'New payment',
        }
        
        print(f"\n2. 提交表单 (payment_count=2):")
        for k, v in form_data.items():
            if 'payment' in k:
                print(f"   {k}={v}")
    
    # 提交表单
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        
        resp = client.post(f'/contract/2/edit', data=form_data, follow_redirects=True)
        print(f"\n3. 提交响应状态: {resp.status_code}")
    
    # 检查结果
    with app.app_context():
        contract = Contract.query.get(2)
        print(f"\n4. 保存后回款记录数: {len(contract.payment_records)}")
        for p in contract.payment_records:
            print(f"   - Payment {p.id}: {p.payment_amount}元, handler={p.handler}")
        
        if len(contract.payment_records) >= 2:
            print("\n✓ 测试通过: 回款记录添加成功")
            return True
        else:
            print("\n✗ 测试失败: 回款记录未添加")
            return False

if __name__ == '__main__':
    success = test_payment_add()
    sys.exit(0 if success else 1)
