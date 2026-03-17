# ALCOEN ERP v1.2 更新日志

## 更新日期
2026-03-10

## 已完成功能

### [LOGIC-7] 拆分完成状态
- **新增字段**: `Contract.delivery_status` 和 `Contract.payment_status`
  - `delivery_status`: pending/partial/completed（发货状态）
  - `payment_status`: pending/partial/completed（回款状态）
  
- **数据库迁移**: `migrate_v1.2_status_split.py`
  - 添加 `delivery_status` 字段 (VARCHAR(20), DEFAULT 'pending')
  - 添加 `payment_status` 字段 (VARCHAR(20), DEFAULT 'pending')
  - 初始化现有合同的拆分状态
  
- **业务逻辑更新**: `ContractService.check_completion()`
  - 分别计算发货完成度和回款完成度
  - 根据数量计算发货状态
  - 根据回款金额计算回款状态
  - 记录状态变更日志
  
- **统计信息更新**: `ContractService.get_statistics()`
  - 新增 `total_paid_value`: 已回款金额
  - 新增 `total_unpaid_value`: 未回款金额
  - 返回 `delivery_status` 和 `payment_status`
  
- **界面更新**:
  - 合同列表页: 显示两个状态badge（发货+回款）
  - 合同详情页: 顶部分别显示发货/回款状态，统计区域拆分为发货情况和回款情况两部分

### [LOGIC-8] 对账单生成器多维度筛选
- **新增筛选条件**:
  - `contract_no`: 合同编号（模糊匹配）
  - `product_codes`: 产品编码列表（精确匹配，多个逗号分隔）
  - `product_names`: 产品名称列表（模糊匹配）
  - `company_name`: 公司名称（改为可选）
  - `start_date/end_date`: 日期范围（改为可选）
  
- **筛选规则**:
  - 所有条件为 "与" 关系（AND）
  - 至少需要一个筛选条件
  - 不选公司则匹配所有公司（支持跨公司查询）
  
- **表单更新**: `StatementGeneratorForm`
  - 新增 `contract_no` 字段
  - 新增 `product_code_filter` 字段
  - 公司名和日期改为可选验证
  
- **界面更新**:
  - 生成器页面: 两列布局，显示所有筛选字段
  - 结果页面: 显示筛选条件区域
  
### 其他修复
- [BUG-1] 发货数量不能超过合同数量 - 已在 `ContractService.add_transaction()` 中验证
- [LOGIC-6] 允许数量为0的回款记录（预收款场景）- 已支持
- [BUG-5] 交易行删除按钮 - 已添加

## 文件变更清单

### 新增文件
- `migrate_v1.2_status_split.py` - 状态拆分数据库迁移脚本

### 修改文件

#### 模型层
- `app/models.py`
  - `Contract` 模型: 添加 `delivery_status`, `payment_status` 字段
  - 添加 `get_delivery_status_display()`, `get_payment_status_display()` 方法

#### 服务层
- `app/services/contract_service.py`
  - `check_completion()`: 改为返回拆分状态字典
  - `get_statistics()`: 添加回款统计
  
- `app/services/statement_service.py`
  - `create_statement()`: 支持多维度筛选参数
  - `get_statement_by_no()`: 返回 `filter_conditions` 字典

#### 表单层
- `app/forms.py`
  - `StatementGeneratorForm`: 新增字段，修改验证规则

#### 路由层
- `app/routes/statement.py`
  - `generator()`: 处理新筛选条件
  - `view_statement()`: 传递 `filter_conditions`

#### 模板层
- `templates/contract/list.html`: 显示拆分状态
- `templates/contract/detail.html`: 显示拆分状态和统计
- `templates/statement/generator.html`: 多维度筛选表单
- `templates/statement/result.html`: 显示筛选条件

## 待办事项
- [ ] [BUG-2] 编辑合同表单需要完善 - 产品列表和交易记录编辑
- [ ] 历史合同页面 - 合同列表展示（已存在于 /contract/list）
- [ ] 产品图片上传功能完善

## 数据库结构变更

```sql
-- contracts 表新增字段
ALTER TABLE contracts ADD COLUMN delivery_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE contracts ADD COLUMN payment_status VARCHAR(20) DEFAULT 'pending';
```

## 测试建议

1. **状态拆分测试**:
   - 创建一个合同，添加部分发货记录，验证 delivery_status = partial
   - 添加回款记录，验证 payment_status 变化
   - 全部发货完成后验证 delivery_status = completed

2. **多维度筛选测试**:
   - 只输入合同编号查询
   - 只输入产品编码查询（跨公司）
   - 组合条件：公司+合同+产品编码
   - 验证所有条件为AND关系
