# ALCOEN ERP v1.1 升级方案（最终修订版 - 产品编码为核心）

> 本文档详细描述从 v1.0 到 v1.1 的功能升级实施方案
> 
> **关键变更**：
> 1. 以"产品编码"作为产品唯一标识
> 2. **产品名称不唯一** - 同一编码可对应不同名称
> 3. **交易录入时修改产品信息不入库** - 仅影响当前交易记录
> 4. **产品库编辑独立** - 只能通过产品库页面修改产品信息

---

## 升级概览

| 序号 | 功能需求 | 涉及文件 | 复杂度 |
|------|---------|---------|--------|
| 1 | 新增产品库功能（产品编码唯一） | models.py, forms.py, routes/product.py | 3星 |
| 2 | 交易记录增加产品编码字段 | models.py, forms.py, templates/transaction/ | 3星 |
| 3 | 录入页面产品编码下拉+自动填充 | forms.py, templates/transaction/form.html | 4星 |
| 4 | 自动产品入库逻辑（修订版） | services/product_service.py, routes/transaction.py | 5星 |
| 5 | 增加发货日期、产品编码检索 | routes/transaction.py, templates/transaction/list.html | 2星 |
| 6 | 多维度对账单生成 | services/statement_service.py, routes/statement.py | 4星 |

---

## 重要逻辑说明

### 产品入库规则（修订后）

```
┌─────────────────────────────────────────────────────────────────┐
│  用户在交易录入页面手动输入产品编码                                │
│                           │                                      │
│                           ▼                                      │
│              ┌──────────────────────┐                           │
│              │  产品编码是否已存在？  │                           │
│              └──────────┬───────────┘                           │
│                    是 /      \ 否                                │
│                      /        \                                  │
│                     ▼          ▼                                 │
│        ┌──────────────┐   ┌──────────────┐                      │
│        │  匹配产品库   │   │  创建新产品   │                      │
│        │  读取默认值   │   │  入库产品库   │                      │
│        └──────┬───────┘   └──────┬───────┘                      │
│               │                   │                              │
│               ▼                   ▼                              │
│  ┌─────────────────────────────────────────┐                    │
│  │  用户可修改：名称、型号、类型、单价       │                    │
│  │  修改结果：                              │                    │
│  │  • 仅保存到当前交易记录                   │                    │
│  │  • 不更新产品库数据                       │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                 │
│  ⚠️ 重要：修改产品库数据必须通过产品库编辑页面                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. 数据库模型变更

### 1.1 新增 Product 模型

```python
# models.py

class Product(db.Model):
    """产品库 - 以产品编码为唯一标识"""
    __tablename__ = 'products'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # 产品编码 - 唯一标识（核心字段）
    product_code: Mapped[str] = mapped_column(
        String(50), 
        unique=True, 
        nullable=False, 
        index=True,
        comment='产品编码，唯一标识'
    )
    
    # 其他字段作为默认值
    product_name: Mapped[str] = mapped_column(String(100), nullable=True)
    product_model: Mapped[str] = mapped_column(String(100), nullable=True)
    product_type: Mapped[str] = mapped_column(String(50), nullable=True)
    default_price: Mapped[float] = mapped_column(Float, nullable=True)
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    image_path: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联的交易记录
    transactions: Mapped[list['Transaction']] = relationship(back_populates='product')
    
    def __repr__(self):
        return f'<Product {self.product_code}>'
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'product_code': self.product_code,
            'product_name': self.product_name,
            'product_model': self.product_model,
            'product_type': self.product_type,
            'default_price': self.default_price,
            'remark': self.remark
        }
```

### 1.2 修改 Transaction 模型

```python
# models.py - Transaction 模型修改

class Transaction(db.Model):
    """交易记录表 - v1.1 产品编码版"""
    __tablename__ = 'transactions'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # v1.1: 产品编码为核心
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'), nullable=True)
    product_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # 产品信息字段（独立于产品库，允许同一编码不同名称）
    product_name: Mapped[str] = mapped_column(String(100), nullable=True)
    product_model: Mapped[str] = mapped_column(String(100), nullable=True)
    product_type: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # 原有字段
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
    
    # 关联关系
    product: Mapped['Product'] = relationship(back_populates='transactions')
    statement_items: Mapped[list['StatementItem']] = relationship(back_populates='transaction')
