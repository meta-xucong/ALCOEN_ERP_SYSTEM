# ALCOEN ERP v1.0 实施技术指南

> 本文档是代码编写的直接参考资料，包含所有技术细节和实现规范。

---

## 1. 功能需求确认

### 1.1 公司名称管理
- **输入方式**: 自由文本输入
- **智能提示**: 基于历史输入自动补全
- **实现方式**: 
  - 前端: 带自动补全的输入框 (datalist 或 Select2)
  - 后端: 维护 Company 表存储历史公司名称

### 1.2 对账单编号
- **格式**: `DZ` + 年份(4位) + 序号(3位)
- **示例**: `DZ2024001`, `DZ2024002`
- **生成规则**: 
  - 每年从001开始重新编号
  - 根据创建时间自动分配

### 1.3 时间筛选
- **筛选方式**: 起始日期 ~ 结束日期
- **精度**: 精确到日 (YYYY-MM-DD)
- **应用字段**: 发货日期 (delivery_date)
- **逻辑**: 汇总该时间段内的所有订单

### 1.4 对账单模板
- **状态**: v1.0 基础版本，预留美化接口
- **包含元素**: 
  - 公司Logo位置 (预留)
  - 对账单标题
  - 筛选条件摘要
  - 交易明细表格
  - 对账单总金额
  - 页脚信息

---

## 2. 数据库设计

### 2.1 数据表结构

#### companies 表 (公司名称管理)
```sql
CREATE TABLE companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### transactions 表 (交易记录)
```sql
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name VARCHAR(100) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity FLOAT NOT NULL,
    unit VARCHAR(20) NOT NULL,
    price_with_tax FLOAT NOT NULL,
    total_price_with_tax FLOAT NOT NULL,
    invoice_date DATE,
    payment_date DATE,
    contract_no VARCHAR(100),
    delivery_date DATE NOT NULL,
    remark TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### statements 表 (对账单记录)
```sql
CREATE TABLE statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_no VARCHAR(20) NOT NULL UNIQUE,
    company_name VARCHAR(100) NOT NULL,
    filter_start_date DATE,
    filter_end_date DATE,
    filter_products TEXT,  -- JSON格式存储筛选的产品列表
    statement_total FLOAT NOT NULL,
    record_count INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### statement_items 表 (对账单明细关联)
```sql
CREATE TABLE statement_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement_id INTEGER NOT NULL,
    transaction_id INTEGER NOT NULL,
    display_seq INTEGER NOT NULL,
    FOREIGN KEY (statement_id) REFERENCES statements(id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);
```

### 2.2 SQLAlchemy 模型定义

```python
# models.py

from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, Text, Date, Integer, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Company(db.Model):
    """公司名称表 - 用于自动补全"""
    __tablename__ = 'companies'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

class Transaction(db.Model):
    """交易记录表 - 核心数据"""
    __tablename__ = 'transactions'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    price_with_tax: Mapped[float] = mapped_column(Float, nullable=False)
    total_price_with_tax: Mapped[float] = mapped_column(Float, nullable=False)
    invoice_date: Mapped[Date] = mapped_column(Date, nullable=True)
    payment_date: Mapped[Date] = mapped_column(Date, nullable=True)
    contract_no: Mapped[str] = mapped_column(String(100), nullable=True)
    delivery_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联的对账单明细
    statement_items: Mapped[list['StatementItem']] = relationship(back_populates='transaction')

class Statement(db.Model):
    """对账单记录表 - 保存生成的对账单"""
    __tablename__ = 'statements'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    statement_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    filter_start_date: Mapped[Date] = mapped_column(Date, nullable=True)
    filter_end_date: Mapped[Date] = mapped_column(Date, nullable=True)
    filter_products: Mapped[str] = mapped_column(Text, nullable=True)  # JSON
    statement_total: Mapped[float] = mapped_column(Float, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联的明细
    items: Mapped[list['StatementItem']] = relationship(back_populates='statement', cascade='all, delete-orphan')

class StatementItem(db.Model):
    """对账单明细关联表"""
    __tablename__ = 'statement_items'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey('statements.id'), nullable=False)
    transaction_id: Mapped[int] = mapped_column(ForeignKey('transactions.id'), nullable=False)
    display_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    
    statement: Mapped['Statement'] = relationship(back_populates='items')
    transaction: Mapped['Transaction'] = relationship(back_populates='statement_items')

