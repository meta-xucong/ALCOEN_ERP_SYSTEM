#!/usr/bin/env python
"""
ALCOEN QC 系统数据库迁移脚本
创建质量控制系统所需的全部数据表和初始角色数据
"""
import os
import sys
import json
import sqlite3
from datetime import datetime

# 将项目根目录加入路径
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, BASE_DIR)

DB_PATH = os.path.join(BASE_DIR, 'data', 'erp.db')


def table_exists(cursor, table_name: str) -> bool:
    """检查表是否已存在"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def index_exists(cursor, index_name: str) -> bool:
    """检查索引是否已存在"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,)
    )
    return cursor.fetchone() is not None


def role_exists(cursor, role_code: str) -> bool:
    """检查角色是否已存在"""
    cursor.execute(
        "SELECT id FROM roles WHERE code=?",
        (role_code,)
    )
    return cursor.fetchone() is not None


def create_qc_tables(cursor):
    """创建 QC 系统所需的全部数据表"""
    
    # 1. qc_user_bindings
    if not table_exists(cursor, 'qc_user_bindings'):
        cursor.execute("""
            CREATE TABLE qc_user_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                is_active BOOLEAN DEFAULT 0,
                approved_by INTEGER,
                approved_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (role_id) REFERENCES roles(id),
                FOREIGN KEY (approved_by) REFERENCES users(id),
                UNIQUE (user_id)
            )
        """)
        print("[OK] 创建表: qc_user_bindings")
    else:
        print("[SKIP] 表已存在: qc_user_bindings")
    
    # 索引
    for idx, col in [
        ('idx_qc_user_bindings_user', 'user_id'),
        ('idx_qc_user_bindings_role', 'role_id'),
        ('idx_qc_user_bindings_active', 'is_active'),
    ]:
        if not index_exists(cursor, idx):
            cursor.execute(f"CREATE INDEX {idx} ON qc_user_bindings({col})")
            print(f"[OK] 创建索引: {idx}")
    
    # 2. qc_work_orders
    if not table_exists(cursor, 'qc_work_orders'):
        cursor.execute("""
            CREATE TABLE qc_work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_no VARCHAR(100) UNIQUE NOT NULL,
                workpiece_name VARCHAR(200) NOT NULL,
                quantity FLOAT NOT NULL,
                controller_id INTEGER NOT NULL,
                inspector_id INTEGER,
                status VARCHAR(50) DEFAULT 'qc_pending',
                qc_completed_at DATETIME,
                inspection_completed_at DATETIME,
                accepted_at DATETIME,
                rejected_at DATETIME,
                rejection_reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (controller_id) REFERENCES users(id),
                FOREIGN KEY (inspector_id) REFERENCES users(id)
            )
        """)
        print("[OK] 创建表: qc_work_orders")
    else:
        print("[SKIP] 表已存在: qc_work_orders")
    
    for idx, col in [
        ('idx_qcwo_status', 'status'),
        ('idx_qcwo_controller', 'controller_id'),
        ('idx_qcwo_inspector', 'inspector_id'),
        ('idx_qcwo_created', 'created_at'),
    ]:
        if not index_exists(cursor, idx):
            cursor.execute(f"CREATE INDEX {idx} ON qc_work_orders({col})")
            print(f"[OK] 创建索引: {idx}")
    
    # 3. qc_work_order_attachments
    if not table_exists(cursor, 'qc_work_order_attachments'):
        cursor.execute("""
            CREATE TABLE qc_work_order_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER NOT NULL,
                attach_type VARCHAR(50) NOT NULL,
                title VARCHAR(255),
                content TEXT,
                file_path VARCHAR(500) NOT NULL,
                file_type VARCHAR(50),
                is_required BOOLEAN DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (work_order_id) REFERENCES qc_work_orders(id) ON DELETE CASCADE
            )
        """)
        print("[OK] 创建表: qc_work_order_attachments")
    else:
        print("[SKIP] 表已存在: qc_work_order_attachments")
    
    for idx, col in [
        ('idx_qcwoa_work_order', 'work_order_id'),
        ('idx_qcwoa_type', 'attach_type'),
    ]:
        if not index_exists(cursor, idx):
            cursor.execute(f"CREATE INDEX {idx} ON qc_work_order_attachments({col})")
            print(f"[OK] 创建索引: {idx}")
    
    # 4. qc_inspection_records
    if not table_exists(cursor, 'qc_inspection_records'):
        cursor.execute("""
            CREATE TABLE qc_inspection_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER NOT NULL,
                inspector_id INTEGER NOT NULL,
                attachment_id INTEGER NOT NULL,
                result VARCHAR(20) NOT NULL,
                remark TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (work_order_id) REFERENCES qc_work_orders(id) ON DELETE CASCADE,
                FOREIGN KEY (inspector_id) REFERENCES users(id),
                FOREIGN KEY (attachment_id) REFERENCES qc_work_order_attachments(id)
            )
        """)
        print("[OK] 创建表: qc_inspection_records")
    else:
        print("[SKIP] 表已存在: qc_inspection_records")
    
    for idx, col in [
        ('idx_qcir_work_order', 'work_order_id'),
        ('idx_qcir_attachment', 'attachment_id'),
        ('idx_qcir_inspector', 'inspector_id'),
    ]:
        if not index_exists(cursor, idx):
            cursor.execute(f"CREATE INDEX {idx} ON qc_inspection_records({col})")
            print(f"[OK] 创建索引: {idx}")
    
    # 5. qc_acceptance_signatures
    if not table_exists(cursor, 'qc_acceptance_signatures'):
        cursor.execute("""
            CREATE TABLE qc_acceptance_signatures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER NOT NULL,
                signer_id INTEGER NOT NULL,
                signer_role VARCHAR(50) NOT NULL,
                signed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (work_order_id) REFERENCES qc_work_orders(id) ON DELETE CASCADE,
                FOREIGN KEY (signer_id) REFERENCES users(id),
                UNIQUE (work_order_id, signer_role)
            )
        """)
        print("[OK] 创建表: qc_acceptance_signatures")
    else:
        print("[SKIP] 表已存在: qc_acceptance_signatures")
    
    for idx, col in [
        ('idx_qcas_work_order', 'work_order_id'),
    ]:
        if not index_exists(cursor, idx):
            cursor.execute(f"CREATE INDEX {idx} ON qc_acceptance_signatures({col})")
            print(f"[OK] 创建索引: {idx}")


