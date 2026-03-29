"""
数据库迁移脚本：v1.5 删除部门负责人表
- 移除 Manager 表
- 部门不再预设负责人，由PM在创建合同时指定
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text

def migrate():
    """执行迁移"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("ERP System Migration: v1.5 - Remove Manager Table")
        print("=" * 60)
        
        try:
            # 检查 managers 表是否存在
            result = db.session.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='managers'"
            )).fetchone()
            
            if result:
                print("\n1. Dropping managers table...")
                db.session.execute(text("DROP TABLE IF EXISTS managers"))
                print("   [OK] managers table dropped")
            else:
                print("\n1. managers table does not exist, skipping")
            
            # 检查 contracts 表结构
            print("\n2. Checking contracts table structure...")
            result = db.session.execute(text(
                "PRAGMA table_info(contracts)"
            )).fetchall()
            columns = [col[1] for col in result]
            
            if 'manager' in columns:
                print("   [OK] contracts.manager field exists (kept as text field)")
            else:
                print("   [!] contracts.manager field does not exist")
            
            if 'department' in columns:
                print("   [OK] contracts.department field exists")
            else:
                print("   [!] contracts.department field does not exist")
            
            db.session.commit()
            print("\n" + "=" * 60)
            print("Migration completed successfully!")
            print("=" * 60)
            print("\nNotes:")
            print("- Manager table has been removed")
            print("- Departments no longer have preset managers")
            print("- PMs default to themselves as manager when creating contracts,")
            print("  but can select other department members")
            print("- Historical contract manager info is preserved in contracts.manager")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] Migration failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    return True

if __name__ == '__main__':
    success = migrate()
    sys.exit(0 if success else 1)
