#!/usr/bin/env python3
"""
邮件发送测试脚本
快速验证邮件配置是否正确
"""
import os
import sys

def test_import():
    """测试导入"""
    print("=" * 60)
    print("📧 ERP系统 - 邮件发送测试")
    print("=" * 60)
    print()
    
    print("[1/3] 检查依赖...")
    try:
        from app import create_app, db
        from app.services.email_service import EmailService
        print("  ✅ 所有模块导入成功")
        return create_app, EmailService
    except Exception as e:
        print(f"  ❌ 导入失败: {e}")
        return None, None


def test_config(app):
    """测试配置"""
    print()
    print("[2/3] 检查邮件配置...")
    
    configs = {
        'MAIL_SERVER': app.config.get('MAIL_SERVER'),
        'MAIL_PORT': app.config.get('MAIL_PORT'),
        'MAIL_USERNAME': app.config.get('MAIL_USERNAME'),
        'MAIL_PASSWORD': app.config.get('MAIL_PASSWORD'),
    }
    
    all_ok = True
    for key, value in configs.items():
        if key == 'MAIL_PASSWORD':
            display = '*' * len(value) if value else '(未设置)'
        else:
            display = value if value else '(未设置)'
        
        status = '✅' if value else '❌'
        print(f"  {status} {key}: {display}")
        
        if not value:
            all_ok = False
    
    if not all_ok:
        print()
        print("⚠️  部分配置未设置，请检查：")
        print("  - 环境变量是否已配置")
        print("  - .env 文件是否存在且正确")
        print("  - 是否已重启ERP服务")
        return False
    
    return True


def test_send(app, EmailService):
    """测试发送"""
    print()
    print("[3/3] 测试发送邮件...")
    print("-" * 60)
    
    with app.app_context():
        # 使用配置的邮箱作为收件人进行测试
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import smtplib
        
        try:
            username = app.config.get('MAIL_USERNAME')
            password = app.config.get('MAIL_PASSWORD')
            server_addr = app.config.get('MAIL_SERVER', 'smtp.exmail.qq.com')
            port = app.config.get('MAIL_PORT', 465)
            
            print(f"  连接到 {server_addr}:{port}...")
            server = smtplib.SMTP_SSL(server_addr, port, timeout=10)
            
            print(f"  登录账号 {username}...")
            server.login(username, password)
            
            # 创建测试邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = 'ERP系统 - 邮件测试'
            msg['From'] = f'ERP系统 <{username}>'
            msg['To'] = username
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: "Microsoft YaHei", Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                    .content {{ padding: 30px; }}
                    .success {{ color: #28a745; font-size: 48px; text-align: center; margin: 20px 0; }}
                    .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #999; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>✅ 邮件配置测试成功！</h1>
                    </div>
                    <div class="content">
                        <div class="success">🎉</div>
                        <p style="text-align: center; font-size: 16px;">
                            您的ERP系统邮件服务已正确配置，可以正常发送验证码邮件。
                        </p>
                        <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                        <p style="color: #666; font-size: 14px;">
                            <strong>配置信息：</strong><br>
                            SMTP服务器: {server_addr}<br>
                            端口: {port}<br>
                            发件账号: {username}<br>
                            发送时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        </p>
                    </div>
                    <div class="footer">
                        <p>此邮件由ERP系统自动发送</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            print(f"  发送测试邮件到 {username}...")
            server.sendmail(username, username, msg.as_string())
            server.quit()
            
            print("-" * 60)
            print("✅ 邮件发送成功！")
            print()
            print(f"📧 请检查收件箱: {username}")
            print("   如果未收到，请检查垃圾邮件文件夹")
            
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            print("-" * 60)
            print(f"❌ 认证失败: {e}")
            print()
            print("💡 可能的原因：")
            print("   1. 邮箱账号或密码错误")
            print("   2. 腾讯企业邮箱需要使用授权码而不是登录密码")
            print("   3. 邮箱账号被锁定")
            return False
            
        except Exception as e:
            print("-" * 60)
            print(f"❌ 发送失败: {e}")
            return False


def main():
    """主函数"""
    create_app, EmailService = test_import()
    
    if not create_app:
        print()
        print("=" * 60)
        print("请检查是否已安装所有依赖：")
        print("  pip install -r requirements.txt")
        print("=" * 60)
        return 1
    
    app = create_app()
    
    if not test_config(app):
        print()
        print("=" * 60)
        print("配置检查未通过，测试中止")
        print("=" * 60)
        return 1
    
    print()
    choice = input("是否立即发送测试邮件? (y/n): ").strip().lower()
    
    if choice in ('y', 'yes', '是'):
        if test_send(app, EmailService):
            print()
            print("=" * 60)
            print("🎉 邮件配置完全正确！ERP系统的验证码功能可以正常使用。")
            print("=" * 60)
            return 0
        else:
            print()
            print("=" * 60)
            print("⚠️  邮件发送失败，请检查配置后重试")
            print("=" * 60)
            return 1
    else:
        print()
        print("测试已取消")
        return 0


if __name__ == '__main__':
    sys.exit(main())
