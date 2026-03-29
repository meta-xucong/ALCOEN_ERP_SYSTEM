# ERP 系统部署运维手册

> 版本: v1.0  
> 最后更新: 2026-03-27  
> 适用环境: Linux (Alibaba Cloud Linux 3 / CentOS 8 / Ubuntu 20.04+)

---

## 📋 目录

1. [部署前准备](#部署前准备)
2. [标准部署流程](#标准部署流程)
3. [数据库迁移规范](#数据库迁移规范)
4. [常见问题排查](#常见问题排查)
5. [依赖管理](#依赖管理)
6. [回滚方案](#回滚方案)

---

## 部署前准备

### 1. 环境检查清单

```bash
# Python 版本（必须 >= 3.10）
python3 --version  # 期望: Python 3.10+

# 数据库备份位置
ls -la data/erp.db

# 静态文件完整性
ls -la static/uploads/

# 配置文件
ls -la config.py
```

### 2. 必备备份（每次部署前必须执行）

```bash
#!/bin/bash
# backup.sh - 部署前备份脚本

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/pre_deploy_${TIMESTAMP}"

mkdir -p "$BACKUP_DIR"

# 备份数据库
cp data/erp.db "$BACKUP_DIR/erp.db"

# 备份配置
cp config.py "$BACKUP_DIR/config.py"

# 备份上传文件
cp -r static/uploads "$BACKUP_DIR/uploads"

# 备份当前代码（可选）
git rev-parse HEAD > "$BACKUP_DIR/git_commit.txt"

echo "备份完成: $BACKUP_DIR"
```

---

## 标准部署流程

### 步骤 1: 停止服务

```bash
# 如果使用 systemd
sudo systemctl stop alcoen-erp

# 或者手动停止
pkill -f "gunicorn.*wsgi:app"
```

### 步骤 2: 拉取最新代码

```bash
# 方式 A: 直接拉取（需要 GitHub 访问）
git pull origin main

# 方式 B: 通过中转服务器（推荐，避免网络问题）
# 在可访问 GitHub 的机器上:
git clone --depth 1 https://github.com/meta-xucong/ALCOEN_ERP_SYSTEM.git /tmp/erp_new
scp -r /tmp/erp_new/* user@server:/opt/alcoen-erp/ALCOEN_ERP_SYSTEM/
```

### 步骤 3: 对比数据库 Schema（关键！）

```bash
# 导出当前数据库结构
sqlite3 data/erp.db ".schema" > /tmp/current_schema.sql

# 对比新旧 models.py 的差异
diff /tmp/current_schema.sql app/models.py

# 或使用 Python 检查
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from app import create_app, db
from app.models import *

app = create_app()
with app.app_context():
    # 检查每个模型对应的表是否存在
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    
    tables = ['users', 'departments', 'managers', 'contracts', 'products', 
              'transactions', 'statements', 'payment_records']
    
    for table in tables:
        if inspector.has_table(table):
            columns = [col['name'] for col in inspector.get_columns(table)]
            print(f"✅ {table}: {', '.join(columns[:5])}...")
        else:
            print(f"❌ {table}: 表不存在！")
EOF
```

### 步骤 4: 执行数据库迁移

**如果 models.py 有变更，必须执行迁移！**

```bash
# 检查是否有未应用的迁移脚本
ls migrate_*.py 2>/dev/null

# 执行迁移（如果有）
python3 migrate_xxx.py

# 或者手动执行 SQL
sqlite3 data/erp.db < "ALTER TABLE xxx ADD COLUMN yyy TEXT;"
```

### 步骤 5: 更新依赖

```bash
# 激活虚拟环境
source venv/bin/activate

# 更新 pip
pip install --upgrade pip

# 安装/更新依赖
pip install -r requirements.txt

# 检查是否有遗漏的依赖（常见遗漏）
pip install Flask-Login Pillow
```

### 步骤 6: 启动服务

```bash
# 方式 A: systemd（推荐）
sudo systemctl start alcoen-erp
sudo systemctl enable alcoen-erp

# 方式 B: 手动启动
gunicorn \
    --bind 127.0.0.1:8080 \
    --workers 4 \
    --timeout 120 \
    --access-logfile /var/log/alcoen-erp/access.log \
    --error-logfile /var/log/alcoen-erp/error.log \
    --daemon \
    wsgi:app
```

### 步骤 7: 验证

```bash
# 检查服务状态
curl -s http://127.0.0.1:8080/auth/login | head -5

# 检查进程
pgrep -c -f "gunicorn.*wsgi:app"

# 查看错误日志
tail -20 /var/log/alcoen-erp/error.log
```

---

## 数据库迁移规范

### 何时需要迁移

- [ ] 新增 Model 类
- [ ] 删除 Model 类
- [ ] 添加/删除字段
- [ ] 修改字段类型
- [ ] 添加/删除索引

### 迁移脚本模板

```python
#!/usr/bin/env python3
"""
迁移脚本: migrate_vx.x_xxx.py
描述: 简要说明变更内容
日期: YYYY-MM-DD
"""

import sys
import sqlite3
sys.path.insert(0, '/opt/alcoen-erp/ALCOEN_ERP_SYSTEM')

DB_PATH = '/opt/alcoen-erp/ALCOEN_ERP_SYSTEM/data/erp.db'

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 检查列/表是否存在
    cursor.execute("PRAGMA table_info(managers)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'name' not in columns:
        print("添加 name 列...")
        cursor.execute("ALTER TABLE managers ADD COLUMN name TEXT DEFAULT '未命名'")
        conn.commit()
        print("✅ 迁移完成")
    else:
        print("列已存在，跳过")
    
    conn.close()

if __name__ == '__main__':
    migrate()
```

### 使用 Flask-Migrate（推荐长期方案）

```bash
# 安装
pip install Flask-Migrate

# 初始化
flask db init

# 生成迁移脚本
flask db migrate -m "add name column to managers"

# 执行迁移
flask db upgrade
```

---

## 常见问题排查

### 问题 1: 500 Internal Server Error

**可能原因:**
- 数据库 schema 不匹配
- 缺少依赖
- 代码错误

**排查步骤:**

```bash
# 1. 查看错误日志
tail -50 /var/log/alcoen-erp/error.log

# 2. 前台运行查看详细错误
pkill -f gunicorn
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from app import create_app
app = create_app()
app.run(debug=True, port=8080)
EOF
```

### 问题 2: 端口冲突 (Address already in use)

```bash
# 查找占用 8080 的进程
lsof -i :8080
ss -tlnp | grep 8080

# 清理所有 gunicorn
pkill -9 -f gunicorn

# 使用 systemd 统一管理，避免手动启动冲突
sudo systemctl restart alcoen-erp
```

### 问题 3: 数据库锁定 (database is locked)

```bash
# 检查是否有其他进程占用
lsof data/erp.db

# 重启服务
sudo systemctl restart alcoen-erp
```

### 问题 4: 静态文件 404

```bash
# 检查文件是否存在
ls -la static/uploads/

# 检查 Nginx 配置
nginx -t
cat /etc/nginx/conf.d/alcoen-erp.conf
```

---

## 依赖管理

### requirements.txt 规范

```txt
# Core dependencies
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-WTF==1.2.1
Flask-Login==0.6.3          # 容易遗漏！
WTForms==3.1.1
Werkzeug==3.0.1

# Excel export
openpyxl==3.1.2

# Image processing
Pillow==10.1.0              # 容易遗漏！

# Date utilities
python-dateutil==2.8.2

# Production server
gunicorn==21.2.0

# Database migrations (推荐添加)
# Flask-Migrate==4.0.5

# Environment variables (可选)
# python-dotenv==1.0.0
```

### 检查缺失依赖

```bash
python3 << 'EOF'
import sys

packages = [
    ('flask', 'Flask'),
    ('flask_sqlalchemy', 'Flask-SQLAlchemy'),
    ('flask_wtf', 'Flask-WTF'),
    ('flask_login', 'Flask-Login'),
    ('wtforms', 'WTForms'),
    ('werkzeug', 'Werkzeug'),
    ('openpyxl', 'openpyxl'),
    ('PIL', 'Pillow'),
    ('dateutil', 'python-dateutil'),
]

for mod, pkg in packages:
    try:
        __import__(mod)
        print(f'✅ {pkg}')
    except ImportError:
        print(f'❌ {pkg} - 需要安装')
EOF
```

---

## 回滚方案

### 快速回滚脚本

```bash
#!/bin/bash
# rollback.sh

if [ -z "$1" ]; then
    echo "用法: ./rollback.sh <备份目录>"
    echo "例如: ./rollback.sh backups/pre_deploy_20260327_161639"
    exit 1
fi

BACKUP_DIR="$1"

echo "开始回滚..."

# 停止服务
sudo systemctl stop alcoen-erp

# 恢复数据库
cp "$BACKUP_DIR/erp.db" data/erp.db

# 恢复配置
cp "$BACKUP_DIR/config.py" config.py

# 恢复上传文件（可选）
# cp -r "$BACKUP_DIR/uploads" static/uploads

# 恢复代码（如果需要）
# git checkout $(cat "$BACKUP_DIR/git_commit.txt")

# 启动服务
sudo systemctl start alcoen-erp

echo "✅ 回滚完成"
```

---

## 附录

### systemd 服务配置

```ini
# /etc/systemd/system/alcoen-erp.service
[Unit]
Description=ALCOEN ERP System
After=network.target

[Service]
Type=exec
User=root
WorkingDirectory=/opt/alcoen-erp/ALCOEN_ERP_SYSTEM
ExecStart=/opt/alcoen-erp/ALCOEN_ERP_SYSTEM/venv/bin/gunicorn \
    --bind 127.0.0.1:8080 \
    --workers 4 \
    --worker-class sync \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile /var/log/alcoen-erp/access.log \
    --error-logfile /var/log/alcoen-erp/error.log \
    --capture-output \
    wsgi:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 常用命令速查

| 操作 | 命令 |
|------|------|
| 查看服务状态 | `sudo systemctl status alcoen-erp` |
| 查看日志 | `sudo journalctl -u alcoen-erp -f` |
| 重启服务 | `sudo systemctl restart alcoen-erp` |
| 查看错误 | `tail -f /var/log/alcoen-erp/error.log` |
| 查看进程 | `pgrep -fa gunicorn` |
| 数据库操作 | `sqlite3 data/erp.db` |

---

## 更新记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-03-27 | v1.0 | 初始版本，总结阿里云2部署经验教训 |

---

**维护者**: meta-xucong  
**如有问题**: 联系技术支持或提交 Issue
