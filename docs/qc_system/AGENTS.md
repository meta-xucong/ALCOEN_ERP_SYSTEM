# ALCOEN QC 系统 - Agent 编码规范

> 本文档为 Kimi Code CLI Agent 在开发质量控制系统 (QC) 模块时提供专属上下文和编码约束。

---

## 1. 适用范围

本 `AGENTS.md` 适用于 `docs/qc_system/` 及其关联的以下目录中的所有文件：
- `app/routes/qc.py`
- `app/services/qc_service.py`
- `app/models.py` 中的 QC 相关模型
- `templates/qc/*`
- `migrations/migrate_add_qc_system.py`

---

## 2. 核心设计约束（必读）

### 2.1 最小侵入原则
**在任何情况下，修改现有 ERP 代码时都必须保证其原有功能不受影响。**

- ✅ 可以新增路由、服务、模板、静态文件
- ✅ 可以微调 `auth/login.html` 以支持 QC 入口显示
- ✅ 可以扩展 `app/models.py` 中的模型和权限常量
- ❌ 不得删除或修改现有 ERP 业务逻辑（合同、交易、对账单等）
- ❌ 不得改变现有 `users` 表的结构（如删除字段、修改唯一约束）
- ❌ 不得破坏现有 pytest 测试（修改后需全量运行并修复）

### 2.2 认证共享约束
QC 与 ERP 共享 `users` 表的密码、邮箱、电话等基础信息：
- 登录认证统一通过 `AuthService.authenticate()`
- 密码修改统一通过 `AuthService.change_password()` / `force_change_password()`
- 禁止在 QC 中单独实现密码存储逻辑

### 2.3 路由前缀约束
所有 QC 页面路由必须以 `/qc/` 为前缀（除了系统门户页 `/` 和认证页 `/auth/*`）。

### 2.4 文件上传约束
QC 附件必须存储在独立的目录树中：
```
static/uploads/qc/{work_order_id}/
```
禁止将 QC 文件写入 `static/uploads/contracts/` 或 `static/uploads/products/`。

---

## 3. 编码规范

### 3.1 Python 代码规范
- 遵循 PEP 8
- 所有函数、类必须包含 docstring
- 使用类型注解提高可读性
- 字符串格式化优先使用 f-string

### 3.2 SQLAlchemy 模型规范
新增模型必须放在 `app/models.py` 中，使用 SQLAlchemy 2.0 的 Mapped 语法：

```python
class QCWorkOrder(db.Model):
    """QC 工件订单模型。"""
    __tablename__ = 'qc_work_orders'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    # ...
```

### 3.3 Flask 路由规范
QC 路由统一使用 `qc_bp` Blueprint：

```python
from flask import Blueprint

qc_bp = Blueprint('qc', __name__, url_prefix='/qc')

@qc_bp.route('/quality-control/')
def quality_control_list():
    """质量控制列表页。"""
    pass
```

### 3.4 前端模板规范
- QC 模板统一放在 `templates/qc/` 目录下
- 必须继承 `templates/qc/base.html`（该文件继承相同的 Bootstrap 5 + Glass CSS）
- 保持与 ERP 一致的按钮、表单、卡片、表格样式

### 3.5 动态表单交互
检测点和备注的无限增删使用 JavaScript 实现，DOM 结构模板如下：

```html
<div class="dynamic-item border rounded p-3 mb-3" data-index="{index}">
    <div class="d-flex justify-content-between align-items-center mb-2">
        <span class="badge bg-secondary">检测点 {index}</span>
        <button type="button" class="btn btn-sm btn-outline-danger" onclick="removeItem(this)">
            <i class="bi bi-trash"></i> 删除
        </button>
    </div>
    <div class="mb-2">
        <input type="text" class="form-control" name="inspection_points[{index}][title]" placeholder="检测点名称" required>
    </div>
    <div class="mb-2">
        <textarea class="form-control" name="inspection_points[{index}][content]" placeholder="检测点描述" rows="2"></textarea>
    </div>
    <div class="file-upload-area">
        <input type="file" class="form-control" name="inspection_points[{index}][file]" accept="image/*" required>
    </div>
</div>
```

---

## 4. 状态与颜色映射（强制统一）

QC 工件订单状态在前端必须使用以下颜色类：

| 状态 | 状态码 | Badge 类 |
|------|--------|---------|
| 质控未完成 | `qc_pending` | `bg-secondary` |
| 质控已完成 | `qc_completed` | `bg-info` |
| 质检未完成 | `inspection_pending` | `bg-warning` |
| 质检已完成 | `inspection_completed` | `bg-primary` |
| 验收已完成 | `accepted` | `bg-success` |
| 质检不合格 | `rejected` | `bg-danger` |

对应的显示文本：

```python
QC_STATUS_DISPLAY = {
    'qc_pending': {'text': '质控未完成', 'badge': 'bg-secondary'},
    'qc_completed': {'text': '质控已完成', 'badge': 'bg-info'},
    'inspection_pending': {'text': '质检未完成', 'badge': 'bg-warning'},
    'inspection_completed': {'text': '质检已完成', 'badge': 'bg-primary'},
    'accepted': {'text': '验收已完成', 'badge': 'bg-success'},
    'rejected': {'text': '质检不合格', 'badge': 'bg-danger'},
}
```

该字典必须定义在 `app/models.py` 或 `app/services/qc_service.py` 中，并在模板中统一调用。

---

## 5. 开发检查清单（每次提交前必做）

### 5.1 语法静态检查
```bash
python -m py_compile app/routes/qc.py app/services/qc_service.py app/models.py migrations/migrate_add_qc_system.py
```

### 5.2 数据库结构验证
```bash
python migrations/migrate_add_qc_system.py
```

### 5.3 应用启动验证
```bash
python run.py
```
确认无报错后按 `Ctrl+C` 停止。

### 5.4 测试运行
```bash
pytest tests/ -v
```
确保现有测试不因 QC 改造而失败。

### 5.5 闭环功能验证
- 创建工件订单 → 查看列表 → 编辑保存 → 完成推送 → 质检提交 → 验收签字 → 打印清单

---

## 6. 进程保护规则（重申）

重启 ERP/QC 服务前：
1. `netstat -ano | findstr :8080` 确认服务端口
2. `taskkill /PID <PID> /F` 仅杀掉对应 PID
3. **严禁**使用 `taskkill /F /IM python.exe`

---

## 7. 常用参考路径

| 用途 | 路径 |
|------|------|
| QC 路由 | `app/routes/qc.py` |
| QC 服务 | `app/services/qc_service.py` |
| QC 模型 | `app/models.py` |
| QC 模板 | `templates/qc/` |
| QC 静态文件 | `static/uploads/qc/` |
| 认证路由 | `app/routes/auth.py` |
| 装饰器 | `app/utils/decorators.py` |
| 数据库 | `data/erp.db` |
| 运行入口 | `run.py` |

---

*文档版本: v1.0*  
*创建日期: 2026-04-13*
