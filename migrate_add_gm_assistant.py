"""
添加总经理助理角色迁移脚本
- 创建 gm_assistant 角色
- 权限：可以查看和修改所有订单，打印对账单，但不能发起订单，看不到发货单

使用方法:
    python migrate_add_gm_assistant.py
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app, db
from app.models import Role, ROLE_PERMISSIONS

app = create_app()


def add_gm_assistant_role():
    """添加总经理助理角色"""
    with app.app_context():
        print("=" * 60)
        print("ALCOEN ERP - 添加总经理助理角色")
        print("=" * 60)
        
        # 检查角色是否已存在
        existing = Role.query.filter_by(code='gm_assistant').first()
        if existing:
            print(f"[INFO] 角色已存在: {existing.name} ({existing.code})")
            # 更新权限
            existing.permissions = str(ROLE_PERMISSIONS['gm_assistant']).replace("'", '"')
            db.session.commit()
            print("[OK] 角色权限已更新")
        else:
            # 创建新角色
            role = Role(
                code='gm_assistant',
                name='总经理助理',
                description='可查看和修改所有订单，打印对账单，不可发起订单，不可见发货单',
                level=70,  # 介于总经理(80)和部门PM(60)之间
                permissions=str(ROLE_PERMISSIONS['gm_assistant']).replace("'", '"')
            )
            db.session.add(role)
            db.session.commit()
            print(f"[OK] 创建角色: {role.name} ({role.code})")
        
        print("\n[OK] 迁移完成!")
        print("=" * 60)


if __name__ == '__main__':
    try:
        add_gm_assistant_role()
    except Exception as e:
        print(f"\n[ERROR] 迁移失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
