# ALCOEN QC 系统权限矩阵文档

> 本文档定义质量控制系统 (QC) 的权限码、角色分配及数据可见性规则，供开发权限检查逻辑时参考。
>
> **历史设计提示：** 本文档描述的是早期单身份权限模型。多身份注册、配件生产与装配/出厂共用身份、统一“供应商”命名及权限收口的现行设计，以 `AI_CATS_MULTI_IDENTITY_ACCESS_CONTROL.md` 为准。本文档仅用于理解旧实现和兼容代码。

---

## 1. 权限码定义

QC 系统的权限码在现有 ERP `PERMISSIONS` 字典基础上进行扩展，统一存储于 `roles.permissions` JSON 字段中。

### 1.1 新增 QC 权限列表

| 权限码 | 中文名称 | 功能说明 |
|--------|---------|---------|
| `qc_dashboard` | QC 仪表盘 | 查看 QC 首页统计数据和最近订单 |
| `qc_work_order_view` | 查看工件订单 | 进入质量控制/检测/验收列表和详情页 |
| `qc_work_order_create` | 创建工件订单 | 在质量控制模块新增工件订单 |
| `qc_work_order_edit` | 编辑工件订单 | 修改自己创建的、状态为 `qc_pending`/`rejected` 的订单 |
| `qc_work_order_delete` | 删除工件订单 | 删除自己创建的工件订单 |
| `qc_inspection_perform` | 执行质量检测 | 在质检详情页对各栏目进行 √/× 判定并提交 |
| `qc_acceptance_perform` | 执行验收确认 | 在验收页点击"质控员已验收"或"质检员已验收" |
| `qc_acceptance_rollback` | 验收回退/撤销 | 将已验收或已质检完成的订单退回至前面的流程 |

### 1.2 权限码在 Python 中的定义位置

建议在 `app/models.py` 中扩展 `PERMISSIONS` 常量字典：

```python
PERMISSIONS = {
    # === 原有 ERP 权限（保持不变）===
    'contract_view': '查看合同',
    'contract_create': '创建合同',
    ...
    
    # === 新增 QC 权限 ===
    'qc_dashboard': 'QC仪表盘',
    'qc_work_order_view': '查看工件订单',
    'qc_work_order_create': '创建工件订单',
    'qc_work_order_edit': '编辑工件订单',
    'qc_work_order_delete': '删除工件订单',
    'qc_inspection_perform': '执行质量检测',
    'qc_acceptance_perform': '执行验收确认',
    'qc_acceptance_rollback': '验收回退/撤销',
}
```

---

## 2. 角色权限分配

### 2.1 QC 专属角色

#### qc_controller（质量控制员）
```json
[
    "qc_dashboard",
    "qc_work_order_view",
    "qc_work_order_create",
    "qc_work_order_edit",
    "qc_work_order_delete",
    "qc_acceptance_perform",
    "qc_acceptance_rollback"
]
```

#### qc_inspector（质量检测员）
```json
[
    "qc_dashboard",
    "qc_work_order_view",
    "qc_inspection_perform"
]
```

### 2.2 与 ERP 共用的角色（在 QC 中的权限）

#### superadmin（超级管理员）
- 通过 `role.code == 'superadmin'` 特殊判定拥有所有权限。
- `permissions` 字段可保持为空列表 `[]` 或包含全部权限。

#### general_manager（总经理）
```json
[
    "qc_dashboard",
    "qc_work_order_view",
    "qc_work_order_create",
    "qc_work_order_edit",
    "qc_work_order_delete",
    "qc_inspection_perform",
    "qc_acceptance_perform",
    "qc_acceptance_rollback"
]
```

#### gm_assistant（总经理助理）
```json
[
    "qc_dashboard",
    "qc_work_order_view",
    "qc_inspection_perform",
    "qc_acceptance_perform",
    "qc_acceptance_rollback"
]
```

### 2.3 ERP 专属角色（在 QC 中无权限）

以下角色默认不包含任何 QC 权限，无法进入 QC 子系统：
- `department_pm`
- `sales_manager`
- `logistics_manager`

---

## 3. 数据可见性规则

### 3.1 可见性判定函数建议

在 `app/services/qc_service.py` 中建议实现以下服务方法：

```python
@staticmethod
def can_view_work_order(user, work_order) -> bool:
    """判断用户是否有权查看指定工件订单"""
    if user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']:
        return True
    if user.role.code == 'qc_controller':
        return work_order.controller_id == user.id
    if user.role.code == 'qc_inspector':
        return work_order.inspector_id == user.id
    return False

@staticmethod
def can_edit_work_order(user, work_order) -> bool:
    """判断用户是否有权编辑指定工件订单"""
    if user.is_superadmin or user.role.code == 'general_manager':
        return True
    if user.role.code == 'qc_controller':
        return work_order.controller_id == user.id and work_order.status in ['qc_pending', 'rejected']
    return False

@staticmethod
def can_inspect_work_order(user, work_order) -> bool:
    """判断用户是否有权执行质检"""
    if user.is_superadmin or user.role.code == 'general_manager':
        return True
    if user.role.code == 'qc_inspector':
        return work_order.inspector_id == user.id and work_order.status in ['qc_completed', 'inspection_pending']
    return False

@staticmethod
def can_accept_work_order(user, work_order) -> bool:
    """判断用户是否有权在验收页签字"""
    if user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']:
        return True
    if user.role.code == 'qc_controller' and work_order.controller_id == user.id:
        return work_order.status == 'inspection_completed'
    if user.role.code == 'qc_inspector' and work_order.inspector_id == user.id:
        return work_order.status == 'inspection_completed'
    return False

@staticmethod
def can_rollback_work_order(user, work_order) -> bool:
    """判断用户是否有权撤销验收或将流程回退"""
    if user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']:
        return True
    if user.role.code == 'qc_controller' and work_order.controller_id == user.id:
        return work_order.status in ['inspection_completed', 'accepted']
    return False
```

