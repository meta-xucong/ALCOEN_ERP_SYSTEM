#!/usr/bin/env python3
"""
腾讯企业邮箱配置助手
帮助用户快速配置邮件服务
"""
import os
import sys
import getpass


def print_header():
    """打印标题"""
    print("=" * 60)
    print("   ERP系统 - 腾讯企业邮箱配置助手")
    print("=" * 60)
    print()


def print_guide():
    """打印配置指南"""
    print("📋 腾讯企业邮箱配置步骤：")
    print("-" * 60)
    print()
    print("1️⃣  登录腾讯企业邮箱管理后台")
    print("    网址: https://exmail.qq.com/login")
    print()
    print("2️⃣  获取邮箱账号")
    print("    例如: erp@yourcompany.com")
    print("    或: noreply@yourcompany.com")
    print()
    print("3️⃣  获取邮箱密码/授权码")
    print("    方式A: 直接使用邮箱登录密码")
    print("    方式B: 开启安全登录后使用授权码（推荐）")
    print()
    print("4️⃣  确认SMTP服务器信息")
    print("    服务器: smtp.exmail.qq.com")
    print("    端口: 465 (SSL)")
    print()
    print("=" * 60)
    print()


def test_email_config(username, password, test_recipient=None):
    """测试邮件配置"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    print("\n🧪 正在测试邮件配置...")
    print("-" * 40)
    
    try:
        # 创建测试邮件
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'ERP系统 - 邮件配置测试'
        msg['From'] = f'ERP系统 <{username}>'
        
        # 如果没有指定收件人，就发给自己
        recipient = test_recipient or username
        msg['To'] = recipient
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #1e3a5f;">✅ 邮件配置测试成功！</h2>
            <p>您的ERP系统邮件服务已正确配置。</p>
            <p>发送时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <hr>
            <p style="color: #666; font-size: 12px;">此邮件由ERP系统自动发送</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        
        # 连接SMTP服务器
        print(f"  正在连接 smtp.exmail.qq.com:465...")
        server = smtplib.SMTP_SSL('smtp.exmail.qq.com', 465, timeout=10)
        
        print(f"  正在登录 {username}...")
        server.login(username, password)
        
        print(f"  正在发送测试邮件到 {recipient}...")
        server.sendmail(username, recipient, msg.as_string())
        
        server.quit()
        
        print("-" * 40)
        print("✅ 邮件发送成功！")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print("-" * 40)
        print(f"❌ 登录失败: {e}")
        print("\n💡 可能的原因：")
        print("   - 邮箱账号或密码错误")
        print("   - 需要使用授权码而不是登录密码")
        print("   - 邮箱未开启SMTP服务")
        return False
        
    except Exception as e:
        print("-" * 40)
        print(f"❌ 发送失败: {e}")
        return False


def create_env_file(config):
    """创建环境变量文件"""
    env_content = f"""# ERP系统 - 腾讯企业邮箱配置
# 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# 邮件服务器配置
MAIL_SERVER=smtp.exmail.qq.com
MAIL_PORT=465
MAIL_USERNAME={config['username']}
MAIL_PASSWORD={config['password']}
MAIL_DEFAULT_SENDER=ERP系统,{config['username']}

# 验证码配置
VERIFY_CODE_LENGTH=4
VERIFY_CODE_EXPIRE_MINUTES=15
TRUSTED_DEVICE_DAYS=30
"""
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    return env_path


def create_batch_file(config):
    """创建Windows批处理文件"""
    batch_content = f"""@echo off
REM ERP系统 - 环境变量配置脚本
REM 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

echo 正在配置ERP系统环境变量...

setx MAIL_SERVER "smtp.exmail.qq.com" /M
setx MAIL_PORT "465" /M
setx MAIL_USERNAME "{config['username']}" /M
setx MAIL_PASSWORD "{config['password']}" /M
setx MAIL_DEFAULT_SENDER "ERP系统,{config['username']}" /M

echo.
echo 环境变量配置完成！
echo 请重新打开命令行窗口或重启电脑使配置生效。
pause
"""
    
    batch_path = os.path.join(os.path.dirname(__file__), 'set_email_env.bat')
    
    with open(batch_path, 'w', encoding='utf-8') as f:
        f.write(batch_content)
    
    return batch_path


def create_powershell_file(config):
    """创建PowerShell脚本文件"""
    ps_content = f"""# ERP系统 - 环境变量配置脚本
# 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Write-Host "正在配置ERP系统环境变量..." -ForegroundColor Green