# 自动更新公司名称表
@event.listens_for(Transaction, 'after_insert')
def auto_add_company(mapper, connection, target):
    """当新增交易记录时，自动将公司名称加入公司表"""
    from sqlalchemy import select
    stmt = select(Company).where(Company.name == target.company_name)
    result = connection.execute(stmt).scalar_one_or_none()
    if not result:
        connection.execute(
            Company.__table__.insert(),
            {'name': target.company_name}
        )
```

---

## 3. 业务逻辑实现

### 3.1 对账单编号生成器

```python
# services/statement_service.py

from datetime import datetime
from models import Statement, db

class StatementService:
    
    @staticmethod
    def generate_statement_no() -> str:
        """生成对账单编号
        
        格式: DZ + 年份(4位) + 序号(3位)
        示例: DZ2024001
        """
        current_year = datetime.now().year
        prefix = f"DZ{current_year}"
        
        # 查询今年最大的编号
        latest = Statement.query.filter(
            Statement.statement_no.like(f"{prefix}%")
        ).order_by(Statement.statement_no.desc()).first()
        
        if latest:
            # 提取序号部分并加1
            last_seq = int(latest.statement_no[-3:])
            new_seq = last_seq + 1
        else:
            new_seq = 1
        
        return f"{prefix}{new_seq:03d}"
    
    @staticmethod
    def create_statement(company_name: str, 
                        start_date: datetime.date,
                        end_date: datetime.date,
                        products: list = None) -> dict:
        """创建对账单
        
        Args:
            company_name: 公司名称
            start_date: 起始日期
            end_date: 结束日期
            products: 产品筛选列表 (可选)
        
        Returns:
            包含对账单信息的字典
        """
        from models import Transaction, StatementItem
        import json
        
        # 1. 构建查询
        query = Transaction.query.filter(
            Transaction.company_name == company_name,
            Transaction.delivery_date >= start_date,
            Transaction.delivery_date <= end_date
        )
        
        # 2. 应用产品筛选
        if products:
            query = query.filter(Transaction.product_name.in_(products))
        
        # 3. 按发货日期排序
        transactions = query.order_by(Transaction.delivery_date).all()
        
        if not transactions:
            return None
        
        # 4. 计算总金额
        total_amount = sum(t.total_price_with_tax for t in transactions)
        
        # 5. 生成对账单记录
        statement = Statement(
            statement_no=StatementService.generate_statement_no(),
            company_name=company_name,
            filter_start_date=start_date,
            filter_end_date=end_date,
            filter_products=json.dumps(products) if products else None,
            statement_total=total_amount,
            record_count=len(transactions)
        )
        
        db.session.add(statement)
        db.session.flush()  # 获取statement.id
        
        # 6. 创建明细关联（重新编号）
        for i, trans in enumerate(transactions, 1):
            item = StatementItem(
                statement_id=statement.id,
                transaction_id=trans.id,
                display_seq=i
            )
            db.session.add(item)
        
        db.session.commit()
        
        return {
            'statement': statement,
            'transactions': transactions,
            'display_items': [
                {'seq': i+1, 'transaction': t} 
                for i, t in enumerate(transactions)
            ]
        }
```

### 3.2 自动计算字段

```python
# models.py - Transaction 模型中

from sqlalchemy import event

@event.listens_for(Transaction, 'before_insert')
@event.listens_for(Transaction, 'before_update')
def calculate_total_price(mapper, connection, target):
    """自动计算总含税价格"""
    if target.quantity and target.price_with_tax:
        target.total_price_with_tax = target.quantity * target.price_with_tax
```

---

## 4. API 设计

### 4.1 路由清单

| 方法 | 路由 | 功能 | 说明 |
|------|------|------|------|
| GET | `/` | 首页 | 数据概览 |
| **交易记录管理** ||||
| GET | `/transactions` | 交易列表 | 分页展示 |
| GET | `/transaction/new` | 录入页面 | 表单页面 |
| POST | `/transaction/new` | 提交录入 | 处理表单 |
| GET | `/transaction/<id>/edit` | 编辑页面 | 表单页面 |
| POST | `/transaction/<id>/edit` | 提交编辑 | 处理表单 |
| POST | `/transaction/<id>/delete` | 删除记录 | AJAX/表单 |
| GET | `/api/companies` | 获取公司列表 | JSON，用于自动补全 |
| **对账单功能** ||||
| GET | `/statement/generator` | 对账单生成器 | 筛选表单页面 |
| POST | `/statement/generate` | 生成对账单 | 处理筛选条件 |
| GET | `/statement/<statement_no>` | 查看对账单 | 展示页面 |
| GET | `/statement/<statement_no>/export` | 导出Excel | 下载文件 |
| GET | `/statements` | 历史对账单 | 列表页面 |

### 4.2 API 详细说明

#### GET /api/companies
获取公司名称列表（用于自动补全）

**Response:**
```json
{
    "companies": [
        {"id": 1, "name": "江苏纯安"},
        {"id": 2, "name": "上海XX科技"},
        {"id": 3, "name": "北京YY贸易"}
    ]
}
```

#### POST /statement/generate
生成对账单

**Request:**
```json
{
    "company_name": "江苏纯安",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "products": ["沉子", "柱管"]  // 可选
}
```

**Response:**
```json
{
    "success": true,
    "statement_no": "DZ2024005",
    "redirect_url": "/statement/DZ2024005"
}
```

---

## 5. 页面设计规范

### 5.1 页面布局

所有页面继承 `base.html`，包含：
- 顶部导航栏 (Navbar)
- 主内容区域
- 页脚

### 5.2 导航栏结构

```
┌─────────────────────────────────────────────────────────────┐
│  🏠 ALCOEN ERP                              [首页] [交易记录] [对账单] │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 各页面详细设计

