#!/usr/bin/env python
"""直接测试路由"""
import sys
sys.path.insert(0, '.')

from app import create_app, db
from app.models import Contract, PaymentRecord

app = create_app()

with app.app_context():
    contract = Contract.query.get(2)
    print(f"Contract: {contract.contract_no}")
    print(f"Payments before: {len(contract.payment_records)}")

# 测试数据
form_data = {
    'contract_no': 'CA/SHSHYM26032401',
    'company_name': 'Test',
    'product_count': '1',
    'product_0_code': 'CP5348595A',
    'product_0_name': '',
    'product_0_quantity': '1',
    'product_0_unit': '个',
    'product_0_price': '5000',
    'transaction_count': '0',
    'payment_count': '2',
    'payment_0_id': '2',
    'payment_0_amount': '1000',
    'payment_0_date': '2026-04-02',
    'payment_0_handler': 'Test',
    'payment_1_amount': '2000',
    'payment_1_date': '2026-04-03',
    'payment_1_handler': 'Test2',
}

print("\nSubmitting form...")

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 1
    
    try:
        resp = client.post('/contract/2/edit', data=form_data, follow_redirects=True)
        print(f"Response status: {resp.status_code}")
        
        # 检查是否重定向到查看页面
        if '/contract/2' in resp.request.path:
            print("Redirected to view page")
        
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

with app.app_context():
    contract = Contract.query.get(2)
    print(f"\nPayments after: {len(contract.payment_records)}")
    for p in contract.payment_records:
        print(f"  - ID {p.id}: {p.payment_amount} yuan")
    
    if len(contract.payment_records) >= 2:
        print("\nSUCCESS!")
    else:
        print("\nFAILED!")
