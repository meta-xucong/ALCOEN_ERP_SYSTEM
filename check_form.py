from app import create_app
import re

app = create_app()
with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 1
    
    resp = client.get('/contract/2/edit')
    html = resp.data.decode('utf-8')
    
    # 查找所有 payment 相关字段
    matches = re.findall(r'name="(payment_[^"]+)"', html)
    print('Payment fields in HTML:')
    for m in sorted(set(matches)):
        print(f'  {m}')
    
    # 查找 payment_count
    if 'id="payment_count"' in html:
        print('\npayment_count input found')
        # 提取 value
        val_match = re.search(r'id="payment_count"[^>]*value="(\d+)"', html)
        if val_match:
            print(f'  Initial value: {val_match.group(1)}')
    
    # 查找 addPaymentRow
    if 'onclick="addPaymentRow()"' in html:
        print('\nAdd payment button found')
