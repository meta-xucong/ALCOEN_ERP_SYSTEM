# ALCOEN ERP v1.2 升级任务清单

> 核心变更：从"交易记录"模式升级为"合同-交易记录"父子模式

---

## 升级概览

```
┌─────────────────────────────────────────────────────────────────┐
│                      v1.2 架构图                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Contract (合同)                                                  │
│  ├── contract_no (合同编号) *必填                                │
│  ├── company_name (公司名称)                                     │
│  ├── status (状态): 未完成/已完成                                │
│  ├── total_value (合同总价)                                      │
│  ├── remark (备注) - 自动记录修改时间                            │
│  │                                                               │
│  ├── ContractProducts (发货产品总数) 1:N                         │
│  │   ├── product_code                                            │
│  │   ├── product_name                                            │
│  │   ├── quantity (计划数量)                                     │
│  │   ├── unit                                                    │
│  │   ├── price (单价)                                            │
│  │   └── total (总价)                                            │
│  │                                                               │
│  └── Transactions (交易记录) 1:N                                 │
│      ├── contract_product_id (关联计划产品)                      │
│      ├── quantity (实际发货数量)                                 │
│      ├── unit                                                    │
│      ├── price (实际单价)                                        │
│      ├── delivery_date                                           │
│      ├── invoice_date                                            │
│      ├── payment_date                                            │
│      ├── payment_amount (回款金额)                               │
│      └── remark                                                  │
│                                                                   │
│  统计模块（自动计算）:                                            │
│  ├── 按产品汇总: 已发货数量、未发货数量                          │
│  ├── 按产品汇总: 已发货货值、未发货货值                          │
│  └── 合同完成状态: 未发货=0时标记已完成                          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: 数据库模型变更

### Task 1.1: 新建 Contract 模型
**文件**: `app/models.py`

```python
class Contract(db.Model):
    """合同表 - v1.2 核心"""
    __tablename__ = 'contracts'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')  # pending/completed
    total_value: Mapped[float] = mapped_column(Float, default=0)
    remark: Mapped[Text] = mapped_column(Text, nullable=True)  # 自动记录修改日志
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    contract_products: Mapped[list['ContractProduct']] = relationship(back_populates='contract', cascade='all, delete-orphan')
    transactions: Mapped[list['Transaction']] = relationship(back_populates='contract')
```

### Task 1.2: 新建 ContractProduct 模型（发货产品总数）
**文件**: `app/models.py`

```python
class ContractProduct(db.Model):
    """合同产品计划 - 发货产品总数"""
    __tablename__ = 'contract_products'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), nullable=False)
    product_code: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name: Mapped[str] = mapped_column(String(100), nullable=True)
    product_model: Mapped[str] = mapped_column(String(100), nullable=True)
    product_type: Mapped[str] = mapped_column(String(50), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)  # 计划数量
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)  # 单价
    total: Mapped[float] = mapped_column(Float, nullable=False)  # 总价
    
    # 关联
    contract: Mapped['Contract'] = relationship(back_populates='contract_products')
    transactions: Mapped[list['Transaction']] = relationship(back_populates='contract_product')
```

### Task 1.3: 修改 Transaction 模型（添加合同关联）
**文件**: `app/models.py`

```python
class Transaction(db.Model):
    """交易记录 - v1.2 关联合同"""
    # ... 原有字段 ...
    
    # v1.2: 新增合同关联
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), nullable=True)
    contract_product_id: Mapped[int] = mapped_column(ForeignKey('contract_products.id'), nullable=True)
    payment_amount: Mapped[float] = mapped_column(Float, nullable=True)  # 回款金额
    
    # 关联
    contract: Mapped['Contract'] = relationship(back_populates='transactions')
    contract_product: Mapped['ContractProduct'] = relationship(back_populates='transactions')
```

### Task 1.4: 数据迁移脚本
**文件**: `migrate_v1.1_to_v1.2.py`

- 创建 contracts 表
- 创建 contract_products 表
- 修改 transactions 表（添加 contract_id）
- 将现有交易记录迁移为单合同模式（每个交易生成一个合同）

---

## Phase 2: 业务逻辑层 (Services)

### Task 2.1: 创建 ContractService
**文件**: `app/services/contract_service.py`

```python
class ContractService:
    """合同服务类"""
    
    @staticmethod
    def create_contract(data, contract_products_data):
        """创建合同及发货产品计划"""
        pass
    
    @staticmethod
    def update_contract(contract_id, data):
        """更新合同基础信息"""
        pass
    
    @staticmethod
    def add_transaction(contract_id, transaction_data):
        """向合同添加交易记录"""
        pass
    
    @staticmethod
    def get_statistics(contract_id):
        """
        获取合同统计信息
        
        Returns:
            {
                'products': [
                    {
                        'product_code': 'P0001',
                        'product_name': '产品A',
                        'planned_qty': 100,      # 计划数量
                        'delivered_qty': 60,      # 已发货数量
                        'remaining_qty': 40,      # 未发货数量
                        'planned_value': 10000,   # 计划货值
                        'delivered_value': 6000,  # 已发货货值
                        'remaining_value': 4000   # 未发货货值
                    }
                ],
                'total_planned': 10000,
                'total_delivered': 6000,
                'total_remaining': 4000,
                'is_completed': False
            }
        """
        pass
    
    @staticmethod
    def check_completion(contract_id):
        """检查合同是否完成，更新状态"""
        pass
    
    @staticmethod
    def append_remark(contract_id, message):
        """向合同备注追加修改记录"""
        # 格式: [2024-03-06 14:30:15] 修改内容
        pass
