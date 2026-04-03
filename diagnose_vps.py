#!/usr/bin/env python3
"""
VPS环境诊断脚本 - 检查可能导致Internal Server Error的问题
"""
import sys
import os
import platform
import sqlite3

def check_python_version():
    """检查Python版本"""
    print("=" * 60)
    print("1. Python版本检查")
    print("=" * 60)
    print(f"Python版本: {platform.python_version()}")
    print(f"Python路径: {sys.executable}")
    print(f"平台: {platform.platform()}")
    
    # 检查Python版本兼容性
    version = tuple(map(int, platform.python_version().split('.')[:2]))
    if version < (3, 10):
        print("[WARN] 警告: Python版本低于3.10，可能存在兼容性问题")
    else:
        print("[OK] Python版本符合要求")
    print()

def check_dependencies():
    """检查依赖包版本"""
    print("=" * 60)
    print("2. 依赖包版本检查")
    print("=" * 60)
    
    required_packages = {
        'flask': '2.0.0',
        'flask_sqlalchemy': '3.0.0',
        'sqlalchemy': '2.0.0',
        'wtforms': '3.0.0',
        'flask_wtf': '1.1.0',
        'werkzeug': '2.3.0',
    }
    
    issues = []
    for package, min_version in required_packages.items():
        try:
            module = __import__(package)
            version = getattr(module, '__version__', 'unknown')
            print(f"  {package}: {version} (需要 >= {min_version})")
            
            # 简单版本比较
            if version != 'unknown':
                current = tuple(map(int, version.split('.')[:2]))
                required = tuple(map(int, min_version.split('.')[:2]))
                if current < required:
                    issues.append(f"{package}版本过低: {version} < {min_version}")
        except ImportError:
            print(f"  {package}: [FAIL] 未安装")
            issues.append(f"{package}未安装")
    
    if issues:
        print("\n[WARN] 依赖问题:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n[OK] 所有依赖包检查通过")
    print()

def check_database():
    """检查数据库"""
    print("=" * 60)
    print("3. 数据库检查")
    print("=" * 60)
    
    db_path = os.path.join('data', 'erp.db')
    if not os.path.exists(db_path):
        print(f"[FAIL] 数据库文件不存在: {db_path}")
        print()
        return
    
    print(f"数据库路径: {db_path}")
    print(f"数据库大小: {os.path.getsize(db_path)} bytes")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        print(f"\n数据库表 ({len(tables)}个):")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"  - {table[0]}: {count} 条记录")
        
        # 检查关键表结构
        print("\n关键表结构检查:")
        critical_tables = ['users', 'products', 'contracts', 'departments', 'roles']
        for table in critical_tables:
            try:
                cursor.execute(f"PRAGMA table_info({table})")
                columns = cursor.fetchall()
                print(f"  [OK] {table}: {len(columns)} 列")
            except Exception as e:
                print(f"  [FAIL] {table}: {e}")
        
        conn.close()
        print("\n[OK] 数据库检查完成")
    except Exception as e:
        print(f"\n[FAIL] 数据库检查失败: {e}")
    print()

def check_file_permissions():
    """检查文件权限"""
    print("=" * 60)
    print("4. 文件权限检查")
    print("=" * 60)
    
    paths_to_check = [
        'data',
        'data/erp.db',
        'static/uploads',
        'exports',
        'app',
        'templates',
    ]
    
    for path in paths_to_check:
        if os.path.exists(path):
            readable = os.access(path, os.R_OK)
            writable = os.access(path, os.W_OK)
            status = "[OK]" if readable else "[FAIL]"
            perm = f"读{'写' if writable else ''}" if readable else "无权限"
            print(f"  {status} {path}: {perm}")
        else:
            print(f"  [WARN] {path}: 不存在")
    print()

def check_environment():
    """检查环境变量"""
    print("=" * 60)
    print("5. 环境变量检查")
    print("=" * 60)
    
    important_vars = [
        'FLASK_ENV',
        'FLASK_APP',
        'SECRET_KEY',
        'DATABASE_URL',
    ]
    
    for var in important_vars:
        value = os.environ.get(var)
        if value:
            # 隐藏敏感信息
            if 'SECRET' in var or 'KEY' in var or 'PASSWORD' in var:
                display = value[:5] + '*****' if len(value) > 5 else '*****'
            else:
                display = value
            print(f"  [OK] {var}: {display}")
        else:
            print(f"  [WARN] {var}: 未设置")
    print()

def test_application():
    """测试应用启动"""
    print("=" * 60)
    print("6. 应用启动测试")
    print("=" * 60)
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app import create_app
        
        print("  导入应用: [OK]")
        
        app = create_app()
        print("  创建应用: [OK]")
        
        with app.app_context():
            from app.models import db, User, Department, Contract
            
            # 测试数据库查询
            try:
                user_count = User.query.count()
                print(f"  用户表查询: [OK] ({user_count} 用户)")
            except Exception as e:
                print(f"  用户表查询: [FAIL] {e}")
            
            try:
                dept_count = Department.query.count()
                print(f"  部门表查询: [OK] ({dept_count} 部门)")
            except Exception as e:
                print(f"  部门表查询: [FAIL] {e}")
            
            try:
                contract_count = Contract.query.count()
                print(f"  合同表查询: [OK] ({contract_count} 合同)")
            except Exception as e:
                print(f"  合同表查询: [FAIL] {e}")
        
        print("\n[OK] 应用启动测试通过")
    except Exception as e:
        print(f"\n[FAIL] 应用启动失败: {e}")
        import traceback
        traceback.print_exc()
    print()

def check_routes():
    """测试关键路由"""
    print("=" * 60)
    print("7. 关键路由测试")
    print("=" * 60)
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app import create_app
        from app.models import User
        
        app = create_app()
        client = app.test_client()
        
        with app.app_context():
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                print("  [FAIL] 未找到admin用户，无法测试")
                return
            
            with client.session_transaction() as sess:
                sess['user_id'] = admin.id
            
            routes = [
                '/department/',
                '/statement/generator',
                '/contract/new',
                '/contract/',
                '/product/',
            ]
            
            for route in routes:
                try:
                    resp = client.get(route)
                    status = "[OK]" if resp.status_code == 200 else "[FAIL]"
                    print(f"  {status} {route}: {resp.status_code}")
                except Exception as e:
                    print(f"  [FAIL] {route}: {e}")
        
        print("\n[OK] 路由测试完成")
    except Exception as e:
        print(f"\n[FAIL] 路由测试失败: {e}")
        import traceback
        traceback.print_exc()
    print()

if __name__ == '__main__':
    print("\n")
    print("*" * 60)
    print("*" + " " * 58 + "*")
    print("*" + "   ALCOEN ERP VPS 环境诊断工具".center(52) + "*")
    print("*" + " " * 58 + "*")
    print("*" * 60)
    print("\n")
    
    check_python_version()
    check_dependencies()
    check_database()
    check_file_permissions()
    check_environment()
    test_application()
    check_routes()
    
    print("=" * 60)
    print("诊断完成")
    print("=" * 60)
    print("\n如发现问题，请根据上述检查项修复后重试。\n")
