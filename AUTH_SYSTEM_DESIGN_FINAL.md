# ALCOEN ERP 账号登录系统 - 最终设计方案

> 版本: v1.0 (Final)  
> 创建日期: 2026-03-13  
> 状态: **已确认，待开发**

---

## 一、需求确认清单

| 需求项 | 确认内容 |
|-------|---------|
| 注册方式 | ✅ 开放注册，需管理员审核 |
| 默认密码 | ✅ 统一为 `1234.abcd` |
| 首次登录 | ✅ 强制修改密码 |
| 角色体系 | ✅ 5级：超级管理员、总经理、部门PM、部门销售经理、物流经理 |
| 记住我 | ✅ 30天 |
| 密码找回 | ✅ 管理员重置 |

---

## 二、角色与权限详细设计

### 2.1 角色定义表

| 角色代码 | 角色名称 | 部门归属 | 数据范围 |
|---------|---------|---------|---------|
| `superadmin` | 超级管理员 | 无 | 全部 |
| `general_manager` | 总经理 | 无 | 全部 |
| `department_pm` | 部门PM | 有 | 本部门 |
| `sales_manager` | 部门销售经理 | 有 | 本部门 |
| `logistics_manager` | 物流经理 | 无 | 全部（资金脱敏，仅发货相关） |

### 2.2 权限矩阵表

| 功能模块 | 操作 | superadmin | general_manager | department_pm | sales_manager | logistics_manager |
|---------|------|:----------:|:---------------:|:-------------:|:-------------:|:-----------------:|
| **合同管理** | 查看合同 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ✅(全部，脱敏) |
| | 创建合同 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ❌ |
| | 编辑合同 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ❌(仅发货记录可编辑) |
| | 编辑发货记录 | ✅ | ✅ | ✅(本部门) | ❌ | ✅(全部) |
| | 删除合同 | ✅ | ✅ | ✅(本部门) | ❌ | ❌ |
| **产品库** | 查看产品 | ✅ | ✅ | ✅ | ✅ | ✅ |
| | 创建产品 | ✅ | ✅ | ✅ | ✅ | ❌ |
| | 编辑产品 | ✅ | ✅ | ✅ | ✅ | ❌ |
| | 删除产品 | ✅ | ✅ | ✅ | ❌ | ❌ |
| **交易记录** | 查看交易 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ✅(全部) |
| | 录入交易 | ✅ | ✅ | ✅(本部门) | ❌ | ✅(全部) |
| | 编辑交易 | ✅ | ✅ | ✅(本部门) | ❌ | ✅(全部，仅发货相关) |
| | 删除交易 | ✅ | ✅ | ✅(本部门) | ❌ | ❌ |
| **对账单** | 查看对账单 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ✅(全部，脱敏) |
| | 生成对账单 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ❌ |
| | 导出对账单 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ❌ |
| | 删除对账单 | ✅ | ✅ | ✅(本部门) | ❌ | ❌ |
| | 删除对账单 | ✅ | ✅ | ✅(本部门) | ❌ | ❌ |
| **回款记录** | 查看回款 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ❌(完全隐藏) |
| | 录入回款 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ❌ |
| | 编辑回款 | ✅ | ✅ | ✅(本部门) | ✅(本部门) | ❌ |
| **用户管理** | 管理用户 | ✅ | ❌ | ❌ | ❌ | ❌ |
| | 管理角色 | ✅ | ❌ | ❌ | ❌ | ❌ |
| | 审核注册 | ✅ | ❌ | ❌ | ❌ | ❌ |

### 2.3 特殊权限说明

#### 物流经理的特殊处理
- **数据范围**：可查看**所有部门**的合同和订单（跨部门）
- **资金脱敏显示**：价格、金额等字段显示为 `***`
- **发货记录独立权限**：可编辑**所有合同**的发货记录
- **回款记录完全隐藏**：页面不显示回款相关模块
- **其他信息只读**：合同基本信息、产品信息等只能查看不能编辑
- **职责**：统一处理所有部门的发货物流

#### 部门销售经理的限制
- **发货记录只读**：可查看但不可编辑发货记录
- **其他编辑权限**：合同信息、产品信息等可正常编辑

---

## 三、数据模型设计

### 3.1 用户表 (users)

