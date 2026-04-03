#!/bin/bash
# VPS环境检查脚本

echo "=========================================="
echo "ALCOEN ERP VPS 环境检查"
echo "=========================================="
echo ""

cd /opt/alcoen_erp_system 2>/dev/null || cd ~/alcoen_erp_system 2>/dev/null || cd .

echo "1. Python版本:"
python3 --version
echo ""

echo "2. 关键依赖包:"
pip3 list | grep -E "Flask|SQLAlchemy|WTForms|Werkzeug"
echo ""

echo "3. 数据库文件:"
ls -lh data/erp.db 2>/dev/null || echo "数据库文件不存在!"
echo ""

echo "4. 目录权限:"
ls -ld data/ static/uploads/ exports/ 2>/dev/null
echo ""

echo "5. 测试应用导入:"
python3 -c "from app import create_app; print('App import: OK')" 2>&1
echo ""

echo "6. 测试数据库查询:"
python3 -c "
from app import create_app
from app.models import User, Department, Contract
app = create_app()
with app.app_context():
    print(f'Users: {User.query.count()}')
    print(f'Departments: {Department.query.count()}')
    print(f'Contracts: {Contract.query.count()}')
" 2>&1
echo ""

echo "=========================================="
echo "检查完成"
echo "=========================================="
