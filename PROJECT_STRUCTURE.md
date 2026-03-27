# ALCOEN ERP v1.0 项目结构

## 文件清单

### 根目录
```
D:\AI\ALCOEN_ERP_SYSTEM\
├── AGENTS.md                        # Agent 编码规范
├── ERP_Implementation_Guide.md      # 详细实施技术指南
├── ERP_System_Technical_Proposal.md # 原始技术方案
├── PROJECT_STRUCTURE.md             # 本文件
├── config.py                        # 应用配置
├── requirements.txt                 # Python 依赖
├── run.py                           # 开发启动入口
└── wsgi.py                          # WSGI 生产入口
```

### 应用代码 (app/)
```
app/
├── __init__.py              # Flask 应用工厂
├── models.py                # 数据库模型 (Company, Transaction, Statement, StatementItem)
├── forms.py                 # WTForms 表单定义
├── routes/                  # 路由/控制器
│   ├── __init__.py
│   ├── main.py             # 首页、API
│   ├── transaction.py      # 交易记录 CRUD
│   └── statement.py        # 对账单生成、导出
├── services/               # 业务逻辑层
│   ├── __init__.py
│   ├── statement_service.py   # 对账单业务逻辑
│   └── transaction_service.py # 交易记录业务逻辑
└── utils/                  # 工具函数
    ├── __init__.py
    └── excel_export.py     # Excel 导出功能
```

### 模板 (templates/)
```
templates/
├── base.html               # 基础模板
├── index.html              # 首页/仪表盘
├── transaction/            # 交易记录模块
│   ├── form.html          # 录入/编辑表单
│   └── list.html          # 列表页面
└── statement/              # 对账单模块
    ├── generator.html     # 对账单生成器
    ├── list.html          # 历史对账单列表
    └── result.html        # 对账单展示页面
```

### 静态资源 (static/)
```
static/
├── css/
│   └── style.css          # 自定义样式
└── js/
    └── app.js             # 前端脚本
```

### 数据目录
```
data/                      # SQLite 数据库
exports/                   # 导出的 Excel 文件
logs/                      # 日志文件
```

## 功能实现清单

### 核心功能 ✅

| 功能模块 | 状态 | 文件 |
|---------|------|------|
| 交易记录录入 | ✅ | transaction/form.html, forms.py |
| 交易记录列表 | ✅ | transaction/list.html |
| 交易记录编辑 | ✅ | transaction/form.html |
| 交易记录删除 | ✅ | transaction/list.html |
| 公司自动补全 | ✅ | models.py (Company表) |
| 对账单生成器 | ✅ | statement/generator.html |
| 对账单展示 | ✅ | statement/result.html |
| 对账单编号生成 | ✅ | statement_service.py |
| Excel 导出 | ✅ | excel_export.py |
| 历史对账单 | ✅ | statement/list.html |

### 数据模型 ✅

| 模型 | 说明 |
|------|------|
| Company | 公司名称表，用于自动补全 |
| Transaction | 交易记录表，核心数据 |
| Statement | 对账单记录表 |
| StatementItem | 对账单明细关联表 |

### 路由清单 ✅

| URL | 功能 |
|-----|------|
| `/` | 首页/仪表盘 |
| `/api/companies` | 获取公司列表 (JSON) |
| `/transaction/` | 交易记录列表 |
| `/transaction/new` | 新增交易记录 |
| `/transaction/<id>/edit` | 编辑交易记录 |
| `/transaction/<id>/delete` | 删除交易记录 |
| `/statement/generator` | 对账单生成器 |
| `/statement/<no>` | 查看对账单 |
| `/statement/<no>/export` | 导出对账单 Excel |
| `/statement/list` | 历史对账单列表 |

## 启动方式

### 开发环境
```bash
python run.py
```
访问: http://localhost:5000

### 生产环境
```bash
# 使用 Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:application
```

## 部署到 VPS

1. 上传代码到 VPS
2. 安装依赖: `pip install -r requirements.txt`
3. 运行: `python run.py` (开发) 或使用 Gunicorn (生产)
4. 访问: `http://VPS_IP:5000`

---

*生成时间: 2026-03-05*