```

### Task 2.2: 修改 TransactionService（适配合同模式）
**文件**: `app/services/transaction_service.py`

- 修改 `create_transaction` 支持 contract_id
- 修改查询方法支持按合同筛选

---

## Phase 3: 表单 (Forms)

### Task 3.1: 创建 ContractForm
**文件**: `app/forms.py`

```python
class ContractForm(FlaskForm):
    """合同基础信息表单"""
    contract_no = StringField('合同编号 *', validators=[DataRequired()])
    company_name = StringField('公司名称 *', validators=[DataRequired()])
    total_value = FloatField('合同总价')
    remark = TextAreaField('备注')
    submit = SubmitField('保存合同')

class ContractProductForm(FlaskForm):
    """合同产品计划表单（动态多条）"""
    product_select_mode = RadioField(choices=[('existing', '现有'), ('manual', '手动')])
    product_id = SelectField('产品编码')
    product_code = StringField('产品编码 *')
    product_name = StringField('产品名称')
    product_model = StringField('产品型号')
    product_type = StringField('产品类型')
    quantity = FloatField('数量 *')
    unit = StringField('单位 *')
    price = FloatField('含税单价 *')
    total = FloatField('总价', render_kw={'readonly': True})

class ContractTransactionForm(FlaskForm):
    """合同交易记录表单（动态多条）"""
    contract_product_id = SelectField('选择产品 *')  # 从合同产品中选择
    quantity = FloatField('发货数量 *')
    unit = StringField('单位')
    price = FloatField('含税单价')
    total = FloatField('小计', render_kw={'readonly': True})
    payment_amount = FloatField('回款金额')
    delivery_date = DateField('发货日期')
    invoice_date = DateField('开票日期')
    payment_date = DateField('回款日期')
    remark = StringField('备注')
```

---

## Phase 4: 路由 (Routes)

### Task 4.1: 创建 Contract 路由
**文件**: `app/routes/contract.py`

```python
contract_bp = Blueprint('contract', __name__, url_prefix='/contract')

@contract_bp.route('/')
def list_contracts():
    """合同列表 - 原交易记录列表位置"""
    pass

@contract_bp.route('/new', methods=['GET', 'POST'])
def new_contract():
    """
    新增合同页面
    
    包含:
    - 合同基础信息（编号、公司）
    - 发货产品总数（动态添加多条）
    - 交易记录（动态添加多条，可折叠）
    - 统计模块（实时计算）
    """
    pass

@contract_bp.route('/<int:id>')
def view_contract(id):
    """查看合同详情"""
    pass

@contract_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit_contract(id):
    """编辑合同 - 可继续添加交易记录"""
    pass

@contract_bp.route('/<int:id>/delete', methods=['POST'])
def delete_contract(id):
    """删除合同（级联删除产品和交易记录）"""
    pass

# API for dynamic operations
@contract_bp.route('/api/calculate-stats/<int:id>')
def api_calculate_stats(id):
    """AJAX: 实时计算统计信息"""
    pass
```

### Task 4.2: 更新应用入口
**文件**: `app/__init__.py`

- 注册 contract 蓝图
- 更新导航栏："交易记录" → "交易合同"

---

## Phase 5: 前端模板 (Templates)

### Task 5.1: 创建合同列表页面
**文件**: `templates/contract/list.html`

- 显示合同编号、公司、状态标记（绿/蓝）、总价
- 筛选：按合同编号、公司、状态
- 操作：查看、编辑、删除

### Task 5.2: 创建合同表单页面（核心）
**文件**: `templates/contract/form.html`

**页面结构**:
```
┌─────────────────────────────────────────┐
│  新增合同                                │
├─────────────────────────────────────────┤
│  合同信息                                │
│  ├── 合同编号 * [________]              │
│  └── 公司名称 * [________▼]             │
├─────────────────────────────────────────┤
│  发货产品总数                            │
│  ┌─────────────────────────────────┐   │
│  │ 产品1: P0001 - 沉子             │   │
│  │ 数量: [100] 单位: [个] 单价: [45] │   │
│  │ 总价: [4500]                     │   │
│  └─────────────────────────────────┘   │
│  [+ 添加产品]                           │
├─────────────────────────────────────────┤
│  交易记录 [展开/折叠 ▼]                 │
│  ┌─────────────────────────────────┐   │
│  │ 记录1: ▼ P0001 - 沉子            │   │
│  │   发货数量: [60]                 │   │
│  │   回款金额: [2700]               │   │
│  │   发货日期: [2024-03-01]         │   │
│  │   ...                            │   │
│  └─────────────────────────────────┘   │
│  [+ 新增交易记录]                       │
├─────────────────────────────────────────┤
│  📊 统计                                 │
│  ┌─────────────────────────────────┐   │
│  │ 产品    计划   已发   未发   货值  │   │
│  │ P0001   100    60     40    4500  │   │
│  │ ...                              │   │
│  │ 状态: 🔴 未完成                   │   │
│  └─────────────────────────────────┘   │
├─────────────────────────────────────────┤
│  📝 备注                                 │
│  [自动记录]                              │
│  [2024-03-06 10:00:00] 创建合同         │
├─────────────────────────────────────────┤
│  [返回]  [保存合同]                      │
└─────────────────────────────────────────┘
```

**关键交互**:
- 动态添加/删除产品计划行
- 交易记录可折叠（默认展开第一条）
- 选择产品时从上面已添加的产品中选择
- 实时计算总价、统计信息
- 自动更新完成状态标记

### Task 5.3: 创建合同详情页面
**文件**: `templates/contract/detail.html`

- 显示完整合同信息
- 产品计划清单
- 交易记录列表（时间线形式）
- 统计信息图表
- 备注日志

### Task 5.4: 更新导航栏
**文件**: `templates/base.html`

- "交易记录" → "交易合同"
- 下拉菜单调整

---

## Phase 6: JavaScript 交互逻辑

### Task 6.1: 动态表单管理
**文件**: `static/js/contract_form.js`

```javascript
// 功能列表:

