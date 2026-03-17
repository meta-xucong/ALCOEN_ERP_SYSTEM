# ALCOEN ERP 系统 - Agent 指导原则

本文档为 Kimi Code CLI Agent 提供项目特定的上下文和编码规范。

---

## Agent 行为准则（必读）

### 提交前必须执行的检查

**在完成任何代码修改后，必须按以下顺序执行自检：**

1. **语法静态自检**
   - 使用 `py_compile` 检查所有修改的 Python 文件
   - 确保无语法错误、无导入错误

2. **数据库结构自检**
   - 检查模型定义与数据库表结构一致
   - 如有新增字段，必须创建迁移脚本
   - 使用 `PRAGMA table_info(table_name)` 验证列存在

3. **模板结构自检**
   - 检查 HTML 模板中的变量名与后端一致
   - 确保 JavaScript 函数正确引用

4. **全量功能自检**
   - 应用能正常启动
   - 关键功能（增删改查）能正常执行
   - 数据库查询无报错

5. **闭环验证**
   - 确保修改的功能可以完整闭环（创建->查看->编辑->保存）
   - 无明显逻辑漏洞

**只有以上所有检查通过后，才能提交代码。**

### 进程保护规则（重要！）

**在编写代码、重启服务时，严禁误杀 Kimi Web 自身进程！**

1. **重启 ERP 服务前**
   - 必须先检查当前运行的 python 进程，识别出 Kimi Web 自身进程（通常占用内存较大或启动时间较早）
   - 只杀掉 ERP 服务对应的 python 进程（监听 8080 端口的进程）
   - 使用 `tasklist | findstr python` 查看所有 python 进程
   - 使用 `netstat -ano | findstr :8080` 确认 ERP 服务端口

2. **禁止的操作**
   - ❌ 禁止使用 `taskkill /F /IM python.exe` 杀掉所有 python 进程
   - ❌ 禁止重启系统
   - ❌ 禁止杀掉端口不是 8080 的 python 进程

3. **正确的重启方式**
   ```powershell
   # 1. 查看 8080 端口占用
   netstat -ano | findstr :8080
   
   # 2. 只杀掉对应 PID 的进程
   taskkill /PID <PID> /F
   
   # 3. 启动 ERP 服务
   python run.py
   ```

---

## 项目概述

**项目名称**: ALCOEN 轻量级 ERP 订单管理系统  
**技术栈**: Python + Flask + SQLite + Bootstrap 5  
**部署环境**: Ubuntu VPS (裸机部署)  
**用户规模**: ≤10人，低并发

### 核心功能

- 订单录入与管理（产品名称、公司名称、产品号、发货量等）
- 公司信息维护
- 产品信息维护
- 多条件检索查询
- Excel/CSV 导出（预设格式模板）
- 历史订单追溯

---

## 技术架构

### 核心技术栈

| 层级 | 技术 | 版本 |
|-----|------|------|
| 后端语言 | Python | 3.10+ |
| Web框架 | Flask | 2.3+ |
| 数据库 | SQLite | 3.x |
| ORM | SQLAlchemy | 2.0+ |
| Excel生成 | pandas + openpyxl | 最新版 |
| 前端 | HTML5 + Bootstrap 5 | 5.x |
| 模板引擎 | Jinja2 | Flask内置 |

### 项目结构

```
/opt/erp/
├── app/                        # 应用主目录
│   ├── __init__.py            # Flask应用初始化
│   ├── models.py              # 数据模型定义
│   ├── routes/                # 路由/视图模块
│   │   ├── __init__.py
│   │   ├── main.py            # 主页面路由
│   │   ├── order.py           # 订单相关路由
│   │   ├── search.py          # 查询路由
│   │   └── export.py          # 导出路由
│   ├── services/              # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── order_service.py   # 订单业务逻辑
│   │   └── export_service.py  # 导出逻辑
│   └── utils/                 # 工具函数
│       ├── __init__.py
│       └── helpers.py
├── static/                    # 静态资源
│   ├── css/
│   ├── js/
│   └── templates/             # Excel模板文件
│       └── order_template.xlsx
├── templates/                 # HTML模板
│   ├── base.html             # 基础模板
│   ├── index.html
│   ├── order/
│   │   ├── list.html
│   │   ├── new.html
│   │   └── detail.html
│   ├── search/
│   │   └── index.html
│   └── components/
│       ├── navbar.html
│       └── pagination.html
├── data/                      # 数据目录
├── logs/                      # 日志目录
├── config.py                  # 配置文件
├── requirements.txt           # Python依赖
├── wsgi.py                    # WSGI入口
└── run.py                     # 开发运行入口
```

### 数据模型

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   Company       │       │    Product      │       │    Order        │
│   (公司信息)     │       │   (产品信息)     │       │   (订单信息)     │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │◄──────┤ company_id (FK) │       │ id (PK)         │
│ name            │       │ id (PK)         │◄──────┤ product_id (FK) │
│ address         │       │ name            │       │ company_id (FK) │
│ contact_person  │       │ product_no      │       │ quantity        │
│ phone           │       │ description     │       │ order_date      │
│ created_at      │       │ unit_price      │       │ delivery_date   │
└─────────────────┘       │ created_at      │       │ status          │
                          └─────────────────┘       │ remark          │
                                                    │ created_by      │
                                                    │ created_at      │
                                                    └─────────────────┘
