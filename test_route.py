#!/usr/bin/env python
"""Test with CSRF token"""
import sys
sys.path.insert(0, '.')

from app import create_app, db
from app.models import Contract, PaymentRecord

app = create_app()

# Enable CSRF for testing
app.config['WTF_CSRF_ENABLED'] = True

with app.app_context():
    contract = Contract.query.get(2)
    print(f"Contract: {contract.contract_no}")
    print(f"Payments before: {len(contract.payment_records)}")

# Get CSRF token first
with app.test_client() as client:
    # Get edit page to obtain CSRF token
    resp = client.get('/contract/2/edit')
    html = resp.data.decode('utf-8')
    
    # Extract CSRF token
    import re
    csrf_match = re.search(r'name="csrf_token" .* value="([^"]+)"', html)
    if csrf_match:
        csrf_token = csrf_match.group(1)
        print(f"CSRF token: {csrf_token[:20]}...")
    else:
        print("CSRF token not found!")
        sys.exit(1)
    
    # Login
    with client.session_transaction() as sess:
        sess['user_id'] = 1
    
    # Submit form with CSRF token
    form_data = {
        'csrf_token': csrf_token,
        'contract_no': 'CA/SHSHYM26032401',
        'company_name': 'Test Company',
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
    
    print("\nSubmitting form with CSRF token...")
    resp = client.post('/contract/2/edit', data=form_data, follow_redirects=True)
    print(f"Response: {resp.status_code}")

with app.app_context():
    contract = Contract.query.get(2)
    print(f"\nPayments after: {len(contract.payment_records)}")
    for p in contract.payment_records:
        print(f"  - ID {p.id}: {p.payment_amount} yuan")
    
    if len(contract.payment_records) >= 2:
        print("\nSUCCESS!")
    else:
        print("\nFAILED!")
