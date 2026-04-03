#!/usr/bin/env python
"""检查合同数据"""
from app import create_app
from app.models import Contract

app = create_app()

with app.app_context():
    contract = Contract.query.get(2)
    print(f'Contract: {contract.contract_no}')
    print(f'Products: {len(contract.contract_products)}')
    print(f'Transactions: {len(contract.transactions)}')
    print(f'Payments: {len(contract.payment_records)}')
    
    print()
    print('=== JavaScript Arrays ===')
    
    print()
    print('// existingProducts')
    print('const existingProducts = [')
    for cp in contract.contract_products:
        print(f"    {{product_code: '{cp.product_code}', quantity: {cp.quantity}}},")
    print('];')
    
    print()
    print('// existingTransactions')
    print('const existingTransactions = [')
    for t in contract.transactions:
        print(f"    {{id: {t.id}, product_code: '{t.product_code}', quantity: {t.quantity}}},")
    print('];')
    
    print()
    print('// existingPayments')
    print('const existingPayments = [')
    for p in contract.payment_records:
        print(f"    {{id: {p.id}, payment_amount: {p.payment_amount}}},")
    print('];')
