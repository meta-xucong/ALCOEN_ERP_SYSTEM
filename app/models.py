from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, Text, Date, Integer, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app import db


class Company(db.Model):
    """公司名称表 - 用于自动补全"""
    __tablename__ = 'companies'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f'<Company {self.name}>'


class Product(db.Model):
    """产品库 - 以产品编码为唯一标识"""
    __tablename__ = 'products'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(100), nullable=True)
    product_model: Mapped[str] = mapped_column(String(100), nullable=True)
    product_type: Mapped[str] = mapped_column(String(50), nullable=True)
    default_price: Mapped[float] = mapped_column(Float, nullable=True)
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    image_path: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    transactions: Mapped[list['Transaction']] = relationship(back_populates='product')
    
    def __repr__(self):
        return f'<Product {self.product_code}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'product_code': self.product_code,
            'product_name': self.product_name,
            'product_model': self.product_model,
            'product_type': self.product_type,
            'default_price': self.default_price,
            'remark': self.remark
        }


# ==================== v1.2: 新增合同模型 ====================

class Department(db.Model):
    """部门表 - v1.3"""
    __tablename__ = 'departments'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # [v1.5] 移除 managers 关系，部门不再有预设负责人
    # 负责人直接在合同中填写，PM默认为自己但可改为部门任意成员
    
    def __repr__(self):
        return f'<Department {self.name}>'


class Contract(db.Model):
    """合同表 - v1.3 添加部门/负责人"""
    __tablename__ = 'contracts'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')  # pending/completed (总状态)
    # [LOGIC-7] 拆分完成状态
    delivery_status: Mapped[str] = mapped_column(String(20), default='pending')  # pending/partial/completed
    payment_status: Mapped[str] = mapped_column(String(20), default='pending')  # pending/partial/completed
    # [v1.3] 归属部门和负责人（二级结构）
    department: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    manager: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    # 保留owner字段用于兼容
    owner: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    # [v1.4] 合同创建人
    created_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    total_value: Mapped[float] = mapped_column(Float, default=0)
    remark: Mapped[str] = mapped_column(Text, nullable=True)  # 自动记录修改日志
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    contract_products: Mapped[list['ContractProduct']] = relationship(
        back_populates='contract', 
        cascade='all, delete-orphan',
        order_by='ContractProduct.id'
    )
    transactions: Mapped[list['Transaction']] = relationship(
        back_populates='contract',
        order_by='Transaction.delivery_date.desc()'
    )
    payment_records: Mapped[list['PaymentRecord']] = relationship(
        back_populates='contract',
        order_by='PaymentRecord.payment_date.desc()'
    )
    images: Mapped[list['ContractImage']] = relationship(
        back_populates='contract',
        cascade='all, delete-orphan',
        order_by='ContractImage.id'
    )
    # [v1.4] 合同文件（PDF、Word等）
    contract_files: Mapped[list['ContractFile']] = relationship(
        back_populates='contract',
        cascade='all, delete-orphan',
        order_by='ContractFile.id'
    )
    created_by: Mapped['User'] = relationship(foreign_keys=[created_by_id])
    
    def __repr__(self):
        return f'<Contract {self.contract_no}>'
    
    def get_status_display(self):
        """获取状态显示"""
        if self.status == 'completed':
            return {'text': '已完成', 'class': 'success', 'badge': 'bg-success'}
        else:
            return {'text': '未完成', 'class': 'warning', 'badge': 'bg-warning'}
    
    def get_delivery_status_display(self):
        """[v1.4] 获取发货状态显示：部分发货黄色，未发货红色"""
        status_map = {
            'completed': {'text': '发货完成', 'class': 'success', 'badge': 'bg-success'},
            'partial': {'text': '部分发货', 'class': 'warning', 'badge': 'bg-warning'},
            'pending': {'text': '未发货', 'class': 'danger', 'badge': 'bg-danger'}
        }
        return status_map.get(self.delivery_status, status_map['pending'])
    
    def get_payment_status_display(self):
        """[v1.4] 获取回款状态显示：部分回款黄色，未回款红色"""
        status_map = {
            'completed': {'text': '回款完成', 'class': 'success', 'badge': 'bg-success'},
            'partial': {'text': '部分回款', 'class': 'warning', 'badge': 'bg-warning'},
            'pending': {'text': '未回款', 'class': 'danger', 'badge': 'bg-danger'}
        }
        return status_map.get(self.payment_status, status_map['pending'])
    
    def append_remark(self, message: str):
        """追加备注记录"""
        from datetime import timezone, timedelta
        tz = timezone(timedelta(hours=8))  # UTC+8
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
        new_entry = f"[{now}] {message}"
        if self.remark:
            self.remark = new_entry + "\n" + self.remark
        else:
            self.remark = new_entry