```python
class User(db.Model):
    """用户表"""
    __tablename__ = 'users'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    real_name: Mapped[str] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(100), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    
    # 角色关联
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), nullable=False)
    
    # 部门关联（部门角色需要，物流经理不需要）
    department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'), nullable=True)
    
    # 状态
    is_active: Mapped[bool] = mapped_column(default=False)  # 需要审核后激活
    is_superadmin: Mapped[bool] = mapped_column(default=False)
    require_password_change: Mapped[bool] = mapped_column(default=True)  # 首次登录需改密码
    
    # 登录记录
    last_login_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_login_ip: Mapped[str] = mapped_column(String(50), nullable=True)
    login_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # 审核信息
    approved_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    role: Mapped['Role'] = relationship(back_populates='users')
    department: Mapped['Department'] = relationship(foreign_keys=[department_id])
    
    def has_permission(self, permission_code: str) -> bool:
        """检查用户是否有指定权限"""
        if self.is_superadmin:
            return True
        return self.role.has_permission(permission_code)
    
    def can_edit_delivery(self) -> bool:
        """是否可以编辑发货记录"""
        if self.is_superadmin or self.role.code in ['superadmin', 'general_manager', 'department_pm']:
            return True
        if self.role.code == 'logistics_manager':
            return True  # 物流经理只能编辑发货记录
        return False
    
    def can_view_financial(self) -> bool:
        """是否可以查看资金信息"""
        if self.role.code == 'logistics_manager':
            return False
        return True
    
    def can_access_department(self, dept_name: str) -> bool:
        """是否可以访问指定部门的数据"""
        # 超级管理员、总经理、物流经理可以访问所有部门
        if self.is_superadmin or self.role.code in ['general_manager', 'logistics_manager']:
            return True
        # 部门角色只能访问本部门
        if self.department and self.department.name == dept_name:
            return True
        return False
    
    def can_edit_contract_delivery(self, contract) -> bool:
        """是否可以编辑合同的发货记录"""
        if self.is_superadmin:
            return True
        # 物流经理可以编辑所有合同的发货记录
        if self.role.code == 'logistics_manager':
            return True
        # 总经理、部门PM可以编辑
        if self.role.code in ['general_manager', 'department_pm']:
            return True
        # 部门销售经理不能编辑发货记录
        return False
```

### 3.2 角色表 (roles)

```python
class Role(db.Model):
    """角色表"""
    __tablename__ = 'roles'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    
    # 权限配置 (JSON格式)
    permissions: Mapped[str] = mapped_column(Text, default='[]')
    
    # 排序权重
    level: Mapped[int] = mapped_column(Integer, default=0)  # 数值越大权限越高
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联
    users: Mapped[list['User']] = relationship(back_populates='role')
    
    def has_permission(self, permission_code: str) -> bool:
        """检查角色是否有指定权限"""
        import json
        perms = json.loads(self.permissions) if self.permissions else []
        return permission_code in perms
```

### 3.3 权限常量定义

