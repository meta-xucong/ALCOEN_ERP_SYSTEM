#!/usr/bin/env python
"""Test payment record add bug"""

import sys
sys.path.insert(0, '.')

from app import create_app, db
from app.models import Contract, PaymentRecord

app = create_app()

def test_payment_add():
    """Test adding payment record"""
    print("=" * 60)
    print("TEST: Add payment record when editing contract")
    print("=" * 60)
    
    with app.app_context():
        contract = Contract.query.get(2)
        print(f"\n1. Contract: {contract.contract_no}")
        print(f"   Current payments: {len(contract.payment_records)}")
        for p in contract.payment_records:
            print(f"   - Payment {p.id}: {p.payment_amount} yuan")
        
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
            'payment_count': '2',
            'payment_0_id': str(payment.id),
            'payment_0_amount': str(payment.payment_amount),
            'payment_0_date': str(payment.payment_date),
            'payment_0_handler': payment.handler or '',
            'payment_1_amount': '2000',
            'payment_1_date': '2026-04-03',
            'payment_1_handler': 'Test',
            'payment_1_remark': 'New payment',
        }
        
        print(f"\n2. Submit form (payment_count=2):")
        for k, v in sorted(form_data.items()):
            if 'payment' in k:
                print(f"   {k}={v}")
    
    # Submit form
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        
        print("\n3. Sending POST request...")
        resp = client.post('/contract/2/edit', data=form_data, follow_redirects=True)
        print(f"   Response status: {resp.status_code}")
        
        # Check response
        html = resp.data.decode('utf-8', errors='ignore')
        if 'success' in html.lower() or 'alert-success' in html:
            print("   Flash: success")
        elif 'error' in html.lower() or 'alert-danger' in html:
            print("   Flash: error")
    
    # Check result
    with app.app_context():
        contract = Contract.query.get(2)
        print(f"\n4. After save - payments: {len(contract.payment_records)}")
        for p in contract.payment_records:
            print(f"   - Payment {p.id}: {p.payment_amount} yuan, handler={p.handler}")
        
        if len(contract.payment_records) >= 2:
            print("\n[PASS] Payment record added successfully!")
            return True
        else:
            print("\n[FAIL] Payment record NOT added!")
            # Check remarks for debug info
            print("\n5. Contract remarks (last 5):")
            remarks = contract.remark.split('\n') if contract.remark else []
            for r in remarks[-5:]:
                if r.strip():
                    print(f"   {r}")
            return False

if __name__ == '__main__':
    success = test_payment_add()
    sys.exit(0 if success else 1)
