"""
v1.4 账号登录系统迁移脚本
- 创建 users 表和 roles 表
- 初始化默认角色
- 创建默认超级管理员账号

使用方法:
    python migrate_v1.4_auth_system.py
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app, db
from app.models import Role, User, ROLE_PERMISSIONS
from werkzeug.security import generate_password_hash
from datetime import datetime

app = create_app()


def init_auth_system():
    """初始化认证系统"""
    with app.app_context():
        print("=" * 60)
        print("ALCOEN ERP v1.4 - Auth System Initialization")
        print("=" * 60)
        
        # 创建新表
        db.create_all()
        print("[OK] Database tables created")
        
        # 初始化角色
        roles_data = [
            {
                'code': 'superadmin',
                'name': '超级管理员',
                'description': '拥有系统所有权限，可管理用户和角色',
                'level': 100,
                'permissions': '[]'  # 空列表表示拥有所有权限
            },
            {
                'code': 'general_manager',
                'name': '总经理',
                'description': '可查看和编辑所有数据，生成对账单',
                'level': 80,
                'permissions': str(ROLE_PERMISSIONS['general_manager']).replace("'", '"')
            },
            {
                'code': 'department_pm',
                'name': '部门PM',
                'description': '可管理本部门所有数据和合同',
                'level': 60,
                'permissions': str(ROLE_PERMISSIONS['department_pm']).replace("'", '"')
            },
            {
                'code': 'sales_manager',
                'name': '部门销售经理',
                'description': '可查看本部门数据，编辑合同（不含发货记录）',
                'level': 40,
                'permissions': str(ROLE_PERMISSIONS['sales_manager']).replace("'", '"')
            },
            {
                'code': 'logistics_manager',
                'name': '物流经理',
                'description': '可查看所有部门订单，编辑发货记录，资金信息脱敏',
                'level': 20,
                'permissions': str(ROLE_PERMISSIONS['logistics_manager']).replace("'", '"')
            }
        ]
        
        created_roles = []
        for role_data in roles_data:
            existing = Role.query.filter_by(code=role_data['code']).first()
            if not existing:
                role = Role(**role_data)
                db.session.add(role)
                created_roles.append(role_data['name'])
                print(f"[OK] Created role: {role_data['name']} ({role_data['code']})")
            else:
                # 更新现有角色的权限
                existing.permissions = role_data['permissions']
                print(f"[OK] Updated role: {role_data['name']}")
        
        db.session.commit()
        
        # 创建默认超级管理员
        admin_user = User.query.filter_by(username='admin').first()
        
        if not admin_user:
            superadmin_role = Role.query.filter_by(code='superadmin').first()
            
            if not superadmin_role:
                print("✗ 错误：超级管理员角色不存在")
                return
            
            admin = User(
                username='admin',
                password_hash=generate_password_hash('1234.abcd'),
                real_name='系统管理员',
                role_id=superadmin_role.id,
                is_active=True,
                is_superadmin=True,
                require_password_change=True,  # 首次登录需改密码
                created_at=datetime.now()
            )
            db.session.add(admin)
            db.session.commit()
            
            print("\n" + "=" * 60)
            print("[OK] Default superadmin created")
            print("=" * 60)
            print("  Username: admin")
            print("  Password: 1234.abcd")
            print("  [!] Must change password on first login")
            print("=" * 60)
        else:
            # 确保admin是超级管理员
            admin_user.is_superadmin = True
            admin_user.is_active = True
            
            # 如果没有角色，设置为超级管理员
            if not admin_user.role_id:
                superadmin_role = Role.query.filter_by(code='superadmin').first()
                if superadmin_role:
                    admin_user.role_id = superadmin_role.id
            
            db.session.commit()
            print("\n[OK] Admin account exists, permissions updated")
        
        print("\n[OK] Auth system initialization completed!")
        print("=" * 60)


if __name__ == '__main__':
    try:
        init_auth_system()
    except Exception as e:
        print(f"\n[ERROR] Initialization failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