class ContractProduct(db.Model):
    """合同产品计划 - 发货产品总数"""
    __tablename__ = 'contract_products'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'), nullable=True)
    product_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(100), nullable=True)
    product_model: Mapped[str] = mapped_column(String(100), nullable=True)
    product_type: Mapped[str] = mapped_column(String(50), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)  # 计划数量
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)  # 单价
    total: Mapped[float] = mapped_column(Float, nullable=False)  # 总价
    remark: Mapped[str] = mapped_column(Text, nullable=True)  # [v1.3] 备注
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联
    contract: Mapped['Contract'] = relationship(back_populates='contract_products')
    product: Mapped['Product'] = relationship(back_populates='contract_products')
    transactions: Mapped[list['Transaction']] = relationship(back_populates='contract_product')
    payment_records: Mapped[list['PaymentRecord']] = relationship(back_populates='contract_product')
    
    def __repr__(self):
        return f'<ContractProduct {self.product_code} x{self.quantity}>'
    
    def get_delivered_quantity(self):
        """获取已发货数量"""
        return sum(t.quantity for t in self.transactions if t.quantity)
    
    def get_delivered_value(self):
        """获取已发货货值"""
        return sum(t.total_price_with_tax for t in self.transactions if t.total_price_with_tax)
    
    def get_remaining_quantity(self):
        """获取未发货数量"""
        return self.quantity - self.get_delivered_quantity()
    
    def get_remaining_value(self):
        """获取未发货货值"""
        return self.total - self.get_delivered_value()


# 添加反向关系到 Product 模型
Product.contract_products = relationship('ContractProduct', back_populates='product')


class Transaction(db.Model):
    """发货记录 - v1.3 独立发货记录（不包含回款信息）"""
    __tablename__ = 'transactions'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # v1.2: 合同关联（核心变更）
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), nullable=True, index=True)
    contract_product_id: Mapped[int] = mapped_column(ForeignKey('contract_products.id'), nullable=True)
    
    # 公司信息
    company_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # 产品信息（冗余存储，便于查询）
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'), nullable=True)
    product_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(100), nullable=True)
    product_model: Mapped[str] = mapped_column(String(100), nullable=True)
    product_type: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # 发货信息
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    price_with_tax: Mapped[float] = mapped_column(Float, nullable=False)
    total_price_with_tax: Mapped[float] = mapped_column(Float, nullable=False)
    
    # v1.3: 经手人（必填）
    handler: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # 日期
    delivery_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    invoice_date: Mapped[Date] = mapped_column(Date, nullable=True)
    
    # 其他
    contract_no: Mapped[str] = mapped_column(String(100), nullable=True)  # 兼容旧数据
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    contract: Mapped['Contract'] = relationship(back_populates='transactions')
    contract_product: Mapped['ContractProduct'] = relationship(back_populates='transactions')
    product: Mapped['Product'] = relationship(back_populates='transactions')
    payment_records: Mapped[list['PaymentRecord']] = relationship(back_populates='transaction')
    
    def __repr__(self):
        return f'<Transaction {self.contract_id}-{self.id} {self.product_code}>'


