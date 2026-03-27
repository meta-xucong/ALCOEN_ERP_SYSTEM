# 📧 ERP系统 - 腾讯企业邮箱配置指南

本文档指导你如何配置腾讯企业邮箱，使ERP系统的验证码邮件功能正常工作。

---

## 🎯 配置方式选择

我们提供两种配置方式，你可以根据需要选择：

| 方式 | 适用场景 | 优点 | 缺点 |
|-----|---------|------|------|
| **方式1: 环境变量** | 生产服务器 | 安全，重启后仍有效 | 需要管理员权限 |
| **方式2: .env 文件** | 开发环境 | 简单，无需重启 | 密码明文存储 |

---

## 🚀 快速配置（推荐）

我们提供了一个交互式配置脚本，可以自动完成所有步骤：

```bash
# 运行配置助手
python email_config_setup.py
```

按照提示输入邮箱账号和密码，脚本会：
1. 测试邮件发送功能
2. 创建配置文件
3. 提供详细的使用说明

---

## 📖 手动配置步骤

### 方式1: 使用环境变量（推荐用于生产环境）

#### 步骤1: 设置环境变量

**Windows (PowerShell 管理员):**
```powershell
[Environment]::SetEnvironmentVariable("MAIL_USERNAME", "你的邮箱@yourcompany.com", "Machine")
[Environment]::SetEnvironmentVariable("MAIL_PASSWORD", "你的邮箱密码", "Machine")
```

**Windows (CMD 管理员):**
```cmd
setx MAIL_USERNAME "你的邮箱@yourcompany.com" /M
setx MAIL_PASSWORD "你的邮箱密码" /M
```

**Linux/Mac:**
```bash
export MAIL_USERNAME="你的邮箱@yourcompany.com"
export MAIL_PASSWORD="你的邮箱密码"
```

#### 步骤2: 重启电脑或终端

环境变量修改后需要重启才能生效。

---

### 方式2: 使用 .env 文件（推荐用于开发环境）

#### 步骤1: 安装 python-dotenv

```bash
pip install python-dotenv
```

#### 步骤2: 创建 .env 文件

在项目根目录创建 `.env` 文件：

```env
# 腾讯企业邮箱配置
MAIL_SERVER=smtp.exmail.qq.com
MAIL_PORT=465
MAIL_USERNAME=你的邮箱@yourcompany.com
MAIL_PASSWORD=你的邮箱密码
MAIL_DEFAULT_SENDER=ERP系统,你的邮箱@yourcompany.com

# 验证码配置
VERIFY_CODE_LENGTH=4
VERIFY_CODE_EXPIRE_MINUTES=15
TRUSTED_DEVICE_DAYS=30
```

#### 步骤3: 修改 app/__init__.py

在文件开头添加：

```python
from dotenv import load_dotenv
import os

# 加载 .env 文件
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
```

---

## 📋 腾讯企业邮箱设置步骤

### 1. 获取邮箱账号

- 登录腾讯企业邮箱管理后台: https://exmail.qq.com/login
- 创建或确认一个发件邮箱，如: `erp@yourcompany.com` 或 `noreply@yourcompany.com`

### 2. 开启 SMTP 服务

腾讯企业邮箱默认开启SMTP服务，无需额外设置。

### 3. 获取密码/授权码

**情况A: 直接使用密码**
- 大多数腾讯企业邮箱可以直接使用登录密码

**情况B: 使用授权码（更安全）**
- 登录邮箱网页版
- 设置 → 客户端设置 → 生成授权码
- 使用授权码代替密码

---

## 🔧 配置参数说明

| 参数 | 说明 | 默认值 |
|-----|------|--------|
| `MAIL_SERVER` | SMTP服务器地址 | smtp.exmail.qq.com |
| `MAIL_PORT` | SMTP端口 | 465 |
| `MAIL_USERNAME` | 发件邮箱账号 | (必填) |
| `MAIL_PASSWORD` | 邮箱密码/授权码 | (必填) |
| `MAIL_DEFAULT_SENDER` | 发件人显示名称 | ERP系统 |
| `VERIFY_CODE_LENGTH` | 验证码位数 | 4 |
| `VERIFY_CODE_EXPIRE_MINUTES` | 验证码有效期(分钟) | 15 |
| `TRUSTED_DEVICE_DAYS` | 信任设备有效期(天) | 30 |

---

## 🧪 测试配置

配置完成后，可以通过以下方式测试：

### 方法1: 使用配置脚本
```bash
python email_config_setup.py
```

### 方法2: 启动ERP系统测试
```bash
python run.py
```

然后：
1. 打开登录页面
2. 输入用户名和密码
3. 检查是否收到验证码邮件

---

## ❗ 常见问题

### Q1: 邮件发送失败，提示认证错误
**A:** 
- 确认邮箱账号和密码正确
- 尝试使用授权码代替密码
- 检查邮箱是否被锁定

### Q2: 邮件发送成功但没收到
**A:**
- 检查垃圾邮件文件夹
- 确认收件邮箱地址正确
- 检查邮件是否被企业邮箱拦截

### Q3: 提示 "邮件服务未配置"
**A:**
- 确认环境变量或 .env 文件已正确配置
- 重启ERP服务
- 检查配置是否被正确加载

### Q4: 腾讯企业邮箱的 SMTP 设置在哪里？
**A:**
腾讯企业邮箱默认开启SMTP，设置如下：
- 服务器: smtp.exmail.qq.com
- 端口: 465 (SSL)
- 账号: 你的完整邮箱地址
- 密码: 邮箱密码或授权码

### Q5: 可以使用其他邮箱吗？
**A:**
可以！修改 `config.py` 中的配置即可：

**Gmail:**
```python
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
```

**QQ邮箱:**
```python
MAIL_SERVER = 'smtp.qq.com'
MAIL_PORT = 465
MAIL_USE_TLS = False
MAIL_USE_SSL = True
# 注意: QQ邮箱需要使用授权码
```

**163邮箱:**
```python
MAIL_SERVER = 'smtp.163.com'
MAIL_PORT = 465
MAIL_USE_TLS = False
MAIL_USE_SSL = True
# 注意: 163邮箱需要使用授权码
```

---

## 🔒 安全建议

1. **生产环境** 使用环境变量，不要提交 .env 文件到代码仓库
2. **定期更换** 邮箱密码或授权码
3. **使用专用邮箱** 建议创建专门的 `noreply@yourcompany.com` 用于系统发件
4. **限制IP** 在腾讯企业邮箱后台设置SMTP发送IP白名单

---

## 📞 需要帮助？

如果配置过程中遇到问题：

1. 检查 `logs/` 目录下的日志文件
2. 确认网络连接和防火墙设置
3. 联系腾讯企业邮箱客服获取支持

---

*文档版本: v1.0*  
*最后更新: 2026-03-20*
