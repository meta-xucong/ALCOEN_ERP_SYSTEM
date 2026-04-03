#!/bin/bash
# ERP系统诊断脚本 - 在跳板机上执行

echo "=========================================="
echo "ALCOEN ERP VPS 远程诊断"
echo "=========================================="
echo ""

# SSH到目标VPS并执行诊断
ssh -p 2222 -i ~/.ssh/aliyun2_rsa root@47.101.209.149 "bash -s" << 'EOF'

echo "=== 1. 系统信息 ==="
uname -a
echo ""

echo "=== 2. Python版本 ==="
python3 --version
echo ""

echo "=== 3. 项目路径 ==="
find /opt /root /var/www /home -name "run.py" -path "*/alcoen*" 2>/dev/null | head -5
echo ""

# 定位项目目录
PROJECT_DIR=$(find /opt /root /var/www /home -name "run.py" -path "*/alcoen*" 2>/dev/null | head -1 | xargs dirname)
if [ -z "$PROJECT_DIR" ]; then
    echo "未找到项目目录!"
    exit 1
fi

echo "项目目录: $PROJECT_DIR"
cd "$PROJECT_DIR"
echo ""

echo "=== 4. Git状态 ==="
git log --oneline -3 2>/dev/null || echo "Git不可用"
echo ""

echo "=== 5. 依赖包 ==="
pip3 list 2>/dev/null | grep -E "Flask|SQLAlchemy|WTForms|Werkzeug" || pip list 2>/dev/null | grep -E "Flask|SQLAlchemy|WTForms|Werkzeug"
echo ""

echo "=== 6. 数据库检查 ==="
ls -la data/erp.db 2>/dev/null
echo ""

echo "=== 7. 应用测试 ==="
python3 -c "
from app import create_app
from app.models import User, Department, Contract
app = create_app()
with app.app_context():
    print(f'Users: {User.query.count()}')
    print(f'Departments: {Department.query.count()}')
    print(f'Contracts: {Contract.query.count()}')
    print('DB OK')
" 2>&1
echo ""

echo "=== 8. 路由测试 ==="
python3 -c "
from app import create_app
from app.models import User
app = create_app()
client = app.test_client()

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if admin:
        with client.session_transaction() as sess:
            sess['user_id'] = admin.id
        
        routes = ['/department/', '/statement/generator', '/contract/new']
        for route in routes:
            try:
                resp = client.get(route)
                status = 'OK' if resp.status_code == 200 else f'FAIL({resp.status_code})'
                print(f'{route}: {status}')
            except Exception as e:
                print(f'{route}: ERROR - {e}')
    else:
        print('No admin user found')
" 2>&1
echo ""

echo "=== 9. 服务状态 ==="
ps aux | grep -E "python|gunicorn" | grep -v grep | head -5
echo ""

netstat -tlnp 2>/dev/null | grep :8080 || ss -tlnp | grep :8080
echo ""

echo "=== 诊断完成 ==="
EOF