class PaymentRecord(db.Model):
    """回款记录 - v1.3 独立的回款记录表"""
    __tablename__ = 'payment_records'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # 关联合同
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), nullable=True, index=True)
    
    # 公司信息
    company_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # 回款信息
    payment_amount: Mapped[float] = mapped_column(Float, nullable=False)  # 回款金额
    payment_date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)  # 回款日期
    
    # 可选关联发货记录 [v1.3] 可选关联产品计划
    transaction_id: Mapped[int] = mapped_column(ForeignKey('transactions.id'), nullable=True)
    contract_product_id: Mapped[int] = mapped_column(ForeignKey('contract_products.id'), nullable=True)
    
    # 经手人
    handler: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # 备注
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    contract: Mapped['Contract'] = relationship(back_populates='payment_records')
    transaction: Mapped['Transaction'] = relationship(back_populates='payment_records')
    contract_product: Mapped['ContractProduct'] = relationship(back_populates='payment_records')
    
    def __repr__(self):
        return f'<PaymentRecord {self.contract_id}-{self.id} {self.payment_amount}>'


class ContractImage(db.Model):
    """合同图片表 - v1.3 支持多张图片上传"""
    __tablename__ = 'contract_images'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # 原始文件名
    filepath: Mapped[str] = mapped_column(String(500), nullable=False)  # 存储路径
    file_type: Mapped[str] = mapped_column(String(50), nullable=True)  # 文件类型
    description: Mapped[str] = mapped_column(String(255), nullable=True)  # 图片描述
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联
    contract: Mapped['Contract'] = relationship(back_populates='images')
    
    def __repr__(self):
        return f'<ContractImage {self.contract_id}-{self.id} {self.filename}>'
    
    @property
    def image_url(self):
        """获取图片访问URL"""
        return f'/uploads/contracts/{self.contract_id}/{self.filename}'
    
    @property
    def thumbnail_url(self):
        """获取缩略图URL"""
        return f'/uploads/contracts/{self.contract_id}/thumb_{self.filename}'


class ContractFile(db.Model):
    """[v1.4] 合同文件表 - 存储PDF、Word等合同文档"""
    __tablename__ = 'contract_files'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey('contracts.id'), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # 原始文件名
    filepath: Mapped[str] = mapped_column(String(500), nullable=False)  # 存储路径
    file_type: Mapped[str] = mapped_column(String(50), nullable=True)  # 文件类型
    file_size: Mapped[int] = mapped_column(Integer, nullable=True)  # 文件大小(字节)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联
    contract: Mapped['Contract'] = relationship(back_populates='contract_files')
    
    def __repr__(self):
        return f'<ContractFile {self.contract_id}-{self.id} {self.filename}>'
    
    @property
    def file_url(self):
        """获取文件访问URL"""
        return f'/uploads/contract_documents/{self.contract_id}/{self.filepath}'
    
    @property
    def is_pdf(self):
        """是否是PDF文件"""
        return self.file_type and self.file_type.lower() == 'pdf'
    
    @property
    def is_image(self):
        """是否是图片文件"""
        if not self.file_type:
            return False
        return self.file_type.lower() in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']


# ==================== 保留旧表用于数据迁移 ====================

