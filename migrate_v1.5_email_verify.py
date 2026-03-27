#!/usr/bin/env python3
"""
数据库迁移脚本 v1.4 -> v1.5
添加邮箱验证码系统所需的数据表
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from sqlalchemy import text


def migrate():
    """执行数据库迁移"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("ERP系统数据库迁移 v1.4 -> v1.5")
        print("功能: 添加邮箱验证码系统")
        print("=" * 60)
        
        # 检查表是否已存在
        with db.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_codes'"
            ))
            if result.fetchone():
                print("[INFO] verification_codes 表已存在，跳过创建")
            else:
                print("[1/2] 创建 verification_codes 表...")
                conn.execute(text("""
                    CREATE TABLE verification_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        code VARCHAR(10) NOT NULL,
                        purpose VARCHAR(20) DEFAULT 'login',
                        device_fingerprint VARCHAR(64),
                        ip_address VARCHAR(50),
                        used_at DATETIME,
                        expires_at DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                """))
                
                # 创建索引
                conn.execute(text(
                    "CREATE INDEX idx_verification_codes_user_id ON verification_codes(user_id)"
                ))
                print("[OK] verification_codes 表创建成功")
            
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trusted_devices'"
            ))
            if result.fetchone():
                print("[INFO] trusted_devices 表已存在，跳过创建")
            else:
                print("[2/2] 创建 trusted_devices 表...")
                conn.execute(text("""
                    CREATE TABLE trusted_devices (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        device_fingerprint VARCHAR(64) NOT NULL,
                        device_name VARCHAR(100),
                        ip_address VARCHAR(50),
                        last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        expires_at DATETIME NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                """))
                
                # 创建索引
                conn.execute(text(
                    "CREATE INDEX idx_trusted_devices_user_id ON trusted_devices(user_id)"
                ))
                conn.execute(text(
                    "CREATE INDEX idx_trusted_devices_fingerprint ON trusted_devices(device_fingerprint)"
                ))
                print("[OK] trusted_devices 表创建成功")
            
            conn.commit()
        
        print("=" * 60)
        print("[SUCCESS] 数据库迁移完成！")
        print("=" * 60)
        print("\n下一步操作：")
        print("1. 配置邮件服务器信息（在环境变量或 config.py 中）：")
        print("   - MAIL_USERNAME: 发件邮箱地址")
        print("   - MAIL_PASSWORD: 邮箱密码或授权码")
        print("\n2. 重启 ERP 服务")
        print("\n3. 已注册用户需要补充邮箱才能使用新设备登录")
        print("=" * 60)


if __name__ == '__main__':
    migrate()