```python
# 权限定义常量
PERMISSIONS = {
    # 合同模块
    'contract_view': '查看合同',
    'contract_create': '创建合同',
    'contract_edit': '编辑合同',
    'contract_delete': '删除合同',
    'contract_edit_delivery': '编辑发货记录',  # 特殊权限
    
    # 产品模块
    'product_view': '查看产品',
    'product_create': '创建产品',
    'product_edit': '编辑产品',
    'product_delete': '删除产品',
    
    # 对账单模块
    'statement_view': '查看对账单',
    'statement_create': '生成对账单',
    'statement_export': '导出对账单',
    'statement_delete': '删除对账单',
    
    # 交易记录模块
    'transaction_view': '查看交易记录',
    'transaction_create': '录入交易',
    'transaction_edit': '编辑交易',
    'transaction_delete': '删除交易',
    
    # 回款记录模块
    'payment_view': '查看回款记录',
    'payment_create': '录入回款',
    'payment_edit': '编辑回款',
    
    # 用户管理模块
    'user_manage': '管理用户',
    'user_approve': '审核注册用户',
    'role_manage': '管理角色权限',
}

# 角色权限配置
ROLE_PERMISSIONS = {
    'superadmin': list(PERMISSIONS.keys()),  # 全部权限
    
    'general_manager': [
        'contract_view', 'contract_create', 'contract_edit', 'contract_delete', 'contract_edit_delivery',
        'product_view', 'product_create', 'product_edit', 'product_delete',
        'statement_view', 'statement_create', 'statement_export', 'statement_delete',
        'transaction_view', 'transaction_create', 'transaction_edit', 'transaction_delete',
        'payment_view', 'payment_create', 'payment_edit',
    ],
    
    'department_pm': [
        'contract_view', 'contract_create', 'contract_edit', 'contract_delete', 'contract_edit_delivery',
        'product_view', 'product_create', 'product_edit', 'product_delete',
        'statement_view', 'statement_create', 'statement_export', 'statement_delete',
        'transaction_view', 'transaction_create', 'transaction_edit', 'transaction_delete',
        'payment_view', 'payment_create', 'payment_edit',
    ],
    
    'sales_manager': [
        'contract_view', 'contract_create', 'contract_edit',
        'product_view', 'product_create', 'product_edit',
        'statement_view', 'statement_create', 'statement_export',
        'transaction_view',
        'payment_view', 'payment_create', 'payment_edit',
    ],
    
    'logistics_manager': [
        'contract_view', 'contract_edit_delivery',
        'product_view',
        'statement_view',
        'transaction_view', 'transaction_create', 'transaction_edit',
    ],
}
```

---

## 四、路由设计

### 4.1 认证路由 (auth.py)

| 路由 | 方法 | 功能 | 说明 |
|-----|------|------|------|
| `/auth/login` | GET/POST | 登录页面 | 独立页面，未登录访问首页重定向至此 |
| `/auth/register` | GET/POST | 注册页面 | 开放注册，提交后需审核 |
| `/auth/logout` | GET | 登出 | 清除session |
| `/auth/change-password` | GET/POST | 修改密码 | 首次登录强制跳转 |
| `/auth/pending` | GET | 审核中提示页 | 注册后等待审核显示 |

### 4.2 用户管理路由 (user.py)

| 路由 | 方法 | 功能 | 权限要求 |
|-----|------|------|---------|
| `/user/` | GET | 用户列表 | `user_manage` |
| `/user/pending` | GET | 待审核用户列表 | `user_approve` |
| `/user/<id>` | GET | 用户详情 | `user_manage` 或本人 |
| `/user/<id>/edit` | GET/POST | 编辑用户 | `user_manage` |
| `/user/<id>/approve` | POST | 审核通过 | `user_approve` |
| `/user/<id>/reject` | POST | 审核拒绝 | `user_approve` |
| `/user/<id>/toggle` | POST | 启用/禁用账号 | `user_manage` |
| `/user/<id>/reset-password` | POST | 重置密码为1234.abcd | `user_manage` |
| `/user/<id>/delete` | POST | 删除用户 | `user_manage` |
| `/user/profile` | GET/POST | 个人资料 | 登录用户 |

### 4.3 角色管理路由 (role.py)

| 路由 | 方法 | 功能 | 权限要求 |
|-----|------|------|---------|
| `/role/` | GET | 角色列表 | `role_manage` |
| `/role/<id>/edit` | GET/POST | 编辑角色权限 | `role_manage` |

---

## 五、页面设计