```

### 1.3 数据迁移策略

```python
# migration_v1.0_to_v1.1.py

def migrate_data():
    """执行数据迁移"""
    from app import create_app, db
    from app.models import Transaction, Product
    
    app = create_app()
    with app.app_context():
        # 创建默认产品 "0"
        default_product = Product.query.filter_by(product_code="0").first()
        if not default_product:
            default_product = Product(
                product_code="0",
                product_name="待分类产品",
                product_model=None,
                product_type=None,
                default_price=0,
                remark="v1.0 迁移的默认产品，请后续手动修改"
            )
            db.session.add(default_product)
            db.session.flush()
            print("创建默认产品 '0'")
        
        # 迁移交易记录
        transactions = Transaction.query.all()
        for trans in transactions:
            trans.product_code = "0"
            trans.product_id = default_product.id
            # product_model 和 product_type 保持为空
        
        db.session.commit()
        print(f"成功迁移 {len(transactions)} 条交易记录")
```

---

## 2. 业务逻辑实现（修订版）

### 2.1 ProductService（关键修订）

```python
# services/product_service.py

import os
from typing import Optional, Tuple
from werkzeug.utils import secure_filename
from app import db
from app.models import Product

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


class ProductService:
    """产品库服务类 - 以产品编码为唯一标识"""
    
    @staticmethod
    def allowed_file(filename: str) -> bool:
        """检查文件扩展名是否允许"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    
    @staticmethod
    def save_image(file, upload_folder: str) -> Optional[str]:
        """保存上传的图片"""
        if file and ProductService.allowed_file(file.filename):
            filename = secure_filename(file.filename)
            import time
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(time.time())}{ext}"
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            return filename
        return None
    
    @staticmethod
    def find_product_by_code(product_code: str) -> Optional[Product]:
        """
        根据编码查找产品
        
        Returns:
            找到返回 Product，未找到返回 None
        """
        return Product.query.filter_by(product_code=product_code).first()
    
    @staticmethod
    def create_product(
        product_code: str,
        product_name: Optional[str] = None,
        product_model: Optional[str] = None,
        product_type: Optional[str] = None,
        default_price: Optional[float] = None,
        remark: Optional[str] = None,
        image_path: Optional[str] = None
    ) -> Product:
        """
        创建新产品
        
        注意：此方法只创建新产品，不检查编码是否已存在
        调用前应先使用 find_product_by_code 检查
        """
        product = Product(
            product_code=product_code,
            product_name=product_name,
            product_model=product_model,
            product_type=product_type,
            default_price=default_price,
            remark=remark or "从交易记录自动创建",
            image_path=image_path
        )
        db.session.add(product)
        db.session.commit()
        return product
    
    @staticmethod
    def get_or_create_product(
        product_code: str,
        product_name: Optional[str] = None,
        product_model: Optional[str] = None,
        product_type: Optional[str] = None,
        default_price: Optional[float] = None
    ) -> Tuple[Product, bool]:
        """
        获取或创建产品
        
        Returns:
            Tuple[Product, bool] - (产品对象, 是否新创建)
        
        重要规则：
        - 如果产品编码已存在：返回现有产品，不更新数据，is_new=False
        - 如果产品编码不存在：创建新产品，入库，is_new=True
        """
        # 先查找
        existing = ProductService.find_product_by_code(product_code)
        if existing:
            # 已存在，直接返回，不更新任何数据
            return existing, False
        
        # 不存在，创建新产品
        new_product = ProductService.create_product(
            product_code=product_code,
            product_name=product_name,
            product_model=product_model,
            product_type=product_type,
            default_price=default_price
        )
        return new_product, True
    
    @staticmethod
    def update_product(
        product_id: int,
        product_name: Optional[str] = None,
        product_model: Optional[str] = None,
        product_type: Optional[str] = None,
        default_price: Optional[float] = None,
        remark: Optional[str] = None,
        image_path: Optional[str] = None
    ) -> Product:
        """
        更新产品信息
        
        此方法仅用于产品库编辑页面
        交易录入页面的修改不调用此方法
        """
        product = Product.query.get(product_id)
        if not product:
            raise ValueError(f"产品ID {product_id} 不存在")
        
        if product_name is not None:
            product.product_name = product_name
        if product_model is not None:
            product.product_model = product_model
        if product_type is not None:
            product.product_type = product_type
        if default_price is not None:
            product.default_price = default_price
        if remark is not None:
            product.remark = remark
        if image_path is not None:
            product.image_path = image_path
        
        db.session.commit()
        return product
    
    @staticmethod
    def get_all_products() -> list:
        """获取所有产品"""
        return Product.query.order_by(Product.product_code).all()
    
    @staticmethod
    def get_product_by_id(product_id: int) -> Optional[Product]:
        """根据ID获取产品"""
        return Product.query.get(product_id)
    
    @staticmethod
    def get_product_choices() -> list:
        """获取产品选项列表（用于下拉框）"""
        products = Product.query.order_by(Product.product_code).all()
        choices = [(0, '-- 请选择产品编码 --')]
        for p in products:
            display = p.product_code
            if p.product_name:
                display += f" - {p.product_name}"
            if p.product_model:
                display += f" ({p.product_model})"
            choices.append((p.id, display))
        return choices
    
    @staticmethod
    def search_products(keyword: str) -> list:
        """搜索产品（支持编码、名称、型号模糊搜索）"""
        from sqlalchemy import or_
        return Product.query.filter(
            or_(
                Product.product_code.contains(keyword),
                Product.product_name.contains(keyword),
                Product.product_model.contains(keyword)
            )
        ).order_by(Product.product_code).all()
    
    @staticmethod
    def check_code_exists(product_code: str) -> bool:
        """检查产品编码是否已存在"""
        return Product.query.filter_by(product_code=product_code).first() is not None
```

---

## 3. 交易记录创建逻辑（关键）

```python
# routes/transaction.py - new_transaction 方法

@transaction_bp.route('/new', methods=['GET', 'POST'])
def new_transaction():
    """新增交易记录 - v1.1 修订版"""
    form = TransactionForm()
    form.product_id.choices = ProductService.get_product_choices()
    
    if form.validate_on_submit():
        try:
            product_code = None
            product_name = None
            product_model = None
            product_type = None
            price = None
            product_id = None
            
            # 获取产品编码和相关信息
            if form.product_select_mode.data == 'existing' and form.product_id.data:
                # ===== 从产品库选择 =====
                product = ProductService.get_product_by_id(form.product_id.data)
                if product:
                    product_code = product.product_code
                    # 从产品库获取默认值
                    product_name = product.product_name
                    product_model = product.product_model
                    product_type = product.product_type
                    price = form.price_with_tax.data or product.default_price
                    product_id = product.id
                else:
                    flash('选择的产品不存在', 'error')
                    return render_template('transaction/form.html', form=form, ...)
            
            else:
                # ===== 手动输入 =====
                product_code = form.product_code.data
                
                # 获取或创建产品（关键逻辑）
                product, is_new = ProductService.get_or_create_product(
                    product_code=product_code,
                    product_name=form.product_name.data,
                    product_model=form.product_model.data,
                    product_type=form.product_type.data,
                    default_price=form.price_with_tax.data
                )
                
                product_id = product.id
                
                if is_new:
                    # 新产品：使用用户输入的数据
                    product_name = form.product_name.data
                    product_model = form.product_model.data
                    product_type = form.product_type.data
                    price = form.price_with_tax.data
                    flash(f'已自动创建新产品：{product_code}', 'info')
                else:
                    # 现有产品：使用用户输入的数据（可能已修改）
                    # 重要：不使用产品库的数据，使用用户表单中的数据
                    product_name = form.product_name.data
                    product_model = form.product_model.data
                    product_type = form.product_type.data
                    price = form.price_with_tax.data
                    # 不更新产品库！
            
            # 创建交易记录
            data = {
                'company_name': form.company_name.data,
                'product_id': product_id,
                'product_code': product_code,      # 必填
                'product_name': product_name,       # 用户输入（可能修改过）
                'product_model': product_model,     # 用户输入（可能修改过）
                'product_type': product_type,       # 用户输入（可能修改过）
                'quantity': form.quantity.data,
                'unit': form.unit.data,
                'price_with_tax': price,
                'delivery_date': form.delivery_date.data,
                'invoice_date': form.invoice_date.data,
                'payment_date': form.payment_date.data,
                'contract_no': form.contract_no.data,
                'remark': form.remark.data
            }
            
            TransactionService.create_transaction(data)
            flash('交易记录添加成功！', 'success')
            return redirect(url_for('transaction.list_transactions'))
        
        except Exception as e:
            flash(f'添加失败：{str(e)}', 'error')
    
    companies = StatementService.get_company_list()
    return render_template('transaction/form.html',
                         form=form,
                         title='新增交易记录',
                         companies=companies)
```

---

## 4. 前端交互逻辑（自动填充但允许修改）

```html
<!-- transaction/form.html - 关键交互 -->

<script>
// 选择产品编码后自动填充（仅作为默认值，用户可修改）
document.getElementById('product_select').addEventListener('change', function() {
    const productId = this.value;
    if (productId && productId !== '0') {
        fetch(`/product/api/${productId}`)
            .then(response => response.json())
            .then(data => {
                // 自动填充默认值（用户可修改）
                document.getElementById('display_product_code').value = data.product_code || '';
                document.getElementById('product_name').value = data.product_name || '';
                document.getElementById('product_model').value = data.product_model || '';
                document.getElementById('product_type').value = data.product_type || '';
                
                // 填充单价
                if (data.default_price) {
                    document.getElementById('price_input').value = data.default_price;
                }
                
                // 更新提示 - 告知用户可以修改
                document.getElementById('price_hint').innerHTML = 
                    `<span class="text-success">
                        <i class="bi bi-check-circle"></i> 
                        已选择产品编码: ${data.product_code}
                     </span>
                     <span class="text-muted ms-2">（可修改下方信息）</span>`;
            });
    }
});

// 手动输入产品编码时，失去焦点后检查是否存在
let productCodeExists = false;
document.getElementById('manual_product_code').addEventListener('blur', function() {
    const code = this.value.trim();
    if (code) {
        fetch(`/product/api/check-code?code=${encodeURIComponent(code)}`)
            .then(response => response.json())
            .then(data => {
                productCodeExists = data.exists;
                if (data.exists) {
                    // 编码已存在，提示用户可修改信息
                    document.getElementById('code_hint').innerHTML = 
                        `<span class="text-info">
                            <i class="bi bi-info-circle"></i> 
                            该产品编码已存在，下方信息将自动填充，您可修改
                         </span>`;
                    
                    // 可选：自动填充现有产品信息
                    if (data.product) {
                        document.getElementById('product_name').value = data.product.product_name || '';
                        document.getElementById('product_model').value = data.product.product_model || '';
                        document.getElementById('product_type').value = data.product.product_type || '';
                        if (data.product.default_price) {
                            document.getElementById('price_input').value = data.product.default_price;
                        }
                    }
                } else {
                    // 新编码
                    document.getElementById('code_hint').innerHTML = 
                        `<span class="text-warning">
                            <i class="bi bi-plus-circle"></i> 
                            新产品编码，保存时将自动创建产品
                         </span>`;
                }
            });
    }
});
</script>
```

---

## 5. 方案对比总结

### 5.1 原方案 vs 修订方案

| 场景 | 原方案 | 修订方案 |
|------|--------|---------|
| **匹配现有产品** | 更新产品库默认值 | **不更新产品库，仅读取默认值** |
| **用户修改信息** | 入库 | **仅保存到交易记录** |
| **修改产品信息** | 交易页面可操作 | **必须通过产品库页面编辑** |
| **产品名称唯一性** | 隐含唯一 | **明确允许同一编码不同名称** |

### 5.2 关键代码差异

```python
# 原方案（错误）
if existing:
    # 更新默认值 - 这会导致交易录入的修改入库
    if product_name:
        existing.product_name = product_name  # ❌ 错误
    return existing

# 修订方案（正确）
if existing:
    # 直接返回，不更新任何数据
    return existing, False  # ✅ 正确
```

---

## 6. 实施检查清单

### 必须实现的逻辑

- [ ] `get_or_create_product` 方法返回 `(Product, bool)` 元组
- [ ] 产品存在时（bool=False）**不更新**产品库任何字段
- [ ] 产品不存在时（bool=True）**创建**新产品并入库
- [ ] 交易记录使用表单中的数据，而非产品库数据
- [ ] 产品库编辑功能独立，只能通过产品库页面修改
- [ ] 前端提示告知用户：修改的信息仅影响当前交易

---

*文档版本: v1.1-final*  
*修订日期: 2026-03-06*  
*核心原则：产品编码唯一，交易修改不入库*
