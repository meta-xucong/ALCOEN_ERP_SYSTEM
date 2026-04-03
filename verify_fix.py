#!/usr/bin/env python
"""验证回款记录修复"""
import sys
sys.path.insert(0, '.')

from app import create_app, db
from app.models import Contract, PaymentRecord

app = create_app()

def verify():
    print("=" * 60)
    print("VERIFY: Payment record save fix")
    print("=" * 60)
    
    with app.app_context():
        contract = Contract.query.get(2)
        print(f"\nContract: {contract.contract_no}")
        print(f"Before: {len(contract.payment_records)} payments")
        for p in contract.payment_records:
            print(f"  - ID {p.id}: {p.payment_amount} yuan")
        
        product = contract.contract_products[0]
        existing = contract.payment_records[0]
        trans = contract.transactions[0] if contract.transactions else None
    
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
        'transaction_count': '1' if trans else '0',
        'payment_count': '2',
        'payment_0_id': str(existing.id),
        'payment_0_amount': str(existing.payment_amount),
        'payment_0_date': str(existing.payment_date),
        'payment_0_handler': existing.handler or '',
        'payment_1_amount': '2000',
        'payment_1_date': '2026-04-03',
        'payment_1_handler': 'Test',
        'payment_1_remark': 'Test new payment',
    }
    
    if trans:
        form_data.update({
            'transaction_0_id': str(trans.id),
            'transaction_0_contract_product_id': product.product_code,
            'transaction_0_quantity': str(trans.quantity),
            'transaction_0_price': str(trans.price_with_tax),
            'transaction_0_handler': trans.handler or '',
            'transaction_0_delivery_date': str(trans.delivery_date),
        })
    
    print(f"\nSubmitting form with payment_count=2...")
    
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1
        resp = client.post('/contract/2/edit', data=form_data, follow_redirects=True)
        print(f"Response: {resp.status_code}")
    
    with app.app_context():
        contract = Contract.query.get(2)
        print(f"\nAfter: {len(contract.payment_records)} payments")
        for p in contract.payment_records:
            print(f"  - ID {p.id}: {p.payment_amount} yuan, date={p.payment_date}")
        
        if len(contract.payment_records) >= 2:
            print("\n✓ FIX WORKS! New payment saved.")
            return True
        else:
            print("\n✗ FIX FAILED! Payment not saved.")
            return False

if __name__ == '__main__':
    success = verify()
    sys.exit(0 if success else 1)