### 5.1 独立登录页面 (auth/login.html)

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                    ALCOEN ERP 系统                          │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │   👤 用户名                                         │   │
│  │   [____________________________________]           │   │
│  │                                                     │   │
│  │   🔒 密码                                           │   │
│  │   [____________________________________]           │   │
│  │                                                     │   │
│  │   [✓] 记住我 (30天)                                │   │
│  │                                                     │   │
│  │   [           登  录           ]                   │   │
│  │                                                     │   │
│  │   ─────────── 或 ───────────                       │   │
│  │                                                     │   │
│  │   [         注 册 新 账 号        ]                 │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│                    © 2024 ALCOEN                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 注册页面 (auth/register.html)

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                    注册新账号                               │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  👤 用户名 *                                        │   │
│  │  [____________________________________]            │   │
│  │                                                     │   │
│  │  🔒 密码 *                                          │   │
│  │  [____________________________________]            │   │
│  │  (系统将自动使用默认密码 1234.abcd)                  │   │
│  │                                                     │   │
│  │  📝 真实姓名 *                                      │   │
│  │  [____________________________________]            │   │
│  │                                                     │   │
│  │  🏢 所属部门 *                                      │   │
│  │  [▼ 请选择部门 ▼]                                  │   │
│  │                                                     │   │
│  │  📧 邮箱                                            │   │
│  │  [____________________________________]            │   │
│  │                                                     │   │
│  │  📱 电话                                            │   │
│  │  [____________________________________]            │   │
│  │                                                     │   │
│  │  [        提 交 注 册        ]                      │   │
│  │                                                     │   │
│  │  ⚠️ 注册后需管理员审核通过方可登录                   │   │
│  │                                                     │   │
│  │  已有账号？立即登录 ←                               │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 首次登录强制修改密码 (auth/change_password.html)

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│              🔐 首次登录 - 请修改密码                       │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  为保障账号安全，首次登录请修改默认密码              │   │
│  │                                                     │   │
│  │  当前密码: 1234.abcd                                │   │
│  │                                                     │   │
│  │  新密码 *                                           │   │
│  │  [____________________________________]            │   │
│  │  (至少6位，包含字母和数字)                           │   │
│  │                                                     │   │
│  │  确认新密码 *                                       │   │
│  │  [____________________________________]            │   │
│  │                                                     │   │
│  │  [        确 认 修 改        ]                      │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.4 用户管理页面 (user/list.html)

```
┌─────────────────────────────────────────────────────────────┐
│  用户管理                                    [+ 新增用户]   │
├─────────────────────────────────────────────────────────────┤
│  [用户名] [角色▼] [状态▼] [搜索] [清空]                     │
├─────────────────────────────────────────────────────────────┤
│  用户名    真实姓名   角色        部门      状态    操作    │
│  ─────────────────────────────────────────────────────────  │
│  admin     管理员    超级管理员   -        ✅启用  [编辑]   │
│  zhangsan  张三      部门PM      销售一部   ✅启用  [编辑]   │
│  lisi      李四      待审核      销售二部   ⏳待审  [审核]   │
│  wangwu    王五      销售经理    销售一部   ❌禁用  [启用]   │
├─────────────────────────────────────────────────────────────┤
│                    第 1 页 / 共 3 页                        │
└─────────────────────────────────────────────────────────────┘
```

### 5.5 待审核用户页面 (user/pending.html)

专门显示注册待审核的用户列表，管理员可快速通过或拒绝。

### 5.6 角色权限配置页面 (role/edit.html)

```
┌─────────────────────────────────────────────────────────────┐
│  配置角色权限: 部门PM                                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📁 合同管理                                                │
│    [✓] 查看合同    [✓] 创建合同    [✓] 编辑合同            │
│    [✓] 删除合同    [✓] 编辑发货记录                        │
│                                                             │
│  📁 产品库                                                  │
│    [✓] 查看产品    [✓] 创建产品    [✓] 编辑产品            │
│    [✓] 删除产品                                            │
│                                                             │
│  📁 对账单                                                  │
│    [✓] 查看对账单  [✓] 生成对账单  [✓] 导出对账单          │
│    [✓] 删除对账单                                          │
│                                                             │
│  📁 ...                                                    │
│                                                             │
│              [保存配置]  [取消]                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、权限控制实现

### 6.1 装饰器定义

```python
# app/utils/decorators.py

from functools import wraps
from flask import session, redirect, url_for, flash, request, g