class Statement(db.Model):
    """对账单记录表 - [v1.4] 添加发起人和部门字段"""
    __tablename__ = 'statements'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    statement_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    filter_start_date: Mapped[Date] = mapped_column(Date, nullable=True)
    filter_end_date: Mapped[Date] = mapped_column(Date, nullable=True)
    filter_products: Mapped[str] = mapped_column(Text, nullable=True)
    statement_total: Mapped[float] = mapped_column(Float, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # [v1.4] 发起人信息
    created_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_by: Mapped['User'] = relationship(foreign_keys=[created_by_id])
    # [v1.4] 发起部门
    department: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    items: Mapped[list['StatementItem']] = relationship(back_populates='statement', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Statement {self.statement_no}>'


class StatementItem(db.Model):
    """对账单明细关联表 - 保留用于兼容"""
    __tablename__ = 'statement_items'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey('statements.id'), nullable=False)
    transaction_id: Mapped[int] = mapped_column(ForeignKey('transactions.id'), nullable=False)
    display_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    
    statement: Mapped['Statement'] = relationship(back_populates='items')
    transaction: Mapped['Transaction'] = relationship(back_populates='statement_items')
    
    def __repr__(self):
        return f'<StatementItem {self.display_seq}>'


# 添加反向关系到 Transaction
Transaction.statement_items = relationship('StatementItem', back_populates='transaction')


# ============ 事件监听 ============

@event.listens_for(Transaction, 'before_insert')
@event.listens_for(Transaction, 'before_update')
def calculate_total_price(mapper, connection, target):
    """自动计算总含税价格 [v1.3] 修复price为0时的计算问题"""
    if target.quantity is not None and target.price_with_tax is not None:
        target.total_price_with_tax = float(target.quantity) * float(target.price_with_tax)


@event.listens_for(ContractProduct, 'before_insert')
@event.listens_for(ContractProduct, 'before_update')
def calculate_contract_product_total(mapper, connection, target):
    """自动计算合同产品总价 [v1.3] 修复price为0时的计算问题"""
    if target.quantity is not None and target.price is not None:
        target.total = float(target.quantity) * float(target.price)


@event.listens_for(Transaction, 'after_insert')
def auto_add_company_and_update_contract(mapper, connection, target):
    """添加公司到列表"""
    from sqlalchemy import select
    
    # 添加公司
    stmt = select(Company).where(Company.name == target.company_name)
    result = connection.execute(stmt).scalar_one_or_none()
    if not result:
        connection.execute(Company.__table__.insert(), {'name': target.company_name})
    
    # 注意：合同备注更新在 ContractService.add_transaction 中处理
    # 这里不重复处理，避免冲突


@event.listens_for(Contract, 'after_update')
def check_contract_completion(mapper, connection, target):
    """检查合同是否完成"""
    # 这个逻辑在 Service 层处理更合适，这里仅作为备选
    pass

# ==================== v1.4: 账号登录系统 ====================

class Role(db.Model):
    """角色表 - 权限角色定义"""
    __tablename__ = 'roles'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    
    # 权限配置 (JSON格式存储权限列表)
    permissions: Mapped[str] = mapped_column(Text, default='[]')
    
    # 排序权重
    level: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联
    users: Mapped[list['User']] = relationship(back_populates='role')
    
    def __repr__(self):
        return f'<Role {self.code}>'
    
    def has_permission(self, permission_code: str) -> bool:
        """检查角色是否有指定权限"""
        import json
        if not self.permissions:
            return False
        perms = json.loads(self.permissions)
        # 空列表表示拥有所有权限（超级管理员）
        if len(perms) == 0 and self.code == 'superadmin':
            return True
        return permission_code in perms


class User(db.Model):
    """用户表 - 账号登录系统"""
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
    
    # 界面主题偏好 - JSON存储: {"background": "glass", "theme": "light", "style": "glass"}
    theme_preference: Mapped[str] = mapped_column(String(500), nullable=True, default='{"background": "glass", "theme": "light", "style": "glass"}')
    
    # 审核信息
    approved_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    role: Mapped['Role'] = relationship(back_populates='users')
    department: Mapped['Department'] = relationship(foreign_keys=[department_id])
    approver: Mapped['User'] = relationship(remote_side=[id], foreign_keys=[approved_by])
    created_contracts: Mapped[list['Contract']] = relationship(back_populates='created_by', foreign_keys='Contract.created_by_id')
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def get_theme_preference(self) -> dict:
        """获取用户的界面主题偏好设置
        
        Returns:
            {
                'bg_type': 'video' | 'image' | 'solid',
                'bg_image': 'bg-main.jpg',  # 图片背景时使用
                'theme': 'light' | 'dark',
                'style': 'glass' | 'modern' | 'classic'
            }
        """
        import json
        default_theme = {'bg_type': 'video', 'bg_image': 'bg-main.jpg', 'theme': 'light', 'style': 'glass'}
        if not self.theme_preference:
            return default_theme
        try:
            theme = json.loads(self.theme_preference)
            return {**default_theme, **theme}
        except (json.JSONDecodeError, TypeError):
            return default_theme
    
    def set_theme_preference(self, bg_type: str = None, bg_image: str = None, theme: str = None, style: str = None) -> None:
        """设置用户的界面主题偏好"""
        import json
        current = self.get_theme_preference()
        if bg_type is not None:
            current['bg_type'] = bg_type
        if bg_image is not None:
            current['bg_image'] = bg_image
        if theme is not None:
            current['theme'] = theme
        if style is not None:
            current['style'] = style
        self.theme_preference = json.dumps(current)
    
    def has_permission(self, permission_code: str) -> bool:
        """检查用户是否有指定权限"""
        if self.is_superadmin:
            return True
        return self.role.has_permission(permission_code)
    
    def can_view_financial(self) -> bool:
        """是否可以查看资金信息（物流经理脱敏）"""
        if self.is_superadmin:
            return True
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
    
    def can_edit_contract_delivery(self, contract=None) -> bool:
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
    
    def can_view_contract(self, contract) -> bool:
        """是否可以查看合同"""
        if self.is_superadmin:
            return True
        # 总经理和物流经理可以查看所有
        if self.role.code in ['general_manager', 'logistics_manager']:
            return True
        # 部门PM可以查看本部门所有合同
        if self.role.code == 'department_pm':
            return contract.department == self.department.name if self.department else False
        # 部门销售经理只能查看自己创建的合同
        if self.role.code == 'sales_manager':
            return contract.created_by_id == self.id
        return False
    
    def can_edit_contract(self, contract=None) -> bool:
        """是否可以编辑合同（进入编辑页面）"""
        if self.is_superadmin:
            return True
        # 物流经理可以编辑（但只能编辑发货记录和附件）
        if self.role.code == 'logistics_manager':
            return True
        # 总经理可以编辑所有
        if self.role.code == 'general_manager':
            return True
        # 部门PM可以编辑本部门所有合同
        if self.role.code == 'department_pm':
            if contract and contract.department:
                return self.department and contract.department == self.department.name
            return True
        # 部门销售经理只能编辑自己创建的合同
        if self.role.code == 'sales_manager':
            if contract:
                return contract.created_by_id == self.id
            return True
        return False
    
    def can_edit_contract_basic(self, contract=None) -> bool:
        """是否可以编辑合同基本信息（物流经理除外）"""
        if self.is_superadmin:
            return True
        # 物流经理不能编辑合同基本信息
        if self.role.code == 'logistics_manager':
            return False
        # 总经理可以编辑所有
        if self.role.code == 'general_manager':
            return True
        # 部门PM可以编辑本部门所有合同
        if self.role.code == 'department_pm':
            if contract and contract.department:
                return self.department and contract.department == self.department.name
            return True
        # 部门销售经理只能编辑自己创建的合同
        if self.role.code == 'sales_manager':
            if contract:
                return contract.created_by_id == self.id
            return True
        return False
    
    def is_logistics_manager(self) -> bool:
        """是否是物流经理"""
        return self.role.code == 'logistics_manager'
    
    def is_department_pm(self) -> bool:
        """是否是部门PM"""
        return self.role.code == 'department_pm'
    
    def is_sales_manager(self) -> bool:
        """是否是部门销售经理"""
        return self.role.code == 'sales_manager'


# 权限定义常量
PERMISSIONS = {
    # 合同模块
    'contract_view': '查看合同',
    'contract_create': '创建合同',
    'contract_edit': '编辑合同',
    'contract_delete': '删除合同',
    'contract_edit_delivery': '编辑发货记录',
    
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


# ==================== v1.5: 邮箱验证码系统 ====================

class VerificationCode(db.Model):
    """验证码表 - 存储登录验证码"""
    __tablename__ = 'verification_codes'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)  # 验证码
    purpose: Mapped[str] = mapped_column(String(20), default='login')  # 用途: login/reset_password/register
    device_fingerprint: Mapped[str] = mapped_column(String(64), nullable=True)  # 设备指纹
    ip_address: Mapped[str] = mapped_column(String(50), nullable=True)  # IP地址
    used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # 使用时间
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 过期时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联
    user: Mapped['User'] = relationship(foreign_keys=[user_id])
    
    def __repr__(self):
        return f'<VerificationCode {self.user_id}:{self.code}>'
    
    @property
    def is_expired(self) -> bool:
        """检查验证码是否已过期"""
        return datetime.now() > self.expires_at
    
    @property
    def is_used(self) -> bool:
        """检查验证码是否已使用"""
        return self.used_at is not None
    
    def mark_as_used(self):
        """标记为已使用"""
        self.used_at = datetime.now()


class TrustedDevice(db.Model):
    """受信任设备表 - 记录用户信任的登录设备"""
    __tablename__ = 'trusted_devices'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    device_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # 设备指纹
    device_name: Mapped[str] = mapped_column(String(100), nullable=True)  # 设备名称（如：Chrome on Windows）
    ip_address: Mapped[str] = mapped_column(String(50), nullable=True)  # 首次记录的IP
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)  # 最后使用时间
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 过期时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    
    # 关联
    user: Mapped['User'] = relationship(foreign_keys=[user_id])
    
    def __repr__(self):
        return f'<TrustedDevice {self.user_id}:{self.device_fingerprint[:8]}...>'
    
    @property
    def is_expired(self) -> bool:
        """检查设备信任是否已过期"""
        return datetime.now() > self.expires_at
    
    def update_last_used(self):
        """更新最后使用时间"""
        self.last_used_at = datetime.now()