def insert_qc_roles(cursor):
    """插入 QC 专属角色"""
    
    roles_to_insert = [
        {
            'name': '质量控制员',
            'code': 'qc_controller',
            'description': '负责工件订单创建、质控流程发起及验收确认',
            'permissions': json.dumps([
                'qc_dashboard',
                'qc_work_order_view',
                'qc_work_order_create',
                'qc_work_order_edit',
                'qc_work_order_delete',
                'qc_acceptance_perform',
                'qc_acceptance_rollback'
            ]),
            'level': 55,
        },
        {
            'name': '质量检测员',
            'code': 'qc_inspector',
            'description': '负责工件订单各栏目质量检测',
            'permissions': json.dumps([
                'qc_dashboard',
                'qc_work_order_view',
                'qc_inspection_perform'
            ]),
            'level': 45,
        },
    ]
    
    for role in roles_to_insert:
        if not role_exists(cursor, role['code']):
            cursor.execute("""
                INSERT INTO roles (name, code, description, permissions, level, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                role['name'],
                role['code'],
                role['description'],
                role['permissions'],
                role['level'],
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))
            print(f"[OK] 创建角色: {role['code']} ({role['name']})")
        else:
            print(f"[SKIP] 角色已存在: {role['code']}")


def create_upload_directories():
    """创建 QC 文件上传目录"""
    upload_dir = os.path.join(BASE_DIR, 'static', 'uploads', 'qc')
    os.makedirs(upload_dir, exist_ok=True)
    print(f"[OK] 创建/确认目录: {upload_dir}")


def verify_migration(cursor):
    """验证迁移结果"""
    print("\n[验证] 迁移后数据库表清单:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    
    required_tables = [
        'qc_user_bindings',
        'qc_work_orders',
        'qc_work_order_attachments',
        'qc_inspection_records',
        'qc_acceptance_signatures',
    ]
    
    for t in required_tables:
        status = "[OK]" if t in tables else "[FAIL]"
        print(f"  {status} {t}")
    
    print("\n[验证] 迁移后 QC 角色清单:")
    cursor.execute("SELECT code, name, level FROM roles WHERE code IN ('qc_controller', 'qc_inspector')")
    for row in cursor.fetchall():
        print(f"  [OK] {row[0]} ({row[1]}, level={row[2]})")


def main():
    print("=" * 60)
    print("ALCOEN QC 系统数据库迁移脚本")
    print("=" * 60)
    print(f"数据库路径: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print(f"[ERROR] 数据库文件不存在: {DB_PATH}")
        sys.exit(1)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        create_qc_tables(cursor)
        insert_qc_roles(cursor)
        create_upload_directories()
        conn.commit()
        verify_migration(cursor)
        print("\n[SUCCESS] 数据库迁移完成！")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
