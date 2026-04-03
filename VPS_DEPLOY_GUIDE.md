# VPS 部署问题排查指南

## 常见问题及解决方案

### 1. Internal Server Error

#### 原因1: 依赖包版本不一致
**检查:**
```bash
pip list | grep -E "Flask|SQLAlchemy|WTForms"
```

**修复:**
```bash
pip install -r requirements.txt --upgrade
```

#### 原因2: 数据库表结构不一致
**检查:**
```bash
python -c "from app import create_app; app = create_app(); print('DB OK')"
```

**修复:** 运行迁移脚本
```bash
python migrate_v1.0_to_v1.1.py
python migrate_v1.1_to_v1.2.py
python migrate_v1.2_to_v1.3.py
python migrate_v1.3_departments.py
python migrate_v1.4_auth_system.py
python migrate_v1.4_statement_fields.py
python migrate_v1.4_contract_files_table.py
python migrate_v1.5_email_verify.py
```

#### 原因3: 文件权限问题
**修复:**
```bash
chmod -R 755 data/
chmod -R 755 static/uploads/
chmod -R 755 exports/
```

#### 原因4: Python版本不兼容
**检查:**
```bash
python --version  # 需要 >= 3.10
```

### 2. 部署检查清单

在VPS上执行以下检查：

```bash
# 1. 检查Python版本
python3 --version

# 2. 安装依赖
pip3 install -r requirements.txt

# 3. 检查数据库
ls -la data/erp.db

# 4. 检查目录权限
ls -la data/
ls -la static/uploads/

# 5. 测试应用启动
python3 -c "from app import create_app; app = create_app(); print('OK')"

# 6. 运行诊断脚本
python3 diagnose_vps.py
```

### 3. 完整部署步骤

```bash
# 1. 进入项目目录
cd /opt/alcoen_erp_system

# 2. 拉取最新代码
git pull origin main

# 3. 清除缓存
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# 4. 安装/更新依赖
pip3 install -r requirements.txt

# 5. 检查数据库迁移
python3 migrate_v1.5_email_verify.py

# 6. 测试启动
python3 -c "from app import create_app; app = create_app()"

# 7. 重启服务
# 如果使用systemd:
sudo systemctl restart alcoen_erp
# 或者使用screen:
# Ctrl+C 停止旧进程
# screen -S erp
# python3 run.py
```

### 4. 查看错误日志

```bash
# 如果使用systemd
sudo journalctl -u alcoen_erp -f

# 如果使用screen/tmux
# 直接查看终端输出

# 检查Flask日志
ls -la logs/
cat logs/*.log
```

### 5. 关键差异点

| 项目 | 本地开发 | VPS生产 |
|------|---------|---------|
| Python版本 | 3.10+ | 3.10+ |
| 数据库 | SQLite | SQLite |
| DEBUG模式 | True | False |
| 静态文件 | 自动 | 需要配置Nginx |
| 进程管理 | 手动 | systemd/screen |

### 6. 快速修复命令

```bash
# 一键修复常见
#!/bin/bash
cd /opt/alcoen_erp_system

# 清除缓存
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# 更新依赖
pip3 install -r requirements.txt --upgrade

# 检查数据库
python3 -c "
from app import create_app, db
from app.models import User
app = create_app()
with app.app_context():
    print(f'Users: {User.query.count()}')
    print('DB OK')
"

echo "修复完成，请手动重启服务"
```