// 1. 动态添加/删除产品计划行
function addContractProductRow() {}
function removeContractProductRow(index) {}

// 2. 动态添加/删除/折叠交易记录
function addTransactionRow() {}  // 展开新行
function toggleTransactionRow(index) {}  // 折叠/展开
function removeTransactionRow(index) {}

// 3. 产品选择联动
// 当在交易记录中选择产品时，自动填充信息
function onProductSelect(transactionIndex, contractProductId) {}

// 4. 自动计算
function calculateProductTotal(index) {}  // 数量*单价=总价
function calculateContractTotal() {}  // 所有产品总价之和
function calculateStatistics() {}  // 已发/未发统计

// 5. 实时检查完成状态
function checkCompletionStatus() {
    // 如果所有未发货数量=0，标记为已完成
}

// 6. 备注自动追加
function appendRemark(message) {
    const now = new Date().toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai'});
    const remark = `[${now}] ${message}\n` + document.getElementById('remark').value;
    document.getElementById('remark').value = remark;
}
```

### Task 6.2: AJAX API 调用
**文件**: `static/js/contract_api.js`

```javascript
// 实时获取统计信息
async function fetchStatistics(contractId) {
    const response = await fetch(`/contract/api/calculate-stats/${contractId}`);
    return await response.json();
}

// 保存时更新备注
async function saveWithRemark(contractId, data, action) {
    appendRemark(`执行操作: ${action}`);
    // 提交表单
}
```

---

## Phase 7: Excel 导出更新

### Task 7.1: 合同导出
**文件**: `app/utils/excel_export.py`

```python
def export_contract_to_excel(contract, output_path):
    """导出合同为Excel"""
    # Sheet 1: 合同信息
    # Sheet 2: 发货产品计划
    # Sheet 3: 交易记录明细
    # Sheet 4: 统计汇总
```

---

## Phase 8: 数据迁移

### Task 8.1: 迁移脚本
**文件**: `migrate_v1.1_to_v1.2.py`

```python
def migrate():
    """
    迁移策略:
    1. 为每个现有交易记录创建一个合同
    2. 合同编号 = 原交易记录ID 或自动生成
    3. 创建对应的 ContractProduct
    4. 关联 Transaction 到 Contract
    """
```

---

## 开发顺序建议

### Week 1: 基础架构
- [ ] Task 1.1-1.4: 数据库模型
- [ ] Task 2.1-2.2: Service 层
- [ ] Task 3.1: Forms

### Week 2: 后端逻辑
- [ ] Task 4.1-4.2: 路由
- [ ] Task 7.1: Excel导出

### Week 3: 前端开发（核心）
- [ ] Task 5.1: 列表页面
- [ ] Task 5.2: 表单页面（最复杂）
- [ ] Task 6.1-6.2: JavaScript

### Week 4: 测试优化
- [ ] Task 8.1: 数据迁移
- [ ] Task 5.3: 详情页面
- [ ] 全量测试

---

## 关键复杂度提示

| 功能 | 复杂度 | 说明 |
|------|--------|------|
| 动态表单（产品+交易记录） | ⭐⭐⭐⭐⭐ | 需要动态添加/删除/折叠 |
| 实时统计计算 | ⭐⭐⭐⭐ | JavaScript 实时更新 DOM |
| 产品选择联动 | ⭐⭐⭐⭐ | 交易记录从产品计划中选择 |
| 自动备注 | ⭐⭐ | 简单字符串拼接 |
| 完成状态标记 | ⭐⭐⭐ | 根据统计结果自动判断 |

---

*文档版本: v1.2*  
*创建日期: 2026-03-06*  
*状态: 待开发*