```

---

## 编码规范

### Python 代码规范

1. **遵循 PEP 8** 风格指南
2. **使用类型注解** 提高代码可读性和可维护性
3. **函数和类** 必须包含 docstring
4. **字符串格式化** 优先使用 f-string

```python
# 推荐
from datetime import datetime
from typing import Optional

def create_order(
    product_id: int,
    company_id: int,
    quantity: float,
    delivery_date: Optional[datetime] = None
) -> dict:
    """创建新订单。
    
    Args:
        product_id: 产品ID
        company_id: 公司ID
        quantity: 发货量
        delivery_date: 预计交货日期，默认为None
        
    Returns:
        包含订单信息的字典
    """
    order = {
        "product_id": product_id,
        "company_id": company_id,
        "quantity": quantity,
        "delivery_date": delivery_date,
        "created_at": datetime.now()
    }
    return order
```

### Flask 路由规范

1. **路由命名** 使用小写字母和下划线
2. **HTTP 方法** 明确指定
3. **错误处理** 使用统一的错误响应格式

```python
from flask import Blueprint, jsonify, request, render_template

order_bp = Blueprint('order', __name__, url_prefix='/order')

@order_bp.route('/new', methods=['GET', 'POST'])
def create_order():
    """订单录入页面。"""
    if request.method == 'POST':
        # 处理表单提交
        pass
    return render_template('order/new.html')

@order_bp.route('/<int:order_id>')
def order_detail(order_id: int):
    """订单详情页面。"""
    order = Order.query.get_or_404(order_id)
    return render_template('order/detail.html', order=order)
```

### SQLAlchemy 模型规范

```python
from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Order(db.Model):
    """订单模型。"""
    
    __tablename__ = 'orders'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'))
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    order_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    delivery_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    
    # 关联关系
    product: Mapped['Product'] = relationship(back_populates='orders')
    company: Mapped['Company'] = relationship(back_populates='orders')
```

### 前端规范

1. **使用 Bootstrap 5** 作为 CSS 框架
2. **HTML 模板** 继承 `base.html`
3. **表单验证** 前端 + 后端双重验证
4. **响应式设计** 适配不同设备

```html
{% extends 'base.html' %}

{% block title %}订单录入 - ERP系统{% endblock %}

{% block content %}
<div class="container">
    <div class="row justify-content-center">
        <div class="col-md-8">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0">新建订单</h5>
                </div>
                <div class="card-body">
                    <form method="POST" action="{{ url_for('order.create_order') }}">
                        <!-- 表单字段 -->
                    </form>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

---

## 开发指导

### 优先事项

1. **P0 (必需)**
   - 公司信息增删改查
   - 产品信息增删改查
   - 订单录入
   - 订单列表/详情
   - 按产品/公司/日期范围查询
   - 历史订单追溯
   - 单订单导出Excel（预设格式模板）

2. **P1 (重要)**
   - 订单编辑/删除
   - 批量订单导出
   - 数据备份功能

3. **P2 (可选)**
   - 简单登录功能

### 模块划分建议

按以下顺序开发：

1. **Phase 1** (3-5天): 基础框架 + 订单录入 + 数据存储
2. **Phase 2** (2-3天): 查询功能 + 列表展示
3. **Phase 3** (2-3天): Excel导出（模板预设）
4. **Phase 4** (1-2天): 部署上线 + 测试优化

### 数据库备份策略

- SQLite数据库: 定时复制+压缩 (每日)
- 代码文件: Git版本控制
- Excel模板: 文件备份 (变更时)

---

## 部署配置

### 服务器软件栈

| 组件 | 用途 |
|-----|------|
| Gunicorn | WSGI HTTP服务器，运行Flask应用 |
| Nginx（可选） | 反向代理、静态文件服务、HTTPS支持 |
| systemd | 进程守护，确保服务开机自启 |

### 环境变量

```bash
# config.py 中使用的环境变量
FLASK_ENV=production
FLASK_APP=wsgi.py
DATABASE_URL=sqlite:///data/erp.db
SECRET_KEY=your-secret-key-here
```

---

## 工具使用偏好

- **文件操作**: 优先使用 `StrReplaceFile` 进行编辑，`WriteFile` 用于创建新文件
- **代码搜索**: 使用 `Grep` 查找代码引用和模式
- **文件查找**: 使用 `Glob` 查找特定类型的文件
- **任务管理**: 复杂功能开发使用 `SetTodoList` 跟踪进度
- **并行任务**: 独立的子任务使用 `Task` 工具分配给子 Agent

---

## 注意事项

1. **SQLite WAL 模式**: 启用 Write-Ahead Logging 以支持更好的并发性能
2. **数据验证**: 所有用户输入都必须经过验证
3. **错误处理**: 使用 try-except 捕获异常，并记录错误日志
4. **Excel 导出**: 使用 pandas + openpyxl，支持复杂格式和预设模板
5. **备份**: 数据库文件定期备份，代码使用 Git 管理

---

## 个性化规则

### 回答格式
- **每次回答末尾**: 必须添加 "喵~"

---

## 参考文档

- **ERP_System_Technical_Proposal.md** - 原始技术方案
- **ERP_Implementation_Guide.md** - 详细实施技术指南（代码编写参考）

---

*文档版本: v1.0*  
*创建日期: 2026-03-04*  
*最后更新: 2026-03-05*