#### 首页 (index.html)
- 快速统计卡片（本月交易数、待回款金额等）
- 最近交易记录（Top 5）
- 快捷操作按钮（录入、生成对账单）

#### 交易录入页面 (transaction_form.html)
```
┌────────────────────────────────────────┐
│  新增交易记录                           │
├────────────────────────────────────────┤
│  公司名称 *  [_______________] [v]     │  ← 自动补全输入框
│  产品名称 *  [_______________]         │
│  数量     *  [____] 单位 [____]        │
│  含税单价 *  [________] 元             │
│  发货日期 *  [____-__-__]              │
│  开票日期    [____-__-__]              │
│  回款日期    [____-__-__]              │
│  合同编号    [____________]            │
│  备注        [____________]            │
│                                        │
│  [  保存  ]   [  取消  ]               │
└────────────────────────────────────────┘
```

#### 对账单生成器 (statement_generator.html)
```
┌──────────────────────────────────────────────────────────────┐
│  对账单生成器                                                  │
├──────────────────────────────────────────────────────────────┤
│  选择公司 *                                                  │
│  [公司名称输入框 ▼]  ← 自动补全，必选                         │
│                                                              │
│  时间范围 *                                                  │
│  从 [2024-01-01] 到 [2024-12-31]                             │
│                                                              │
│  产品筛选（可选）                                             │
│  ☑ 全选                                                      │
│  ☑ 沉子     ☑ 柱管    ☑ C8填料                               │
│  ☑ C18填料  ☑ 其他                                           │
│                                                              │
│            [    生成对账单    ]                               │
└──────────────────────────────────────────────────────────────┘
```

#### 对账单展示页面 (statement_result.html)
```
┌──────────────────────────────────────────────────────────────┐
│  [Logo位置]                                                  │
│                                                              │
│                    对账单                                     │
│                                                              │
│  对账单号：DZ2024001                                          │
│  客户名称：江苏纯安                                            │
│  时间范围：2024年1月1日 - 2024年12月31日                       │
│                                                              │
│  ┌────┬──────────────┬────┬────┬─────┬────────┬──────────┐  │
│  │序号│ 名称及型号   │数量│单位│单价 │ 小计   │发货日期  │  │
│  ├────┼──────────────┼────┼────┼─────┼────────┼──────────┤  │
│  │ 1  │ 沉子 三阶20um│ 36 │ 个 │ 45  │ 1620   │2024-06-17│  │
│  │ 2  │ 柱管 4.6*250│100 │ 套 │ 110 │ 11000  │2024-03-18│  │
│  └────┴──────────────┴────┴────┴─────┴────────┴──────────┘  │
│                                                              │
│                              对账单总金额：12,620 元          │
│                                                              │
│  [导出Excel]  [打印]  [返回]                                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Excel 导出格式

### 6.1 对账单 Excel 模板结构

| 行 | 内容 |
|----|------|
| 1 | [Logo] 公司名称 |
| 2 | 对账单 |
| 3 | 对账单号: DZ2024001 |
| 4 | 客户名称: XXX公司 |
| 5 | 时间范围: XXXX-XX-XX 至 XXXX-XX-XX |
| 6 | （空行） |
| 7 | 表头: 序号, 名称及型号, 数量, 单位, 含税单价, 小计, 发货日期 |
| 8+ | 数据行 |
| 最后一行+2 | 对账单总金额: XXXX 元 |

### 6.2 Excel 导出代码规范

```python
# utils/excel_export.py

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side
from datetime import datetime

