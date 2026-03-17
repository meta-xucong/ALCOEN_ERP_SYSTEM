#!/usr/bin/env python
"""
[v1.4] 修复物流经理权限 - 移除查看对账单权限
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Role, ROLE_PERMISSIONS
import json

def fix_logistics_permissions():
    """修复物流经理权限"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("修复物流经理权限")
        print("=" * 60)
        
        # 从 ROLE_PERMISSIONS 获取正确的权限配置
        correct_perms = ROLE_PERMISSIONS.get('logistics_manager', [])
        
        # 查找物流经理角色
        role = Role.query.filter_by(code='logistics_manager').first()
        
        if not role:
            print("❌ 未找到 logistics_manager 角色")
            return
        
        print(f"\n角色: {role.name} ({role.code})")
        print(f"\n原权限: {role.permissions}")
        
        # 更新权限
        old_perms = json.loads(role.permissions) if role.permissions else []
        new_perms = correct_perms
        
        role.permissions = json.dumps(new_perms)
        db.session.commit()
        
        print(f"\n新权限: {role.permissions}")
        
        # 检查差异
        removed = set(old_perms) - set(new_perms)
        added = set(new_perms) - set(old_perms)
        
        if removed:
            print(f"\n✅ 已移除权限: {removed}")
        if added:
            print(f"\n✅ 已添加权限: {added}")
        
        print("\n" + "=" * 60)
        print("修复完成！")
        print("=" * 60)

if __name__ == '__main__':
    fix_logistics_permissions()