### 3.2 列表查询过滤规则

#### 质量控制模块列表 (`/qc/quality-control/`)
```python
query = QCWorkOrder.query
if user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']:
    pass  # 查看全部
elif user.role.code == 'qc_controller':
    query = query.filter(QCWorkOrder.controller_id == user.id)
else:
    query = query.filter(False)  # 无权限，返回空
```

#### 质量检测模块列表 (`/qc/quality-inspection/`)
```python
query = QCWorkOrder.query.filter(QCWorkOrder.status.in_(['qc_completed', 'inspection_pending']))
if user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']:
    pass  # 查看全部
elif user.role.code == 'qc_inspector':
    query = query.filter(QCWorkOrder.inspector_id == user.id)
else:
    query = query.filter(False)
```

#### 验收模块列表 (`/qc/acceptance/`)
```python
query = QCWorkOrder.query.filter(QCWorkOrder.status.in_(['inspection_completed', 'accepted']))
if user.is_superadmin or user.role.code in ['general_manager', 'gm_assistant']:
    pass  # 查看全部
elif user.role.code == 'qc_controller':
    query = query.filter(QCWorkOrder.controller_id == user.id)
elif user.role.code == 'qc_inspector':
    query = query.filter(QCWorkOrder.inspector_id == user.id)
else:
    query = query.filter(False)
```

---

## 4. 前端权限控制

### 4.1 导航栏菜单显示

在 `templates/qc/base.html` 中，根据用户权限渲染菜单项：

```html
{% if current_user.has_permission('qc_work_order_create') %}
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('qc.quality_control_list') }}">质量控制</a>
</li>
{% endif %}

{% if current_user.has_permission('qc_inspection_perform') %}
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('qc.quality_inspection_list') }}">质量检测</a>
</li>
{% endif %}

{% if current_user.has_permission('qc_acceptance_perform') %}
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('qc.acceptance_list') }}">验收模块</a>
</li>
{% endif %}
```

### 4.2 页面内按钮显示

在模板中通过条件判断控制按钮的显示/隐藏：

```html
<!-- 仅质控员显示完成按钮 -->
{% if current_user.role.code == 'qc_controller' and work_order.controller_id == current_user.id %}
    <button class="btn btn-primary">完成并推送</button>
{% endif %}

<!-- 仅质检员显示质检提交按钮 -->
{% if current_user.role.code == 'qc_inspector' and work_order.inspector_id == current_user.id %}
    <button class="btn btn-success">质检合格</button>
    <button class="btn btn-danger">质检不合格</button>
{% endif %}
```

---

## 5. 权限校验装饰器

### 5.1 推荐的 QC 专属装饰器

在 `app/utils/decorators.py` 中新增：

```python
def qc_login_required(f):
    """要求用户必须登录且具有 QC 访问权限"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url, sub='qc'))
        
        from app.models import User
        user = User.query.get(session['user_id'])
        
        if not user or not user.is_active:
            session.clear()
            return redirect(url_for('auth.login', sub='qc'))
        
        # 检查是否有 QC 角色绑定
        from app.models import QCUserBinding
        binding = QCUserBinding.query.filter_by(user_id=user.id, is_active=True).first()
        if not binding and user.role.code not in ['superadmin', 'general_manager', 'gm_assistant']:
            flash('您尚未获得 QC 系统访问权限', 'warning')
            return redirect(url_for('auth.login', sub='qc'))
        
        g.current_user = user
        g.qc_role_id = binding.role_id if binding else user.role_id
        return f(*args, **kwargs)
    return decorated_function
```

### 5.2 简化策略

考虑到最小侵入原则，也可以复用现有的 `login_required` 装饰器，在路由函数内部自行检查 QC 权限：

```python
@login_required
def some_qc_route():
    if not g.current_user.has_permission('qc_work_order_view'):
        flash('没有权限', 'error')
        return redirect(url_for('main.index'))
    # ...
```

本项目的实际实现采用**复用现有装饰器 + 路由内二次校验**的简化策略。

---

## 6. 权限变更日志

| 日期 | 版本 | 变更说明 |
|------|------|---------|
| 2026-04-13 | v1.0 | 初始版本，定义 8 个 QC 权限码及 5 个角色的权限分配 |
