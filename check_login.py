# -*- coding: utf-8 -*-
import requests
import re

# 获取登录页面
resp = requests.get('http://localhost:8080/auth/login', timeout=10)
print('Status:', resp.status_code)
html = resp.text

print('\n=== Checking Login Page ===')
print('Has verify_code:', 'verify_code' in html)
print('Has email:', 'email' in html.lower())
print('Has 验证码:', '验证码' in html)
print('Has 邮箱:', '邮箱' in html)

# 检查表单字段
print('\n=== Form Fields ===')
inputs = re.findall(r'<input[^>]*name="([^"]+)"', html)
for inp in inputs:
    print('  -', inp)

# 检查是否有验证码相关链接或页面
print('\n=== Routes Check ===')
routes = ['/auth/verify-code', '/auth/login', '/auth/register']
for route in routes:
    r = requests.get(f'http://localhost:8080{route}', allow_redirects=True, timeout=5)
    print(f'  {route}: {r.status_code}')
