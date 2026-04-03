#!/usr/bin/env python
"""Test save payment record"""

import sys
sys.path.insert(0, '.')

from app import create_app, db
from app.models import Contract, PaymentRecord

app = create_app()

def test_save_payment():
    """Test saving contract with new payment"""
    print("=" * 60)
    print("TEST: Save contract with new payment record")
    print("=" * 60)
    
    with app.app_context():
        contract = Contract.query.get(2)
        print(f"\n1. Before save:")
        print(f"   Payments: {len(contract.payment_records)}")
        for p in contract.payment_records:
            print(f"   - ID {p.id}: {p.payment_amount} yuan")
        
        product = contract.contract_products[0]
        existing_payment = contract.payment_records[0]
        existing_trans = contract.transactions[0] if contract.transactions else None
    
    # Build form data
    form_data = {
        'contract_no': contract.contract_no,
        'company_name': contract.company_name,
        'product_count': '1',
        'product_0_code': product.product_code,
        'product_0_name': product.product_name or '',
        'product_0_quantity': str(product.quantity),
        'product_0_unit': product.unit,
        'product_0_price': str(product.price),
        'transaction_count': '1' if existing_trans else '0',
        'payment_count': '2',
        'payment_0_id': str(existing_payment.id),
        'payment_0_amount': str(existing_payment.payment_amount),
        'payment_0_date': str(existing_payment.payment_date),
        'payment_0_handler': existing_payment.handler or '',
        # New payment - no id
        'payment_1_amount': '2000',
        'payment_1_date': '2026-04-03',
        'payment_1_handler': 'Test',
        'payment_1_remark': 'New payment test',
    }
    
    if existing_trans:
        form_data.update({
            'transaction_0_id': str(existing_trans.id),
            'transaction_0_contract_product_id': product.product_code,
            'transaction_0_quantity': str(existing_trans.quantity),
            'transaction_0_price': str(existing_trans.price_with_tax),
            'transaction_0_handler': existing_trans.handler or '',
            'transaction_0_delivery_date': str(existing_trans.delivery_date),
        })
    
    print(f"\n2. Form data:")
    print(f"   payment_count = {form_data['payment_count']}")
    print(f"   payment_0_id = {form_data.get('payment_0_id')} (existing)")
    print(f"   payment_1_amount = {form_data.get('payment_1_amount')} (new, no id)")
    
    # Submit to actual route
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        
        print(f"\n3. Sending POST to /contract/2/edit...")
        resp = client.post('/contract/2/edit', data=form_data, follow_redirects=True)
        print(f"   Response: {resp.status_code}")
    
    # Check result
    with app.app_context():
        contract = Contract.query.get(2)
        print(f"\n4. After save:")
        print(f"   Payments: {len(contract.payment_records)}")
        for p in contract.payment_records:
            print(f"   - ID {p.id}: {p.payment_amount} yuan, date={p.payment_date}")
        
        # Check remarks
        print(f"\n5. Remarks:")
        if contract.remark:
            for r in contract.remark.split('\n')[-3:]:
                if r.strip():
                    print(f"   {r}")
        
        if len(contract.payment_records) >= 2:
            print("\n[PASS] Payment saved!")
            return True
        else:
            print("\n[FAIL] Payment NOT saved!")
            return False

if __name__ == '__main__':
    success = test_save_payment()
    sys.exit(0 if success else 1)