def login_required(f):
    """要求用户必须登录"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        
        # 加载当前用户到 g
        from app.models import User
        g.current_user = User.query.get(session['user_id'])
        
        if not g.current_user:
            session.clear()
            return redirect(url_for('auth.login', next=request.url))
        
        # 检查是否需要修改密码
        if g.current_user.require_password_change and request.endpoint != 'auth.change_password':
            return redirect(url_for('auth.change_password'))
        
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission_code):
    """要求用户拥有指定权限"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login', next=request.url))
            
            from app.models import User
            user = User.query.get(session['user_id'])
            
            if not user or not user.has_permission(permission_code):
                flash('您没有权限执行此操作', 'error')
                return redirect(url_for('main.index'))
            
            g.current_user = user
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """要求用户必须是超级管理员"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        
        from app.models import User
        user = User.query.get(session['user_id'])
        
        if not user or not user.is_superadmin:
            flash('需要超级管理员权限', 'error')
            return redirect(url_for('main.index'))
        
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function
```

### 6.2 模板权限控制

```html
<!-- 根据权限显示/隐藏功能 -->

<!-- 编辑按钮 - 仅对有编辑权限的用户显示 -->
{% if current_user.has_permission('contract_edit') %}
<a href="{{ url_for('contract.edit', id=contract.id) }}" class="btn btn-primary">编辑</a>
{% endif %}

<!-- 删除按钮 - 仅对有删除权限的用户显示 -->
{% if current_user.has_permission('contract_delete') %}
<button class="btn btn-danger" onclick="deleteContract()">删除</button>
{% endif %}

<!-- 物流经理 - 资金信息脱敏 -->
{% if current_user.can_view_financial() %}
    <td>{{ contract.total_value|format_money }}</td>
{% else %}
    <td>***</td>
{% endif %}

<!-- 部门数据过滤 -->
{% if current_user.can_access_department(contract.department) %}
    <!-- 显示合同内容 -->
{% else %}
    <div class="alert alert-warning">您无权查看此部门的数据</div>
{% endif %}
```

---

## 七、数据库迁移与初始化

### 7.1 迁移脚本 (migrate_v1.4_auth_system.py)

```python
"""
v1.4 账号登录系统迁移脚本
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app, db
from app.models import Role, User
from werkzeug.security import generate_password_hash
from datetime import datetime

app = create_app()

def init_auth_system():
    """初始化认证系统"""
    with app.app_context():
        # 创建新表
        db.create_all()
        print("✓ 数据库表创建完成")
        
        # 初始化角色
        roles_data = [
            {
                'code': 'superadmin',
                'name': '超级管理员',
                'description': '拥有系统所有权限，可管理用户和角色',
                'level': 100,
                'permissions': '[]'  # 空列表表示拥有所有权限
            },
            {
                'code': 'general_manager',
                'name': '总经理',
                'description': '可查看和编辑所有数据，生成对账单',
                'level': 80,
                'permissions': '[]'  # 通过代码控制
            },
            {
                'code': 'department_pm',
                'name': '部门PM',
                'description': '可管理本部门所有数据和合同',
                'level': 60,
                'permissions': '[]'
            },
            {
                'code': 'sales_manager',
                'name': '部门销售经理',
                'description': '可查看本部门数据，编辑合同（不含发货记录）',
                'level': 40,
                'permissions': '[]'
            },
            {
                'code': 'logistics_manager',
                'name': '物流经理',
                'description': '仅可编辑发货记录，资金信息脱敏',
                'level': 20,
                'permissions': '[]'
            }
        ]
        
        for role_data in roles_data:
            if not Role.query.filter_by(code=role_data['code']).first():
                role = Role(**role_data)
                db.session.add(role)
                print(f"✓ 创建角色: {role_data['name']}")
        
        db.session.commit()
        
        # 创建默认超级管理员
        if not User.query.filter_by(username='admin').first():
            superadmin_role = Role.query.filter_by(code='superadmin').first()
            admin = User(
                username='admin',
                password_hash=generate_password_hash('1234.abcd'),
                real_name='系统管理员',
                role_id=superadmin_role.id,
                is_active=True,
                is_superadmin=True,
                require_password_change=True,  # 首次登录需改密码
                created_at=datetime.now()
            )
            db.session.add(admin)
            db.session.commit()
            print("✓ 默认管理员创建成功")
            print("  用户名: admin")
            print("  密码: 1234.abcd")
            print("  ⚠️ 首次登录需要修改密码")
        
        print("\n✓ 认证系统初始化完成")

if __name__ == '__main__':
    init_auth_system()