[Environment]::SetEnvironmentVariable("MAIL_SERVER", "smtp.exmail.qq.com", "Machine")
[Environment]::SetEnvironmentVariable("MAIL_PORT", "465", "Machine")
[Environment]::SetEnvironmentVariable("MAIL_USERNAME", "{config['username']}", "Machine")
[Environment]::SetEnvironmentVariable("MAIL_PASSWORD", "{config['password']}", "Machine")
[Environment]::SetEnvironmentVariable("MAIL_DEFAULT_SENDER", "ERP系统,{config['username']}", "Machine")

Write-Host ""
Write-Host "环境变量配置完成！" -ForegroundColor Green
Write-Host "请重新打开PowerShell窗口或重启电脑使配置生效。" -ForegroundColor Yellow
pause
"""
    
    ps_path = os.path.join(os.path.dirname(__file__), 'set_email_env.ps1')
    
    with open(ps_path, 'w', encoding='utf-8') as f:
        f.write(ps_content)
    
    return ps_path


def main():
    """主函数"""
    print_header()
    print_guide()
    
    config = {}
    
    # 获取配置信息
    print("🔧 请输入腾讯企业邮箱配置信息：")
    print("-" * 60)
    
    config['username'] = input("  邮箱账号 (如: erp@yourcompany.com): ").strip()
    
    if not config['username']:
        print("\n❌ 邮箱账号不能为空！")
        return 1
    
    # 使用 getpass 隐藏密码输入
    config['password'] = getpass.getpass("  邮箱密码/授权码: ").strip()
    
    if not config['password']:
        print("\n❌ 密码不能为空！")
        return 1
    
    print()
    
    # 测试配置
    test_recipient = input("  测试收件邮箱 (直接回车则发送到配置邮箱): ").strip()
    
    if test_email_config(config['username'], config['password'], test_recipient or None):
        print()
        print("=" * 60)
        print("✅ 配置验证成功！")
        print("=" * 60)
        print()
        
        # 询问是否创建配置文件
        print("📦 创建配置文件：")
        print()
        
        create_files = []
        
        choice = input("  创建 .env 文件? (y/n): ").strip().lower()
        if choice in ('y', 'yes', '是'):
            env_path = create_env_file(config)
            print(f"     ✅ 已创建: {env_path}")
            create_files.append('.env')
        
        choice = input("  创建 Windows批处理脚本 (set_email_env.bat)? (y/n): ").strip().lower()
        if choice in ('y', 'yes', '是'):
            batch_path = create_batch_file(config)
            print(f"     ✅ 已创建: {batch_path}")
            create_files.append('set_email_env.bat')
        
        choice = input("  创建 PowerShell脚本 (set_email_env.ps1)? (y/n): ").strip().lower()
        if choice in ('y', 'yes', '是'):
            ps_path = create_powershell_file(config)
            print(f"     ✅ 已创建: {ps_path}")
            create_files.append('set_email_env.ps1')
        
        print()
        print("=" * 60)
        print("📖 使用说明：")
        print("=" * 60)
        
        if '.env' in create_files:
            print()
            print("方式1 - 使用 .env 文件（推荐开发环境）：")
            print("  1. 安装 python-dotenv: pip install python-dotenv")
            print("  2. 在 app/__init__.py 中添加:")
            print("     from dotenv import load_dotenv")
            print("     load_dotenv()")
        
        if 'set_email_env.bat' in create_files:
            print()
            print("方式2 - 使用批处理脚本（推荐生产环境）：")
            print("  1. 以管理员身份运行 set_email_env.bat")
            print("  2. 重启电脑或重新打开命令行")
        
        if 'set_email_env.ps1' in create_files:
            print()
            print("方式3 - 使用 PowerShell 脚本：")
            print("  1. 以管理员身份运行 PowerShell")
            print("  2. 执行: .\\set_email_env.ps1")
            print("  3. 重启电脑或重新打开 PowerShell")
        
        print()
        print("=" * 60)
        print("🎉 配置完成！重启ERP服务后生效。")
        print("=" * 60)
        
    else:
        print()
        print("=" * 60)
        print("❌ 配置验证失败，请检查：")
        print("=" * 60)
        print("  1. 邮箱账号和密码是否正确")
        print("  2. 邮箱是否已开启SMTP服务")
        print("  3. 网络连接是否正常")
        print("  4. 防火墙是否允许SMTP端口(465)")
        print()
        print("💡 腾讯企业邮箱常见问题：")
        print("  - 新注册邮箱可能需要等待24小时才能使用SMTP")
        print("  - 部分邮箱需要使用'授权码'而不是登录密码")
        print("  - 检查邮箱是否被锁定或限制")
        print("=" * 60)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