def export_statement_to_excel(statement, transactions, output_path):
    """导出对账单为Excel文件
    
    Args:
        statement: Statement 对象
        transactions: Transaction 列表
        output_path: 输出文件路径
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "对账单"
    
    # 设置列宽
    ws.column_dimensions['A'].width = 8   # 序号
    ws.column_dimensions['B'].width = 25  # 名称及型号
    ws.column_dimensions['C'].width = 10  # 数量
    ws.column_dimensions['D'].width = 8   # 单位
    ws.column_dimensions['E'].width = 12  # 含税单价
    ws.column_dimensions['F'].width = 12  # 小计
    ws.column_dimensions['G'].width = 12  # 发货日期
    
    # 标题行（预留Logo位置）
    ws.merge_cells('A1:G1')
    ws['A1'] = '对账单'
    ws['A1'].font = Font(size=16, bold=True)
    ws['A1'].alignment = Alignment(horizontal='center')
    
    # 对账单信息
    ws['A3'] = f'对账单号：{statement.statement_no}'
    ws['A4'] = f'客户名称：{statement.company_name}'
    ws['A5'] = f'时间范围：{statement.filter_start_date} 至 {statement.filter_end_date}'
    
    # 表头
    headers = ['序号', '名称及型号', '数量', '单位', '含税单价', '小计', '发货日期']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=7, column=col, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')
    
    # 数据行
    row_num = 8
    for i, trans in enumerate(transactions, 1):
        ws.cell(row=row_num, column=1, value=i)
        ws.cell(row=row_num, column=2, value=trans.product_name)
        ws.cell(row=row_num, column=3, value=trans.quantity)
        ws.cell(row=row_num, column=4, value=trans.unit)
        ws.cell(row=row_num, column=5, value=trans.price_with_tax)
        ws.cell(row=row_num, column=6, value=trans.total_price_with_tax)
        ws.cell(row=row_num, column=7, value=trans.delivery_date.strftime('%Y-%m-%d'))
        row_num += 1
    
    # 总金额
    total_row = row_num + 1
    ws.merge_cells(f'A{total_row}:E{total_row}')
    ws[f'A{total_row}'] = '对账单总金额：'
    ws[f'A{total_row}'].alignment = Alignment(horizontal='right')
    ws[f'F{total_row}'] = statement.statement_total
    ws[f'F{total_row}'].font = Font(bold=True, size=12)
    
    wb.save(output_path)
    return output_path
```

---

## 7. 配置文件

### config.py

```python
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

class Config:
    """基础配置"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{os.path.join(DATA_DIR, "erp.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 分页配置
    ITEMS_PER_PAGE = 20
    
    # 文件上传/导出
    EXPORT_FOLDER = os.path.join(BASE_DIR, 'exports')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

class DevelopmentConfig(Config):
    """开发环境"""
    DEBUG = True

class ProductionConfig(Config):
    """生产环境"""
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
```

---

## 8. 部署配置

### 8.1 requirements.txt

```
Flask==3.0.0
Flask-SQLAlchemy==3.1.1
Flask-WTF==1.2.1
WTForms==3.1.1
pandas==2.1.4
openpyxl==3.1.2
python-dateutil==2.8.2
gunicorn==21.2.0
```

### 8.2 启动文件

#### run.py (开发)
```python
from app import create_app, db
from app.models import Company, Transaction, Statement, StatementItem

app = create_app('development')

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'Company': Company,
        'Transaction': Transaction,
        'Statement': Statement,
        'StatementItem': StatementItem
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
```

#### wsgi.py (生产)
```python
from app import create_app

application = create_app('production')
```

---

## 9. 开发顺序建议

按以下顺序实现功能：

1. **Day 1**: 基础框架搭建
   - 项目结构创建
   - 配置文件
   - 数据库模型 (Company, Transaction)
   - 基础页面模板

2. **Day 2**: 交易记录CRUD
   - 录入功能（含公司自动补全）
   - 列表展示
   - 编辑/删除

3. **Day 3**: 对账单功能
   - 对账单生成器页面
   - 筛选逻辑实现
   - 对账单展示页面
   - 编号生成器

4. **Day 4**: 导出与优化
   - Excel导出功能
   - 历史对账单列表
   - UI美化

---

## 10. 注意事项

1. **数据验证**: 所有表单字段必须做后端验证
2. **日期处理**: 使用 Python datetime.date 类型
3. **浮点精度**: 金额计算使用 Decimal 或注意精度问题
4. **并发考虑**: SQLite 在写入时加锁，避免并发写入冲突
5. **自动补全**: 公司名称输入框需要防抖处理

---

*文档版本: v1.0*  
*创建日期: 2026-03-05*  
*关联文档: ERP_System_Technical_Proposal.md*