```

---

## 八、文件结构

```
app/
├── models.py                      # 添加 User, Role 模型
├── utils/
│   ├── __init__.py
│   ├── decorators.py              # 登录/权限装饰器
│   └── auth_helpers.py            # 认证辅助函数
├── routes/
│   ├── __init__.py
│   ├── auth.py                    # 登录/注册/登出
│   ├── user.py                    # 用户管理
│   ├── role.py                    # 角色权限管理
│   ├── main.py                    # 修改：添加登录保护
│   ├── contract.py                # 修改：添加权限控制
│   └── ...
├── services/
│   ├── __init__.py
│   ├── auth_service.py            # 认证服务
│   └── user_service.py            # 用户服务
templates/
├── auth/
│   ├── login.html                 # 独立登录页面
│   ├── register.html              # 注册页面
│   ├── change_password.html       # 修改密码
│   └── pending.html               # 审核中提示
├── user/
│   ├── list.html                  # 用户列表
│   ├── pending.html               # 待审核用户
│   ├── form.html                  # 用户编辑
│   └── profile.html               # 个人资料
├── role/
│   ├── list.html                  # 角色列表
│   └── edit.html                  # 权限编辑
└── base.html                      # 修改：用户信息、登录状态
static/
├── css/
│   └── auth.css                   # 登录页面专用样式
└── js/
    └── auth.js                    # 认证相关JS
```

---

## 九、与现有系统集成清单

### 9.1 需要修改的文件

| 文件 | 修改内容 |
|-----|---------|
| `app/__init__.py` | 注册 auth, user, role 蓝图；添加全局上下文处理器 |
| `app/models.py` | 添加 User, Role 模型；修改 Department 添加关联 |
| `app/routes/main.py` | 为 index 添加 @login_required |
| `app/routes/contract.py` | 添加权限装饰器；部门数据过滤；物流经理脱敏处理 |
| `app/routes/statement.py` | 添加权限装饰器；部门数据过滤 |
| `app/routes/product.py` | 添加权限装饰器 |
| `app/routes/transaction.py` | 添加权限装饰器；部门数据过滤 |
| `templates/base.html` | 添加用户信息显示；根据权限显示菜单 |
| `templates/contract/detail.html` | 根据角色显示/隐藏编辑按钮；资金脱敏 |
| `templates/contract/form.html` | 根据角色禁用部分字段 |

### 9.2 新增文件清单

| 文件 | 说明 |
|-----|------|
| `app/utils/decorators.py` | 权限装饰器 |
| `app/utils/auth_helpers.py` | 认证辅助函数 |
| `app/routes/auth.py` | 认证路由 |
| `app/routes/user.py` | 用户管理路由 |
| `app/routes/role.py` | 角色管理路由 |
| `app/services/auth_service.py` | 认证服务 |
| `app/services/user_service.py` | 用户服务 |
| `templates/auth/*.html` | 认证相关页面 |
| `templates/user/*.html` | 用户管理页面 |
| `templates/role/*.html` | 角色管理页面 |
| `static/css/auth.css` | 登录页面样式 |
| `migrate_v1.4_auth_system.py` | 数据库迁移脚本 |

---

## 十、开发步骤

### Phase 1: 核心认证功能
1. ✅ 创建 User, Role 模型
2. ✅ 创建认证路由 (login, register, logout, change-password)
3. ✅ 创建独立登录/注册页面
4. ✅ 实现登录验证装饰器
5. ✅ 数据库迁移脚本

### Phase 2: 用户与角色管理
1. ✅ 创建用户管理路由和页面
2. ✅ 创建角色权限管理路由和页面
3. ✅ 实现用户审核流程
4. ✅ 实现密码重置功能

### Phase 3: 权限集成
1. ✅ 为现有路由添加权限控制
2. ✅ 模板中添加权限判断
3. ✅ 实现部门数据过滤
4. ✅ 实现物流经理资金脱敏

### Phase 4: 测试与优化
1. 测试各角色权限
2. 测试数据隔离
3. 优化用户体验

---

## 十一、附录

### 默认账号信息

```
用户名: admin
密码: 1234.abcd
角色: 超级管理员
注意: 首次登录强制修改密码
```

### 注册流程

```
用户注册 → 填写信息（含部门选择）→ 提交 → 等待审核 
    → 管理员审核通过 → 可登录使用
    → 管理员审核拒绝 → 账号禁用
```

### 登录流程

```
用户登录 → 验证账号密码
    → 账号未激活 → 提示等待审核
    → 需要改密码 → 跳转修改密码页面
    → 正常登录 → 跳转ERP主页
```

---

**此文档已根据需求确认完成，可作为开发指导文档使用。**

**确认人:** ________________ **日期:** ________________

**开发人员:** ________________ **开始日期:** ________________