# ==================== v1.5: 邮件验证系统模型 ====================

class SystemSetting(db.Model):
    """系统设置表 - 存储系统级配置"""
    __tablename__ = 'system_settings'
    
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    
    # 关联
    updated_by: Mapped['User'] = relationship(foreign_keys=[updated_by_id])
    
    def __repr__(self):
        return f'<SystemSetting {self.key}>'
    
    @staticmethod
    def get(key: str, default: str = None) -> str:
        """获取设置值"""
        setting = SystemSetting.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @staticmethod
    def set(key: str, value: str, description: str = None, user_id: int = None):
        """设置值"""
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
            setting.updated_by_id = user_id
        else:
            setting = SystemSetting(
                key=key,
                value=value,
                description=description,
                updated_by_id=user_id
            )
            db.session.add(setting)
        db.session.commit()
        return setting
    
    @staticmethod
    def get_email_config() -> dict:
        """获取系统邮箱配置"""
        return {
            'server': SystemSetting.get('mail_server', 'smtp.exmail.qq.com'),
            'port': int(SystemSetting.get('mail_port', '465')),
            'use_ssl': SystemSetting.get('mail_use_ssl', 'true').lower() == 'true',
            'username': SystemSetting.get('mail_username', ''),
            'password': SystemSetting.get('mail_password', ''),
            'sender_name': SystemSetting.get('mail_sender_name', 'ERP系统'),
        }
    
    @staticmethod
    def set_email_config(config: dict, user_id: int = None):
        """保存系统邮箱配置"""
        settings = [
            ('mail_server', config.get('server', 'smtp.exmail.qq.com'), 'SMTP服务器地址'),
            ('mail_port', str(config.get('port', 465)), 'SMTP端口'),
            ('mail_use_ssl', 'true' if config.get('use_ssl', True) else 'false', '是否使用SSL'),
            ('mail_username', config.get('username', ''), '发件邮箱账号'),
            ('mail_password', config.get('password', ''), '发件邮箱密码'),
            ('mail_sender_name', config.get('sender_name', 'ERP系统'), '发件人显示名称'),
        ]
        for key, value, desc in settings:
            SystemSetting.set(key, value, desc, user_id)


# 角色权限配置
ROLE_PERMISSIONS = {
    'superadmin': list(PERMISSIONS.keys()),
    
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
        # 'statement_view',  # [v1.4] 物流经理不能查看历史对账单
        'transaction_view', 'transaction_create', 'transaction_edit',
    ],
    
    'gm_assistant': [
        'contract_view', 'contract_edit',  # 可以查看和修改所有订单，但不能创建
        'product_view',
        'statement_view', 'statement_export',  # 可以查看和打印对账单
        # 没有 'contract_create' - 不可以发起订单
        # 没有 'transaction_view' - 看不到发货单
    ],
}



