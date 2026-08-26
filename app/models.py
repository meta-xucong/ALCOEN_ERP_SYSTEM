from datetime import datetime
from flask import current_app, has_app_context
from sqlalchemy import Boolean, String, Float, ForeignKey, DateTime, Text, Date, Integer, UniqueConstraint, event
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

class FormalContractParty(db.Model):
    """甲方档案，按规范化后的甲方名称唯一识别。"""

    __tablename__ = 'formal_contract_parties'

    id: Mapped[int] = mapped_column(primary_key=True)
    party_a_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), nullable=True, index=True)
    billing_address: Mapped[str] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(50), nullable=True)
    tax_no: Mapped[str] = mapped_column(String(100), nullable=True)
    bank_name: Mapped[str] = mapped_column(String(150), nullable=True)
    bank_account: Mapped[str] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default='manual', nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    company: Mapped['Company'] = relationship(
        'Company',
        foreign_keys=[company_id],
        back_populates='formal_contract_parties',
    )
    formal_contracts: Mapped[list['FormalContract']] = relationship(
        'FormalContract',
        back_populates='party',
        cascade='all, delete-orphan',
        order_by=lambda: (FormalContract.created_at.desc(), FormalContract.id.desc()),
    )

    def __repr__(self):
        return f'<FormalContractParty {self.party_a_name}>'


class FormalContract(db.Model):
    """正式合同生成器中的独立合同记录。"""

    __tablename__ = 'formal_contracts'

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey('departments.id'),
        nullable=True,
        index=True,
    )
    party_id: Mapped[int] = mapped_column(
        ForeignKey('formal_contract_parties.id'),
        nullable=False,
        index=True,
    )
    party_a_billing_address: Mapped[str] = mapped_column(String(255), nullable=True)
    party_a_phone: Mapped[str] = mapped_column(String(50), nullable=True)
    party_a_tax_no: Mapped[str] = mapped_column(String(100), nullable=True)
    party_a_bank_name: Mapped[str] = mapped_column(String(150), nullable=True)
    party_a_bank_account: Mapped[str] = mapped_column(String(100), nullable=True)
    party_b_name: Mapped[str] = mapped_column(String(100), nullable=True)
    party_b_billing_address: Mapped[str] = mapped_column(String(255), nullable=True)
    party_b_phone: Mapped[str] = mapped_column(String(50), nullable=True)
    party_b_tax_no: Mapped[str] = mapped_column(String(100), nullable=True)
    party_b_bank_name: Mapped[str] = mapped_column(String(150), nullable=True)
    party_b_bank_account: Mapped[str] = mapped_column(String(100), nullable=True)
    contract_no: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    sign_place: Mapped[str] = mapped_column(String(100), nullable=True)
    sign_date: Mapped[Date] = mapped_column(Date, nullable=True)
    quality_standard: Mapped[str] = mapped_column(Text, nullable=True)
    delivery_terms: Mapped[str] = mapped_column(Text, nullable=True)
    delivery_schedule: Mapped[str] = mapped_column(Text, nullable=True)
    settlement_terms: Mapped[str] = mapped_column(Text, nullable=True)
    breach_terms: Mapped[str] = mapped_column(Text, nullable=True)
    dispute_terms: Mapped[str] = mapped_column(Text, nullable=True)
    total_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    total_amount_upper: Mapped[str] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='draft', nullable=False, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    party: Mapped['FormalContractParty'] = relationship(
        'FormalContractParty',
        back_populates='formal_contracts',
    )
    department: Mapped['Department'] = relationship(
        'Department',
        foreign_keys=[department_id],
    )
    created_by: Mapped['User'] = relationship('User', foreign_keys=[created_by_id])
    items: Mapped[list['FormalContractItem']] = relationship(
        'FormalContractItem',
        back_populates='formal_contract',
        cascade='all, delete-orphan',
        order_by=lambda: (FormalContractItem.sort_order.asc(), FormalContractItem.id.asc()),
    )
    documents: Mapped[list['FormalContractDocument']] = relationship(
        'FormalContractDocument',
        back_populates='formal_contract',
        cascade='all, delete-orphan',
        order_by=lambda: (
            FormalContractDocument.generated_at.desc(),
            FormalContractDocument.id.desc(),
        ),
    )
    sync_links: Mapped[list['FormalContractSync']] = relationship(
        'FormalContractSync',
        back_populates='formal_contract',
        cascade='all, delete-orphan',
        order_by=lambda: (FormalContractSync.synced_at.desc(), FormalContractSync.id.desc()),
    )

    def __repr__(self):
        return f'<FormalContract {self.id}:{self.contract_no or "draft"}>'

    @property
    def is_generated(self) -> bool:
        return self.status in {'generated', 'synced'}

    @property
    def is_synced(self) -> bool:
        return self.status == 'synced' or any(
            link.sync_status == 'success' for link in self.sync_links
        )

    @property
    def latest_document(self):
        return self.documents[0] if self.documents else None

    @property
    def sync_link(self):
        return next(
            (link for link in self.sync_links if link.sync_status == 'success'),
            None,
        )


class FormalContractItem(db.Model):
    """正式合同产品明细，同时保存产品快照。"""

    __tablename__ = 'formal_contract_items'

    id: Mapped[int] = mapped_column(primary_key=True)
    formal_contract_id: Mapped[int] = mapped_column(
        ForeignKey('formal_contracts.id'),
        nullable=False,
        index=True,
    )
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'), nullable=True, index=True)
    product_code: Mapped[str] = mapped_column(String(50), nullable=True)
    product_name: Mapped[str] = mapped_column(String(100), nullable=True)
    product_model: Mapped[str] = mapped_column(String(100), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default='个', nullable=False)
    quantity: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    formal_contract: Mapped['FormalContract'] = relationship(
        'FormalContract',
        back_populates='items',
    )
    product: Mapped['Product'] = relationship(
        'Product',
        foreign_keys=[product_id],
        back_populates='formal_contract_items',
    )

    def __repr__(self):
        return f'<FormalContractItem {self.product_code} x{self.quantity}>'


class FormalContractTemplate(db.Model):
    """管理员维护的 DOCX 模板版本。"""

    __tablename__ = 'formal_contract_templates'

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey('departments.id'),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default='inactive', nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    activated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    deactivated_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    uploaded_by: Mapped['User'] = relationship('User', foreign_keys=[uploaded_by_id])
    department: Mapped['Department'] = relationship(
        'Department',
        foreign_keys=[department_id],
    )
    documents: Mapped[list['FormalContractDocument']] = relationship(
        'FormalContractDocument',
        back_populates='template',
    )

    def __repr__(self):
        return f'<FormalContractTemplate {self.name}:{self.version}>'

    @property
    def is_active(self) -> bool:
        return self.status == 'active'


class FormalContractDocument(db.Model):
    """正式合同生成的 DOCX 文件和不可变数据快照。"""

    __tablename__ = 'formal_contract_documents'

    id: Mapped[int] = mapped_column(primary_key=True)
    formal_contract_id: Mapped[int] = mapped_column(
        ForeignKey('formal_contracts.id'),
        nullable=False,
        index=True,
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey('formal_contract_templates.id'),
        nullable=False,
        index=True,
    )
    template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    docx_path: Mapped[str] = mapped_column(String(500), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    generated_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    print_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_printed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    formal_contract: Mapped['FormalContract'] = relationship(
        'FormalContract',
        back_populates='documents',
    )
    template: Mapped['FormalContractTemplate'] = relationship(
        'FormalContractTemplate',
        back_populates='documents',
    )
    generated_by: Mapped['User'] = relationship('User', foreign_keys=[generated_by_id])

    def __repr__(self):
        return f'<FormalContractDocument {self.formal_contract_id}:{self.id}>'


class FormalContractSync(db.Model):
    """正式合同与交易合同的一对一同步关系。"""

    __tablename__ = 'formal_contract_syncs'

    id: Mapped[int] = mapped_column(primary_key=True)
    formal_contract_id: Mapped[int] = mapped_column(
        ForeignKey('formal_contracts.id'),
        nullable=False,
        unique=True,
        index=True,
    )
    contract_id: Mapped[int] = mapped_column(
        ForeignKey('contracts.id'),
        nullable=True,
        unique=True,
        index=True,
    )
    synced_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    sync_status: Mapped[str] = mapped_column(String(20), default='success', nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    formal_contract: Mapped['FormalContract'] = relationship(
        'FormalContract',
        back_populates='sync_links',
    )
    contract: Mapped['Contract'] = relationship('Contract', foreign_keys=[contract_id])
    synced_by: Mapped['User'] = relationship('User', foreign_keys=[synced_by_id])

    def __repr__(self):
        return f'<FormalContractSync {self.formal_contract_id}->{self.contract_id}>'


Company.formal_contract_parties = relationship(
    'FormalContractParty',
    back_populates='company',
    foreign_keys='FormalContractParty.company_id',
)
Product.formal_contract_items = relationship(
    'FormalContractItem',
    back_populates='product',
    foreign_keys='FormalContractItem.product_id',
)


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


class UserDepartment(db.Model):
    """用户与部门的多对多关联。"""

    __tablename__ = 'user_departments'

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey('departments.id'), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    user: Mapped['User'] = relationship(back_populates='department_links')
    department: Mapped['Department'] = relationship()

    def __repr__(self):
        return f'<UserDepartment {self.user_id}:{self.department_id}>'


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
    actual_received_value: Mapped[float] = mapped_column(Float, default=0)  # 实收金额（回款完成判断基准）
    discount_value: Mapped[float] = mapped_column(Float, default=0)  # 折扣金额（总价 - 实收金额）
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
        # Keep same-day delivery records deterministic after new rows are added.
        order_by=lambda: (
            Transaction.delivery_date.desc(),
            Transaction.id.desc(),
        )
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
        if any(record.is_zero_value_exemption for record in self.payment_records):
            return {'text': '不需要回款', 'class': 'secondary', 'badge': 'bg-secondary'}
        status_map = {
            'completed': {'text': '回款完成', 'class': 'success', 'badge': 'bg-success'},
            'partial': {'text': '部分回款', 'class': 'warning', 'badge': 'bg-warning'},
            'pending': {'text': '未回款', 'class': 'danger', 'badge': 'bg-danger'}
        }
        return status_map.get(self.payment_status, status_map['pending'])

    def get_invoice_status_display(self):
        """获取开票状态显示。"""
        if any(record.is_zero_value_exemption for record in self.payment_records):
            return {'text': '不需要开票', 'class': 'secondary', 'badge': 'bg-secondary'}
        has_invoice = any(
            (p.invoice_date or (p.invoice_amount or 0) > 0)
            for p in self.payment_records
        ) or any(
            t.invoice_date for t in self.transactions
        )
        if has_invoice:
            return {'text': '已开票', 'class': 'success', 'badge': 'bg-success'}
        return {'text': '未开票', 'class': 'danger', 'badge': 'bg-danger'}

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
    transactions: Mapped[list['Transaction']] = relationship(
        back_populates='contract_product',
        order_by=lambda: Transaction.id.asc()
    )
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
    delivery_batch_no: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
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
    payment_amount: Mapped[float] = mapped_column(Float, nullable=True)  # 回款金额
    invoice_amount: Mapped[float] = mapped_column(Float, nullable=True)  # 开票金额
    payment_date: Mapped[Date] = mapped_column(Date, nullable=True, index=True)  # 回款日期
    invoice_date: Mapped[Date] = mapped_column(Date, nullable=True, index=True)  # 开票日期

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
        return f'<PaymentRecord {self.contract_id}-{self.id} pay={self.payment_amount} invoice={self.invoice_amount}>'

    @property
    def has_payment(self) -> bool:
        return (self.payment_amount or 0) > 0

    @property
    def has_invoice(self) -> bool:
        return (self.invoice_amount or 0) > 0

    @property
    def is_zero_value_exemption(self) -> bool:
        """Whether this record explicitly marks a no-payment/no-invoice giveaway."""
        return self.payment_amount == 0 and self.invoice_amount == 0

    @property
    def status_flags(self) -> list[str]:
        flags: list[str] = []
        if self.is_zero_value_exemption:
            flags.append('不需要回款/开票')
            return flags
        if self.has_payment and not self.has_invoice:
            flags.append('已回款，未开票')
        if self.has_invoice and not self.has_payment:
            flags.append('已开票，未回款')
        return flags


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
        target.total_price_with_tax = round(float(target.quantity) * float(target.price_with_tax), 2)


@event.listens_for(ContractProduct, 'before_insert')
@event.listens_for(ContractProduct, 'before_update')
def calculate_contract_product_total(mapper, connection, target):
    """自动计算合同产品总价 [v1.3] 修复price为0时的计算问题"""
    if target.quantity is not None and target.price is not None:
        target.total = round(float(target.quantity) * float(target.price), 2)


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

    @property
    def display_name(self) -> str:
        """Return a user-facing role name for shared ERP/QC templates."""
        if self.code == 'qc_inspector':
            return '供应商'
        return self.name

    def get_permission_codes(self) -> list[str]:
        """Return the stored permission codes for the role."""
        import json

        if not self.permissions:
            return []

        try:
            permissions = json.loads(self.permissions)
        except (json.JSONDecodeError, TypeError):
            return []

        return permissions if isinstance(permissions, list) else []

    def has_qc_permission(self, permission_code: str) -> bool:
        """Check QC permissions strictly against the stored role configuration."""
        return permission_code in QC_PERMISSIONS and permission_code in self.get_permission_codes()

    def has_permission(self, permission_code: str) -> bool:
        """检查角色是否有指定权限"""
        import json
        if not self.permissions:
            return False
        perms = json.loads(self.permissions)
        # 空列表表示拥有所有权限（超级管理员）
        if len(perms) == 0 and self.code == 'superadmin':
            return True
        # 总经理自动拥有所有权限
        if self.code == 'general_manager':
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
    department_links: Mapped[list['UserDepartment']] = relationship(
        back_populates='user',
        cascade='all, delete-orphan',
        foreign_keys='UserDepartment.user_id',
    )
    approver: Mapped['User'] = relationship(remote_side=[id], foreign_keys=[approved_by])
    created_contracts: Mapped[list['Contract']] = relationship(back_populates='created_by', foreign_keys='Contract.created_by_id')

    def __repr__(self):
        return f'<User {self.username}>'

    @property
    def departments(self) -> list['Department']:
        """返回用户所属的全部部门，兼容旧的单部门字段。"""
        departments: list['Department'] = []
        seen_ids: set[int] = set()

        if self.department and self.department.id not in seen_ids:
            departments.append(self.department)
            seen_ids.add(self.department.id)

        for link in self.department_links:
            if link.department and link.department.id not in seen_ids:
                departments.append(link.department)
                seen_ids.add(link.department.id)

        return departments

    @property
    def department_ids(self) -> list[int]:
        """返回用户所属的全部部门 ID。"""
        return [department.id for department in self.departments]

    @property
    def department_names(self) -> list[str]:
        """返回用户所属的全部部门名称。"""
        return [department.name for department in self.departments]

    @property
    def department_names_display(self) -> str:
        """返回用于前端展示的部门文本。"""
        if self.department_names:
            return '、'.join(self.department_names)
        if self.role and self.role.code == 'logistics_manager':
            return '全部部门'
        return '-'

    def belongs_to_department_id(self, department_id: int | None) -> bool:
        """检查用户是否属于某个部门 ID。"""
        return bool(department_id and department_id in self.department_ids)

    def belongs_to_department(self, dept_name: str | None) -> bool:
        """检查用户是否属于某个部门名称。"""
        return bool(dept_name and dept_name in self.department_names)

    def set_departments(self, department_ids: list[int] | None) -> None:
        """同步多部门归属，并保持旧的主部门字段兼容。"""
        normalized_ids: list[int] = []
        for department_id in department_ids or []:
            if department_id and department_id not in normalized_ids:
                normalized_ids.append(department_id)

        existing_links = {link.department_id: link for link in self.department_links}
        for department_id, link in existing_links.items():
            if department_id not in normalized_ids:
                db.session.delete(link)

        for department_id in normalized_ids:
            if department_id not in existing_links:
                self.department_links.append(UserDepartment(department_id=department_id))

        self.department_id = normalized_ids[0] if normalized_ids else None

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

    def has_qc_permission(self, permission_code: str) -> bool:
        """Check AI CATS permissions through the multi-identity access service."""
        from app.services.ai_cats_access_service import AICatsAccessService

        return AICatsAccessService.has_legacy_permission(self, permission_code)

    @staticmethod
    def _ai_cats_test_access_enabled() -> bool:
        """Return whether AI CATS test-period open access is enabled."""
        if not has_app_context():
            return False
        return bool(current_app.config.get('AI_CATS_TEST_OPEN_ACCESS', False))

    @property
    def has_ai_cats_test_access(self) -> bool:
        """Return whether the current user should receive temporary broad AI CATS access."""
        if not self.is_active or not self._ai_cats_test_access_enabled():
            return False
        if self.is_superadmin:
            return False
        if self.role and self.role.code in QC_ADMIN_ROLE_CODES:
            return False
        return True

    @property
    def ai_cats_effective_role_code(self) -> str:
        """Return one legacy-compatible role code for code paths not yet identity-aware."""
        from app.services.ai_cats_access_service import AICatsAccessService

        return AICatsAccessService.legacy_effective_role_code(self)

    @property
    def ai_cats_is_manager(self) -> bool:
        """Return whether the user has full AI CATS management access."""
        from app.services.ai_cats_access_service import AICatsAccessService

        return AICatsAccessService.is_manager(self)

    @property
    def ai_cats_is_controller(self) -> bool:
        """Return whether the user has the shared production/assembly controller identity."""
        return self.has_ai_cats_identity('controller')

    @property
    def ai_cats_is_inspector(self) -> bool:
        """Return whether the user has the supplier identity."""
        return self.has_ai_cats_identity('supplier')

    def has_ai_cats_identity(self, identity_code: str, module_code: str | None = None) -> bool:
        """Return whether one active AI CATS identity is enabled for an optional module."""
        from app.services.ai_cats_access_service import AICatsAccessService

        return AICatsAccessService.has_identity(self, identity_code, module_code)

    def has_ai_cats_scope(self, module_code: str) -> bool:
        """Return whether any active identity grants access to one AI CATS module."""
        from app.services.ai_cats_access_service import AICatsAccessService

        return AICatsAccessService.has_scope(self, module_code)

    @property
    def has_ai_cats_access(self) -> bool:
        """Return whether the active account can enter AI CATS."""
        from app.services.ai_cats_access_service import AICatsAccessService

        return AICatsAccessService.can_enter(self)

    def has_ai_cats_permission(self, permission_code: str) -> bool:
        """Return whether the user can perform one legacy AI CATS permission."""
        from app.services.ai_cats_access_service import AICatsAccessService

        return AICatsAccessService.has_legacy_permission(self, permission_code)

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
        if self.is_superadmin or self.role.code in ['general_manager', 'gm_assistant', 'logistics_manager']:
            return True
        # 部门角色只能访问本部门
        return self.belongs_to_department(dept_name)

    def can_edit_contract_delivery(self, contract=None) -> bool:
        """是否可以编辑合同的发货记录"""
        if self.is_superadmin:
            return True
        if not (self.has_permission('contract_edit_delivery') or self.has_permission('contract_edit')):
            return False
        # 物流经理可以编辑所有合同的发货记录
        if self.role.code == 'logistics_manager':
            return True
        # 总经理、总经理助理、部门PM可以编辑
        if self.role.code in ['general_manager', 'gm_assistant', 'department_pm']:
            return True
        # 部门销售经理只能编辑自己创建的合同
        if self.role.code == 'sales_manager':
            if contract:
                return contract.created_by_id == self.id
            return True
        return True

    def can_view_contract(self, contract) -> bool:
        """是否可以查看合同"""
        if self.is_superadmin:
            return True
        if not self.has_permission('contract_view'):
            return False
        # 总经理、总经理助理和物流经理可以查看所有
        if self.role.code in ['general_manager', 'gm_assistant', 'logistics_manager']:
            return True
        # 部门PM可以查看本部门所有合同
        if self.role.code == 'department_pm':
            return self.belongs_to_department(contract.department)
        # 部门销售经理只能查看自己创建的合同
        if self.role.code == 'sales_manager':
            return contract.created_by_id == self.id
        return True

    def can_edit_contract(self, contract=None) -> bool:
        """是否可以编辑合同（进入编辑页面）"""
        if self.is_superadmin:
            return True
        # 物流经理可以编辑（但只能编辑发货记录和附件）
        if self.role.code == 'logistics_manager':
            return self.has_permission('contract_edit_delivery')
        if not self.has_permission('contract_edit'):
            return False
        # 总经理、总经理助理可以编辑所有
        if self.role.code in ['general_manager', 'gm_assistant']:
            return True
        # 部门PM可以编辑本部门所有合同
        if self.role.code == 'department_pm':
            if contract and contract.department:
                return self.belongs_to_department(contract.department)
            return True
        # 部门销售经理只能编辑自己创建的合同
        if self.role.code == 'sales_manager':
            if contract:
                return contract.created_by_id == self.id
            return True
        return True

    def can_edit_contract_basic(self, contract=None) -> bool:
        """是否可以编辑合同基本信息（物流经理除外）"""
        if self.is_superadmin:
            return True
        # 物流经理不能编辑合同基本信息
        if self.role.code == 'logistics_manager':
            return False
        if not self.has_permission('contract_edit'):
            return False
        # 总经理、总经理助理可以编辑所有
        if self.role.code in ['general_manager', 'gm_assistant']:
            return True
        # 部门PM可以编辑本部门所有合同
        if self.role.code == 'department_pm':
            if contract and contract.department:
                return self.belongs_to_department(contract.department)
            return True
        # 部门销售经理只能编辑自己创建的合同
        if self.role.code == 'sales_manager':
            if contract:
                return contract.created_by_id == self.id
            return True
        return True

    def can_delete_contract(self, contract=None) -> bool:
        """是否可以删除合同。

        规则：
        1. 超级管理员可以删除所有合同；
        2. 合同创建人可以删除自己创建的合同（物流经理除外）；
        3. 其他角色需同时具备 contract_delete 权限，且满足基础编辑范围校验。
        """
        if self.is_superadmin:
            return True

        if not contract:
            return False

        # 物流经理不允许删除合同
        if self.role.code == 'logistics_manager':
            return False

        # 创建人可删除自己创建的合同（满足用户需求）
        if contract.created_by_id == self.id:
            return True

        # 非创建人需具备删除权限，并且落在可编辑范围内
        if not self.has_permission('contract_delete'):
            return False
        return self.can_edit_contract_basic(contract)

    def is_logistics_manager(self) -> bool:
        """是否是物流经理"""
        return self.role.code == 'logistics_manager'

    def is_department_pm(self) -> bool:
        """是否是部门PM"""
        return self.role.code == 'department_pm'

    def is_sales_manager(self) -> bool:
        """是否是部门销售经理"""
        return self.role.code == 'sales_manager'

    def is_gm_assistant(self) -> bool:
        """是否是总经理助理"""
        return self.role.code == 'gm_assistant'


# 权限定义常量
ERP_PERMISSIONS = {
    # 合同模块
    'contract_view': '查看合同',
    'contract_create': '创建合同',
    'contract_edit': '编辑合同',
    'contract_delete': '删除合同',
    'contract_edit_delivery': '编辑发货记录',

    # 正式合同生成器
    'formal_contract_view': '查看正式合同',
    'formal_contract_create': '创建正式合同',
    'formal_contract_edit': '编辑正式合同',
    'formal_contract_generate': '生成正式合同',
    'formal_contract_print': '打印正式合同',
    'formal_contract_sync': '同步到交易合同',
    'formal_contract_template_manage': '管理正式合同模板',
    'formal_contract_history_view': '查看正式合同历史',

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

QC_PERMISSIONS = {
    'qc_dashboard': 'QC仪表盘',
    'qc_workpiece_view': '查看工件库',
    'qc_workpiece_create': '新增工件',
    'qc_workpiece_edit': '编辑工件',
    'qc_workpiece_delete': '删除工件',
    'qc_work_order_view': '查看工件订单',
    'qc_work_order_create': '创建工件订单',
    'qc_work_order_edit': '编辑工件订单',
    'qc_work_order_delete': '删除工件订单',
    'qc_inspection_view': '查看质量检测',
    'qc_inspection_perform': '执行质量检测',
    'qc_acceptance_perform': '执行验收确认',
    'qc_acceptance_rollback': '验收回退/撤销',
}

PERMISSIONS = {**ERP_PERMISSIONS, **QC_PERMISSIONS}

QC_ROLE_CODES = ('qc_controller', 'qc_inspector')
QC_MANAGER_ROLE_CODES = ('general_manager', 'gm_assistant')
QC_ADMIN_ROLE_CODES = QC_MANAGER_ROLE_CODES + QC_ROLE_CODES

AI_CATS_IDENTITY_DEFINITIONS = {
    'controller': {
        'name': '质量控制人',
        'description': '负责配件生产和装配/出厂中的发起、管理与质控方确认',
        'default_scopes': ('production', 'assembly'),
    },
    'supplier': {
        'name': '供应商',
        'description': '负责被指派订单的质量检测、材料上传、供应商确认与验收',
        'default_scopes': ('production', 'assembly'),
    },
    'researcher': {
        'name': '研究人员',
        'description': '负责研究项目、研究批次和研究方验收',
        'default_scopes': ('research',),
    },
    'research_reviewer': {
        'name': '指导/验收人员',
        'description': '负责被指派研究批次的指导审批和指导方验收',
        'default_scopes': ('research',),
    },
}
AI_CATS_IDENTITY_CODES = tuple(AI_CATS_IDENTITY_DEFINITIONS)
AI_CATS_MODULE_CODES = ('production', 'assembly', 'research')
AI_CATS_IDENTITY_STATUS_CODES = ('pending', 'active', 'rejected', 'revoked')
AI_CATS_ACCOUNT_ACCESS_MODES = ('ai_cats_only', 'shared')
AI_CATS_TECHNICAL_ROLE_CODE = 'ai_cats_user'

AI_CATS_LEGACY_ROLE_IDENTITY_MAP = {
    # Existing accounts used each legacy role across all three modules. Backfill
    # both identities so current production data remains operable after cutover.
    'qc_controller': ('controller', 'researcher'),
    'qc_inspector': ('supplier', 'research_reviewer'),
}

QC_DEFAULT_PERMISSION_CODES = {
    'general_manager': (
        'qc_dashboard',
        'qc_workpiece_view',
        'qc_workpiece_create',
        'qc_workpiece_edit',
        'qc_workpiece_delete',
        'qc_work_order_view',
        'qc_work_order_create',
        'qc_work_order_edit',
        'qc_work_order_delete',
        'qc_inspection_view',
        'qc_inspection_perform',
        'qc_acceptance_perform',
        'qc_acceptance_rollback',
    ),
    'gm_assistant': (
        'qc_dashboard',
        'qc_workpiece_view',
        'qc_workpiece_create',
        'qc_workpiece_edit',
        'qc_workpiece_delete',
        'qc_work_order_view',
        'qc_work_order_create',
        'qc_work_order_edit',
        'qc_work_order_delete',
        'qc_inspection_view',
        'qc_inspection_perform',
        'qc_acceptance_perform',
        'qc_acceptance_rollback',
    ),
    'qc_controller': (
        'qc_dashboard',
        'qc_workpiece_view',
        'qc_workpiece_create',
        'qc_workpiece_edit',
        'qc_workpiece_delete',
        'qc_work_order_view',
        'qc_work_order_create',
        'qc_work_order_edit',
        'qc_work_order_delete',
        'qc_inspection_view',
        'qc_acceptance_perform',
        'qc_acceptance_rollback',
    ),
    'qc_inspector': (
        'qc_dashboard',
        'qc_inspection_view',
        'qc_inspection_perform',
        'qc_acceptance_perform',
    ),
}

QC_ROLE_PERMISSION_CODES = {
    role_code: QC_DEFAULT_PERMISSION_CODES[role_code]
    for role_code in QC_ROLE_CODES
}

QC_ROLE_EDITABLE_PERMISSIONS = {
    role_code: {permission_code: PERMISSIONS[permission_code] for permission_code in permission_codes}
    for role_code, permission_codes in QC_DEFAULT_PERMISSION_CODES.items()
}

QC_WORKPIECE_TYPE_SELF = 'self_produced'
QC_WORKPIECE_TYPE_OUTSOURCED = 'outsourced'
QC_WORKPIECE_TYPES = (QC_WORKPIECE_TYPE_SELF, QC_WORKPIECE_TYPE_OUTSOURCED)
QC_WORKPIECE_TYPE_DISPLAY = {
    QC_WORKPIECE_TYPE_SELF: '自产',
    QC_WORKPIECE_TYPE_OUTSOURCED: '外采',
}
QC_QUALITY_MATERIAL_ATTACHMENT_TYPE = 'qc_material'
QC_GUIDE_ATTACHMENT_TYPES = ('inspection_point', 'instruction')

RESEARCH_STATUS_DISPLAY = {
    'draft': {'text': '草稿', 'badge': 'bg-secondary'},
    'research_pending': {'text': '研究准备中', 'badge': 'bg-primary'},
    'research_submitted': {'text': '待指导审批', 'badge': 'bg-warning text-dark'},
    'review_completed': {'text': '指导完成', 'badge': 'bg-info text-dark'},
    'accepted': {'text': '阶段研发完成', 'badge': 'bg-success'},
    'returned': {'text': '已退回补充', 'badge': 'bg-danger'},
}

RESEARCH_ATTACHMENT_TYPE_DISPLAY = {
    'initiation_material': '立项资料',
    'research_material': '研究资料',
    'experiment_plan': '实验方案',
    'validation_item': '观察项 / 验证目标',
    'risk_note': '风险提示 / 补充说明',
}

ASSEMBLY_STATUS_DISPLAY = {
    'draft': {'text': '草稿', 'badge': 'bg-secondary'},
    'assembly_pending': {'text': '装配准备中', 'badge': 'bg-primary'},
    'assembly_completed': {'text': '待加工批次', 'badge': 'bg-info'},
    'inspection_pending': {'text': '质检未完成', 'badge': 'bg-warning text-dark'},
    'inspection_completed': {'text': '质检已完成', 'badge': 'bg-primary'},
    'accepted': {'text': '质检已完成', 'badge': 'bg-success'},
    'rejected': {'text': '质检不合格', 'badge': 'bg-danger'},
}

ASSEMBLY_PRODUCT_ATTACHMENT_TITLE_PREFIX = {
    'assembly_sheet': '装配单',
    'coa_template': 'COA报告模板',
    'remark': '备注',
}

ASSEMBLY_OUTBOUND_STATUS_DISPLAY = {
    'confirming': {'text': '待出厂确认', 'badge': 'bg-primary'},
    'completed': {'text': '出厂完成', 'badge': 'bg-success'},
}

ASSEMBLY_PRODUCT_LEVEL_DISPLAY = {
    1: '一级产品库',
    2: '二级产品库',
    3: '三级产品库',
}

RESEARCH_ATTACHMENT_TITLE_PREFIX = {
    'initiation_material': '立项资料',
    'research_material': '研究资料',
    'experiment_plan': '实验方案',
    'validation_item': '观察项',
    'risk_note': '风险提示',
}


def normalize_qc_workpiece_type(value: str | None) -> str:
    """Return a safe workpiece type code."""
    return value if value in QC_WORKPIECE_TYPES else QC_WORKPIECE_TYPE_SELF


def normalize_qc_guide_title(title: str | None, index: int | None = None) -> str:
    """Normalize legacy detection-point labels into work-instruction labels."""
    normalized = (title or '').strip().replace('检测点', '作业指导书')
    if normalized:
        return normalized
    if index is not None:
        return f'作业指导书{index}'
    return '作业指导书'


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
        'formal_contract_view', 'formal_contract_create', 'formal_contract_edit',
        'formal_contract_generate', 'formal_contract_print', 'formal_contract_sync',
        'formal_contract_template_manage', 'formal_contract_history_view',
        'product_view', 'product_create', 'product_edit', 'product_delete',
        'statement_view', 'statement_create', 'statement_export', 'statement_delete',
        'transaction_view', 'transaction_create', 'transaction_edit', 'transaction_delete',
        'payment_view', 'payment_create', 'payment_edit',
    ],

    'department_pm': [
        'contract_view', 'contract_create', 'contract_edit', 'contract_delete', 'contract_edit_delivery',
        'formal_contract_view', 'formal_contract_create', 'formal_contract_edit',
        'formal_contract_generate', 'formal_contract_print', 'formal_contract_sync',
        'formal_contract_history_view',
        'product_view', 'product_create', 'product_edit', 'product_delete',
        'statement_view', 'statement_create', 'statement_export', 'statement_delete',
        'transaction_view', 'transaction_create', 'transaction_edit', 'transaction_delete',
        'payment_view', 'payment_create', 'payment_edit',
    ],

    'sales_manager': [
        'contract_view', 'contract_create', 'contract_edit',
        'formal_contract_view', 'formal_contract_create', 'formal_contract_edit',
        'formal_contract_generate', 'formal_contract_print', 'formal_contract_sync',
        'formal_contract_history_view',
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
        'formal_contract_view', 'formal_contract_create', 'formal_contract_edit',
        'formal_contract_generate', 'formal_contract_print', 'formal_contract_sync',
        'formal_contract_history_view',
        'product_view',
        'statement_view', 'statement_export',  # 可以查看和打印对账单
        # 没有 'contract_create' - 不可以发起订单
        # 没有 'transaction_view' - 看不到发货单
    ],
}





# ==================== v2.0: 质量控制系统 (QC) 模型 ====================

QC_STATUS_DISPLAY = {
    'draft': {'text': '草稿', 'badge': 'bg-dark'},
    'qc_pending': {'text': '质控未完成', 'badge': 'bg-secondary'},
            'qc_completed': {'text': '待加工批次', 'badge': 'bg-info'},
    'inspection_pending': {'text': '质检未完成', 'badge': 'bg-warning'},
    'inspection_completed': {'text': '待验收确认', 'badge': 'bg-primary'},
    'accepted': {'text': '质检已完成', 'badge': 'bg-success'},
    'rejected': {'text': '质检不合格', 'badge': 'bg-danger'},
}


def get_qc_signer_role_display(role_code: str) -> str:
    """Return the user-facing QC signer role label."""
    if role_code == 'qc_controller':
        return '质控人'
    if role_code == 'qc_inspector':
        return '供应商'
    return role_code


class QCUserBinding(db.Model):
    """QC 用户角色绑定表 - 记录 ERP 账号在 QC 子系统中的角色及审核状态"""
    __tablename__ = 'qc_user_bindings'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=False)
    approved_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    user: Mapped['User'] = relationship(foreign_keys=[user_id])
    role: Mapped['Role'] = relationship(foreign_keys=[role_id])
    approver: Mapped['User'] = relationship(foreign_keys=[approved_by])

    def __repr__(self):
        return f'<QCUserBinding {self.user_id}:{self.role_id}>'


class AICatsAccountProfile(db.Model):
    """AI CATS account access settings, separate from global ERP activation."""

    __tablename__ = 'ai_cats_account_profiles'

    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'),
        primary_key=True,
    )
    access_mode: Mapped[str] = mapped_column(String(20), nullable=False, default='shared')
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )

    user: Mapped['User'] = relationship(foreign_keys=[user_id])

    def __repr__(self):
        return f'<AICatsAccountProfile {self.user_id}:{self.access_mode}>'


class AICatsUserIdentity(db.Model):
    """One independently reviewable AI CATS business identity for a user."""

    __tablename__ = 'ai_cats_user_identities'
    __table_args__ = (
        UniqueConstraint('user_id', 'identity_code', name='uq_ai_cats_user_identity'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    identity_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending', index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default='registration')
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    approved_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )

    user: Mapped['User'] = relationship(foreign_keys=[user_id])
    approver: Mapped['User'] = relationship(foreign_keys=[approved_by])
    revoker: Mapped['User'] = relationship(foreign_keys=[revoked_by])
    scopes: Mapped[list['AICatsUserIdentityScope']] = relationship(
        back_populates='identity',
        cascade='all, delete-orphan',
        order_by='AICatsUserIdentityScope.module_code',
    )

    @property
    def display_name(self) -> str:
        definition = AI_CATS_IDENTITY_DEFINITIONS.get(self.identity_code, {})
        return definition.get('name', self.identity_code)

    @property
    def enabled_module_codes(self) -> set[str]:
        if self.scopes:
            return {scope.module_code for scope in self.scopes if scope.is_enabled}
        definition = AI_CATS_IDENTITY_DEFINITIONS.get(self.identity_code, {})
        return set(definition.get('default_scopes', ()))

    def __repr__(self):
        return f'<AICatsUserIdentity {self.user_id}:{self.identity_code}:{self.status}>'


class AICatsUserIdentityScope(db.Model):
    """Enabled AI CATS module scope for one assigned identity."""

    __tablename__ = 'ai_cats_user_identity_scopes'
    __table_args__ = (
        UniqueConstraint(
            'user_identity_id',
            'module_code',
            name='uq_ai_cats_user_identity_scope',
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_identity_id: Mapped[int] = mapped_column(
        ForeignKey('ai_cats_user_identities.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    module_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
    )

    identity: Mapped['AICatsUserIdentity'] = relationship(back_populates='scopes')

    def __repr__(self):
        return f'<AICatsUserIdentityScope {self.user_identity_id}:{self.module_code}>'


class AICatsIdentityAuditLog(db.Model):
    """Immutable audit log for AI CATS identity and account changes."""

    __tablename__ = 'ai_cats_identity_audit_logs'

    id: Mapped[int] = mapped_column(primary_key=True)
    target_user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id'),
        nullable=False,
        index=True,
    )
    identity_code: Mapped[str] = mapped_column(String(40), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    before_state: Mapped[str] = mapped_column(Text, nullable=True)
    after_state: Mapped[str] = mapped_column(Text, nullable=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    target_user: Mapped['User'] = relationship(foreign_keys=[target_user_id])
    operator: Mapped['User'] = relationship(foreign_keys=[operator_id])

    def __repr__(self):
        return f'<AICatsIdentityAuditLog {self.target_user_id}:{self.action}>'


class QCWorkpiece(db.Model):
    """QC 工件库主表。"""
    __tablename__ = 'qc_workpieces'

    id: Mapped[int] = mapped_column(primary_key=True)
    workpiece_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    workpiece_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    workpiece_type: Mapped[str] = mapped_column(
        String(20),
        default=QC_WORKPIECE_TYPE_SELF,
        nullable=False,
        index=True,
    )
    stock_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    creator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    creator: Mapped['User'] = relationship(foreign_keys=[creator_id])
    attachments: Mapped[list['QCWorkpieceAttachment']] = relationship(
        back_populates='workpiece',
        cascade='all, delete-orphan',
        order_by='QCWorkpieceAttachment.sort_order'
    )
    work_orders: Mapped[list['QCWorkOrder']] = relationship(back_populates='workpiece')
    stock_histories: Mapped[list['QCWorkpieceStockHistory']] = relationship(
        back_populates='workpiece',
        cascade='all, delete-orphan',
        order_by='QCWorkpieceStockHistory.created_at.desc(), QCWorkpieceStockHistory.id.desc()'
    )

    def __repr__(self):
        return f'<QCWorkpiece {self.workpiece_code}>'

    @property
    def normalized_type(self) -> str:
        return normalize_qc_workpiece_type(self.workpiece_type)

    @property
    def is_outsourced(self) -> bool:
        return self.normalized_type == QC_WORKPIECE_TYPE_OUTSOURCED

    @property
    def workpiece_type_display(self) -> str:
        return QC_WORKPIECE_TYPE_DISPLAY.get(self.normalized_type, '自产')

    @property
    def primary_material_label(self) -> str:
        return '质检材料' if self.is_outsourced else '图纸'

    @property
    def drawing_attachment(self) -> 'QCWorkpieceAttachment | None':
        return next((attachment for attachment in self.attachments if attachment.attach_type == 'drawing'), None)

    @property
    def drawing_attachments(self) -> list['QCWorkpieceAttachment']:
        drawings = [
            attachment
            for attachment in self.attachments
            if attachment.attach_type == 'drawing'
        ]
        return sorted(drawings, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def quality_material_attachments(self) -> list['QCWorkpieceAttachment']:
        materials = [
            attachment
            for attachment in self.attachments
            if attachment.attach_type == QC_QUALITY_MATERIAL_ATTACHMENT_TYPE
        ]
        return sorted(materials, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def primary_material_attachments(self) -> list['QCWorkpieceAttachment']:
        if self.is_outsourced:
            return self.quality_material_attachments
        return self.drawing_attachments

    @property
    def guide_attachments(self) -> list['QCWorkpieceAttachment']:
        guides = [attachment for attachment in self.attachments if attachment.attach_type in QC_GUIDE_ATTACHMENT_TYPES]
        return sorted(guides, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def remark_attachments(self) -> list['QCWorkpieceAttachment']:
        remarks = [attachment for attachment in self.attachments if attachment.attach_type == 'remark']
        return sorted(remarks, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def coa_template_attachments(self) -> list['QCWorkpieceAttachment']:
        templates = [attachment for attachment in self.attachments if attachment.attach_type == 'coa_template']
        return sorted(templates, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def coa_template_attachment(self) -> 'QCWorkpieceAttachment | None':
        return self.coa_template_attachments[0] if self.coa_template_attachments else None


class QCWorkOrder(db.Model):
    """QC 工件订单主表"""
    __tablename__ = 'qc_work_orders'

    id: Mapped[int] = mapped_column(primary_key=True)
    # A business batch number may be reused for separate production orders.
    # The primary key remains the immutable identifier for every order.
    batch_no: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    workpiece_id: Mapped[int] = mapped_column(ForeignKey('qc_workpieces.id', ondelete='SET NULL'), nullable=True, index=True)
    workpiece_name: Mapped[str] = mapped_column(String(200), nullable=False)
    workpiece_type: Mapped[str] = mapped_column(
        String(20),
        default=QC_WORKPIECE_TYPE_SELF,
        nullable=False,
        index=True,
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    controller_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    inspector_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default='qc_pending', index=True)
    qc_completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    inspection_completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    inventory_posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)
    drawing_note_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    drawing_note_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    drawing_note_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    guide_certificate_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    guide_certificate_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    guide_certificate_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    remark_note_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    remark_note_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    remark_note_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    workpiece: Mapped['QCWorkpiece'] = relationship(back_populates='work_orders')
    controller: Mapped['User'] = relationship(foreign_keys=[controller_id])
    inspector: Mapped['User'] = relationship(foreign_keys=[inspector_id])
    attachments: Mapped[list['QCWorkOrderAttachment']] = relationship(
        back_populates='work_order',
        cascade='all, delete-orphan',
        order_by='QCWorkOrderAttachment.sort_order'
    )
    inspection_records: Mapped[list['QCInspectionRecord']] = relationship(
        back_populates='work_order',
        cascade='all, delete-orphan',
        order_by='QCInspectionRecord.id'
    )
    acceptance_batches: Mapped[list['QCAcceptanceBatch']] = relationship(
        back_populates='work_order',
        cascade='all, delete-orphan',
        order_by='QCAcceptanceBatch.id'
    )
    signatures: Mapped[list['QCAcceptanceSignature']] = relationship(
        back_populates='work_order',
        cascade='all, delete-orphan',
        order_by='QCAcceptanceSignature.id'
    )
    histories: Mapped[list['QCWorkOrderHistory']] = relationship(
        back_populates='work_order',
        cascade='all, delete-orphan',
        order_by='QCWorkOrderHistory.created_at.desc(), QCWorkOrderHistory.id.desc()'
    )

    def __repr__(self):
        return f'<QCWorkOrder {self.batch_no}>'

    def get_status_display(self) -> dict:
        """获取状态显示信息"""
        return QC_STATUS_DISPLAY.get(self.status, QC_STATUS_DISPLAY['qc_pending'])

    def get_acceptance_status_display(self) -> dict:
        """Return a user-facing acceptance progress badge."""
        if self.status == 'accepted':
            return QC_STATUS_DISPLAY['accepted']

        if self.status == 'inspection_completed':
            roles_signed = {signature.signer_role for signature in self.signatures}
            if roles_signed:
                return {'text': '待另一方确认', 'badge': 'bg-warning'}
            return QC_STATUS_DISPLAY['inspection_completed']

        return self.get_status_display()

    @property
    def completed_acceptance_batches(self) -> list['QCAcceptanceBatch']:
        return [
            batch for batch in self.acceptance_batches
            if batch.completed_at is not None
        ]

    @property
    def active_acceptance_batch(self) -> 'QCAcceptanceBatch | None':
        open_batches = [
            batch for batch in self.acceptance_batches
            if batch.completed_at is None
        ]
        return open_batches[-1] if open_batches else None

    @property
    def actual_delivered_quantity(self) -> float:
        delivered = sum(float(batch.accepted_quantity or 0) for batch in self.completed_acceptance_batches)
        if delivered <= 0 and self.status == 'accepted' and not self.acceptance_batches:
            return float(self.quantity or 0)
        return delivered

    @property
    def remaining_acceptance_quantity(self) -> float:
        return max(0.0, float(self.quantity or 0) - self.actual_delivered_quantity)

    @property
    def normalized_type(self) -> str:
        return normalize_qc_workpiece_type(self.workpiece_type)

    @property
    def is_outsourced(self) -> bool:
        return self.normalized_type == QC_WORKPIECE_TYPE_OUTSOURCED

    @property
    def workpiece_type_display(self) -> str:
        return QC_WORKPIECE_TYPE_DISPLAY.get(self.normalized_type, '自产')

    @property
    def primary_material_label(self) -> str:
        return '质检材料' if self.is_outsourced else '图纸'

    @property
    def drawing_attachment(self) -> 'QCWorkOrderAttachment | None':
        return next((attachment for attachment in self.attachments if attachment.attach_type == 'drawing'), None)

    @property
    def drawing_attachments(self) -> list['QCWorkOrderAttachment']:
        drawings = [
            attachment
            for attachment in self.attachments
            if attachment.attach_type == 'drawing'
        ]
        return sorted(drawings, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def quality_material_attachments(self) -> list['QCWorkOrderAttachment']:
        materials = [
            attachment
            for attachment in self.attachments
            if attachment.attach_type == QC_QUALITY_MATERIAL_ATTACHMENT_TYPE
        ]
        return sorted(materials, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def primary_material_attachments(self) -> list['QCWorkOrderAttachment']:
        if self.is_outsourced:
            materials = self.quality_material_attachments
            if materials:
                return materials
        return self.drawing_attachments

    @property
    def guide_attachments(self) -> list['QCWorkOrderAttachment']:
        guides = [attachment for attachment in self.attachments if attachment.attach_type in QC_GUIDE_ATTACHMENT_TYPES]
        return sorted(guides, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def remark_attachments(self) -> list['QCWorkOrderAttachment']:
        remarks = [attachment for attachment in self.attachments if attachment.attach_type == 'remark']
        return sorted(remarks, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def non_remark_attachments(self) -> list['QCWorkOrderAttachment']:
        attachments = [attachment for attachment in self.attachments if attachment.attach_type != 'remark']
        return sorted(attachments, key=lambda attachment: (attachment.sort_order, attachment.id))

    @property
    def ordered_attachments(self) -> list['QCWorkOrderAttachment']:
        """Return attachments in the UI order: primary material, guides, then remarks."""
        ordered: list['QCWorkOrderAttachment'] = []
        ordered.extend(self.primary_material_attachments)
        ordered.extend(self.guide_attachments)
        ordered.extend(self.remark_attachments)

        remaining = [
            attachment
            for attachment in self.attachments
            if attachment not in ordered
        ]
        ordered.extend(sorted(remaining, key=lambda attachment: (attachment.sort_order, attachment.id)))
        return ordered

    def _build_order_file_url(self, relative_path: str | None) -> str:
        if not relative_path:
            return ''
        return f'/uploads/qc/{self.id}/{relative_path}'

    @staticmethod
    def _display_filename(original_name: str | None, relative_path: str | None) -> str:
        if original_name:
            return original_name
        if relative_path:
            return relative_path.split('/')[-1]
        return ''

    @property
    def drawing_note_file_url(self) -> str:
        return self._build_order_file_url(self.drawing_note_file_path)

    @property
    def drawing_note_filename(self) -> str:
        return self._display_filename(self.drawing_note_original_name, self.drawing_note_file_path)

    @property
    def guide_certificate_file_url(self) -> str:
        return self._build_order_file_url(self.guide_certificate_file_path)

    @property
    def guide_certificate_filename(self) -> str:
        return self._display_filename(self.guide_certificate_original_name, self.guide_certificate_file_path)

    @property
    def remark_note_file_url(self) -> str:
        return self._build_order_file_url(self.remark_note_file_path)

    @property
    def remark_note_filename(self) -> str:
        return self._display_filename(self.remark_note_original_name, self.remark_note_file_path)

    def can_be_edited_by(self, user: 'User') -> bool:
        """判断指定用户是否可以编辑此订单"""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_work_order_edit'):
            return self.status in ['draft', 'qc_pending', 'rejected']
        if user.has_ai_cats_identity('controller', 'production') and user.has_ai_cats_permission('qc_work_order_edit') and self.controller_id == user.id:
            return self.status in ['draft', 'qc_pending', 'rejected']
        return False

    def can_be_deleted_by(self, user: 'User') -> bool:
        """判断指定用户是否可以删除此订单"""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager and user.has_ai_cats_permission('qc_work_order_delete'):
            return self.status in ['draft', 'qc_pending', 'rejected']
        if user.has_ai_cats_identity('controller', 'production') and user.has_ai_cats_permission('qc_work_order_delete') and self.controller_id == user.id:
            return self.status in ['draft', 'qc_pending', 'rejected']
        return False

    def can_be_viewed_by(self, user: 'User') -> bool:
        """判断指定用户是否有权查看此订单"""
        if user.is_superadmin:
            return True
        if user.ai_cats_is_manager:
            return any(
                user.has_ai_cats_permission(permission_code)
                for permission_code in (
                    'qc_work_order_view',
                    'qc_work_order_create',
                    'qc_work_order_edit',
                    'qc_work_order_delete',
                    'qc_inspection_view',
                    'qc_inspection_perform',
                    'qc_acceptance_perform',
                    'qc_acceptance_rollback',
                )
            )
        if self.status == 'draft':
            return (
                user.has_ai_cats_identity('controller', 'production')
                and self.controller_id == user.id
                and any(
                    user.has_ai_cats_permission(permission_code)
                    for permission_code in (
                        'qc_work_order_view',
                        'qc_work_order_create',
                        'qc_work_order_edit',
                        'qc_work_order_delete',
                    )
                )
            )
        if user.has_ai_cats_identity('controller', 'production') and self.controller_id == user.id:
            return any(
                user.has_ai_cats_permission(permission_code)
                for permission_code in (
                    'qc_work_order_view',
                    'qc_work_order_create',
                    'qc_work_order_edit',
                    'qc_work_order_delete',
                    'qc_inspection_view',
                    'qc_acceptance_perform',
                    'qc_acceptance_rollback',
                )
            )
        if user.has_ai_cats_identity('supplier', 'production') and self.inspector_id == user.id:
            return any(
                user.has_ai_cats_permission(permission_code)
                for permission_code in (
                    'qc_inspection_view',
                    'qc_inspection_perform',
                    'qc_acceptance_perform',
                )
            )
        return False


class QCWorkpieceStockHistory(db.Model):
    """Immutable stock movement history for one QC workpiece."""

    __tablename__ = 'qc_workpiece_stock_histories'

    id: Mapped[int] = mapped_column(primary_key=True)
    workpiece_id: Mapped[int] = mapped_column(ForeignKey('qc_workpieces.id', ondelete='CASCADE'), nullable=False, index=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey('qc_work_orders.id', ondelete='SET NULL'), nullable=True, index=True)
    acceptance_batch_id: Mapped[int] = mapped_column(ForeignKey('qc_acceptance_batches.id', ondelete='SET NULL'), nullable=True, index=True)
    assembly_order_id: Mapped[int] = mapped_column(ForeignKey('assembly_orders.id', ondelete='SET NULL'), nullable=True, index=True)
    assembly_acceptance_batch_id: Mapped[int] = mapped_column(ForeignKey('assembly_acceptance_batches.id', ondelete='SET NULL'), nullable=True, index=True)
    outbound_order_id: Mapped[int] = mapped_column(ForeignKey('assembly_outbound_orders.id', ondelete='SET NULL'), nullable=True, index=True)
    outbound_batch_id: Mapped[int] = mapped_column(ForeignKey('assembly_outbound_batches.id', ondelete='SET NULL'), nullable=True, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False, default='acceptance_in')
    batch_no: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    production_quantity: Mapped[float] = mapped_column(Float, nullable=True)
    accepted_quantity: Mapped[float] = mapped_column(Float, nullable=True)
    quantity_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stock_before: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stock_after: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    workpiece: Mapped['QCWorkpiece'] = relationship(back_populates='stock_histories')
    work_order: Mapped['QCWorkOrder'] = relationship(foreign_keys=[work_order_id])
    acceptance_batch: Mapped['QCAcceptanceBatch'] = relationship(foreign_keys=[acceptance_batch_id])
    assembly_order: Mapped['AssemblyOrder'] = relationship(foreign_keys=[assembly_order_id])
    assembly_acceptance_batch: Mapped['AssemblyAcceptanceBatch'] = relationship(foreign_keys=[assembly_acceptance_batch_id])
    outbound_order: Mapped['AssemblyOutboundOrder'] = relationship(foreign_keys=[outbound_order_id])
    outbound_batch: Mapped['AssemblyOutboundBatch'] = relationship(foreign_keys=[outbound_batch_id])
    operator: Mapped['User'] = relationship(foreign_keys=[operator_id])

    @property
    def change_type_display(self) -> str:
        if self.change_type == 'acceptance_in':
            return '验收入库'
        if self.change_type == 'acceptance_reverse':
            return '撤销入库'
        if self.change_type == 'outbound_out':
            return '出厂扣减'
        if self.change_type == 'assembly_consumption':
            return '装配扣减'
        if self.change_type == 'assembly_reverse':
            return '装配撤销'
        return self.change_type

    @property
    def operator_name(self) -> str:
        if self.operator:
            return self.operator.real_name or self.operator.username
        return '系统'


class QCWorkpieceAttachment(db.Model):
    """QC 工件库附件表。"""
    __tablename__ = 'qc_workpiece_attachments'

    id: Mapped[int] = mapped_column(primary_key=True)
    workpiece_id: Mapped[int] = mapped_column(ForeignKey('qc_workpieces.id', ondelete='CASCADE'), nullable=False)
    attach_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    is_required: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    workpiece: Mapped['QCWorkpiece'] = relationship(back_populates='attachments')

    @property
    def file_url(self) -> str:
        """获取文件访问 URL。"""
        if not self.file_path:
            return ''
        return f'/uploads/qc/workpieces/{self.workpiece_id}/{self.file_path}'

    @property
    def is_image(self) -> bool:
        """是否是图片文件。"""
        if not self.file_type:
            return False
        return self.file_type.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']

    @property
    def display_title(self) -> str:
        """Return a normalized attachment title."""
        if self.attach_type == 'drawing':
            return self.title or f'图纸{self.sort_order + 1}'
        if self.attach_type == QC_QUALITY_MATERIAL_ATTACHMENT_TYPE:
            return self.title or f'质检材料{self.sort_order + 1}'
        if self.attach_type in QC_GUIDE_ATTACHMENT_TYPES:
            return normalize_qc_guide_title(self.title, self.sort_order + 1)
        if self.attach_type == 'coa_template':
            return self.title or 'COA报告模板'
        return self.title or '备注'

    def __repr__(self):
        return f'<QCWorkpieceAttachment {self.workpiece_id}:{self.attach_type}>'


class QCWorkOrderAttachment(db.Model):
    """QC 工件订单附件表 - 图纸、作业指导书、备注"""
    __tablename__ = 'qc_work_order_attachments'

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey('qc_work_orders.id', ondelete='CASCADE'), nullable=False)
    attach_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    is_required: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    work_order: Mapped['QCWorkOrder'] = relationship(back_populates='attachments')
    inspection_records: Mapped[list['QCInspectionRecord']] = relationship(
        back_populates='attachment',
        cascade='all, delete-orphan'
    )

    @property
    def file_url(self) -> str:
        """获取文件访问URL"""
        if not self.file_path:
            return ''
        return f'/uploads/qc/{self.work_order_id}/{self.file_path}'

    @property
    def is_image(self) -> bool:
        """是否是图片文件"""
        if not self.file_type:
            return False
        return self.file_type.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']

    @property
    def display_title(self) -> str:
        """Return a normalized attachment title."""
        if self.attach_type == 'drawing':
            return self.title or f'图纸{self.sort_order + 1}'
        if self.attach_type == QC_QUALITY_MATERIAL_ATTACHMENT_TYPE:
            return self.title or f'质检材料{self.sort_order + 1}'
        if self.attach_type in QC_GUIDE_ATTACHMENT_TYPES:
            return normalize_qc_guide_title(self.title, self.sort_order + 1)
        return self.title or '备注'

    @property
    def requires_report(self) -> bool:
        """Whether the inspection row requires a qualified-report upload."""
        return self.attach_type in QC_GUIDE_ATTACHMENT_TYPES

    @property
    def report_label(self) -> str:
        """Return the report-column label for the inspection page."""
        if self.attach_type == 'drawing':
            return '图纸确认函（可选）'
        if self.attach_type == QC_QUALITY_MATERIAL_ATTACHMENT_TYPE:
            return '质检材料确认函（可选）'
        if self.attach_type in QC_GUIDE_ATTACHMENT_TYPES:
            return '合格报告'
        return ''

    @property
    def extra_file_label(self) -> str:
        """Return the label used by section-level supplemental uploads."""
        if self.attach_type == 'remark':
            return '批注信息'
        if self.attach_type in QC_GUIDE_ATTACHMENT_TYPES:
            return '生产凭证'
        return '批注信息'

    def __repr__(self):
        return f'<QCWorkOrderAttachment {self.work_order_id}:{self.attach_type}>'


class QCInspectionRecord(db.Model):
    """QC 质检记录表"""
    __tablename__ = 'qc_inspection_records'

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey('qc_work_orders.id', ondelete='CASCADE'), nullable=False)
    inspector_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    attachment_id: Mapped[int] = mapped_column(ForeignKey('qc_work_order_attachments.id'), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default='draft')
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    report_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    report_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    report_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    work_order: Mapped['QCWorkOrder'] = relationship(back_populates='inspection_records')
    inspector: Mapped['User'] = relationship(foreign_keys=[inspector_id])
    attachment: Mapped['QCWorkOrderAttachment'] = relationship(back_populates='inspection_records')

    def __repr__(self):
        return f'<QCInspectionRecord {self.work_order_id}:{self.attachment_id}:{self.result}>'

    @property
    def is_pass(self) -> bool:
        return self.result == 'pass'

    @property
    def is_fail(self) -> bool:
        return self.result == 'fail'

    @property
    def is_draft(self) -> bool:
        return self.result == 'draft'

    @property
    def has_report(self) -> bool:
        return bool(self.report_file_path)

    @property
    def report_filename(self) -> str:
        if self.report_original_name:
            return self.report_original_name
        if self.report_file_path:
            return self.report_file_path.split('/')[-1]
        return ''

    @property
    def report_url(self) -> str:
        if not self.report_file_path:
            return ''
        return f'/uploads/qc/{self.work_order_id}/{self.report_file_path}'


class QCAcceptanceBatch(db.Model):
    """One partial or final acceptance delivery batch for a QC work order."""
    __tablename__ = 'qc_acceptance_batches'

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey('qc_work_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    production_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    accepted_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    inventory_posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    work_order: Mapped['QCWorkOrder'] = relationship(back_populates='acceptance_batches')
    signatures: Mapped[list['QCAcceptanceSignature']] = relationship(
        back_populates='acceptance_batch',
        cascade='all, delete-orphan',
        order_by='QCAcceptanceSignature.id'
    )

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def signatures_by_role(self) -> dict[str, 'QCAcceptanceSignature']:
        return {signature.signer_role: signature for signature in self.signatures}

    def __repr__(self):
        return f'<QCAcceptanceBatch {self.work_order_id}:{self.accepted_quantity}>'


class QCAcceptanceSignature(db.Model):
    """QC 验收签字记录表"""
    __tablename__ = 'qc_acceptance_signatures'

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey('qc_work_orders.id', ondelete='CASCADE'), nullable=False)
    acceptance_batch_id: Mapped[int] = mapped_column(ForeignKey('qc_acceptance_batches.id', ondelete='CASCADE'), nullable=True, index=True)
    signer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    signer_role: Mapped[str] = mapped_column(String(50), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    work_order: Mapped['QCWorkOrder'] = relationship(back_populates='signatures')
    acceptance_batch: Mapped['QCAcceptanceBatch'] = relationship(back_populates='signatures')
    signer: Mapped['User'] = relationship(foreign_keys=[signer_id])

    @property
    def signer_role_display(self) -> str:
        return get_qc_signer_role_display(self.signer_role)

    def __repr__(self):
        return f'<QCAcceptanceSignature {self.work_order_id}:{self.signer_role}>'


class QCWorkOrderHistory(db.Model):
    """Immutable operation history for a QC work order."""
    __tablename__ = 'qc_work_order_histories'

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey('qc_work_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    work_order: Mapped['QCWorkOrder'] = relationship(back_populates='histories')
    operator: Mapped['User'] = relationship(foreign_keys=[operator_id])

    @property
    def operator_name(self) -> str:
        if self.operator:
            return self.operator.real_name or self.operator.username
        return '系统'

    def __repr__(self):
        return f'<QCWorkOrderHistory {self.work_order_id}:{self.action}>'


class ResearchProject(db.Model):
    """Research project template for the AI CATS research module."""

    __tablename__ = 'research_projects'

    id: Mapped[int] = mapped_column(primary_key=True)
    project_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    project_category: Mapped[str] = mapped_column(String(50), nullable=True, index=True)
    research_direction: Mapped[str] = mapped_column(String(200), nullable=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    creator: Mapped['User'] = relationship(foreign_keys=[creator_id])
    attachments: Mapped[list['ResearchProjectAttachment']] = relationship(
        back_populates='project',
        cascade='all, delete-orphan',
        order_by='ResearchProjectAttachment.sort_order'
    )
    batches: Mapped[list['ResearchBatch']] = relationship(back_populates='project')

    def __repr__(self):
        return f'<ResearchProject {self.project_code}>'

    @property
    def initiation_materials(self) -> list['ResearchProjectAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'initiation_material'
        ]

    @property
    def research_materials(self) -> list['ResearchProjectAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'research_material'
        ]

    @property
    def experiment_plans(self) -> list['ResearchProjectAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'experiment_plan'
        ]

    @property
    def validation_items(self) -> list['ResearchProjectAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'validation_item'
        ]

    @property
    def risk_notes(self) -> list['ResearchProjectAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'risk_note'
        ]


class ResearchBatch(db.Model):
    """Research execution batch."""

    __tablename__ = 'research_batches'

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('research_projects.id', ondelete='SET NULL'), nullable=True, index=True)
    project_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    sample_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    researcher_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default='draft', nullable=False, index=True)
    research_submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    review_completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    returned_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    return_reason: Mapped[str] = mapped_column(Text, nullable=True)
    initiation_note_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    initiation_note_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    initiation_note_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    phase_result_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    phase_result_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    phase_result_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    supplementary_note_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    supplementary_note_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    supplementary_note_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    project: Mapped['ResearchProject'] = relationship(back_populates='batches')
    researcher: Mapped['User'] = relationship(foreign_keys=[researcher_id])
    reviewer: Mapped['User'] = relationship(foreign_keys=[reviewer_id])
    attachments: Mapped[list['ResearchBatchAttachment']] = relationship(
        back_populates='batch',
        cascade='all, delete-orphan',
        order_by='ResearchBatchAttachment.sort_order'
    )
    review_records: Mapped[list['ResearchReviewRecord']] = relationship(
        back_populates='batch',
        cascade='all, delete-orphan',
        order_by='ResearchReviewRecord.id'
    )
    signatures: Mapped[list['ResearchAcceptanceSignature']] = relationship(
        back_populates='batch',
        cascade='all, delete-orphan',
        order_by='ResearchAcceptanceSignature.id'
    )
    histories: Mapped[list['ResearchBatchHistory']] = relationship(
        back_populates='batch',
        cascade='all, delete-orphan',
        order_by='ResearchBatchHistory.created_at.desc(), ResearchBatchHistory.id.desc()'
    )

    def __repr__(self):
        return f'<ResearchBatch {self.batch_no}>'

    def _attachments_of_type(self, attach_type: str) -> list['ResearchBatchAttachment']:
        """Return batch attachments filtered by one type."""
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == attach_type
        ]

    def get_status_display(self) -> dict:
        """Return the display badge for the current research status."""
        return RESEARCH_STATUS_DISPLAY.get(self.status, RESEARCH_STATUS_DISPLAY['draft'])

    def get_acceptance_status_display(self) -> dict:
        """Return the acceptance progress display badge."""
        if self.status == 'accepted':
            return RESEARCH_STATUS_DISPLAY['accepted']
        if self.status == 'review_completed':
            signed_roles = {signature.signer_role for signature in self.signatures}
            if signed_roles:
                return {'text': '待另一方确认', 'badge': 'bg-warning text-dark'}
        return self.get_status_display()

    @property
    def initiation_note_file_url(self) -> str:
        if not self.initiation_note_file_path:
            return ''
        return f'/uploads/research/batches/{self.id}/{self.initiation_note_file_path}'

    @property
    def initiation_note_filename(self) -> str:
        return self.initiation_note_original_name or (
            self.initiation_note_file_path.split('/')[-1] if self.initiation_note_file_path else ''
        )

    @property
    def phase_result_file_url(self) -> str:
        if not self.phase_result_file_path:
            return ''
        return f'/uploads/research/batches/{self.id}/{self.phase_result_file_path}'

    @property
    def phase_result_filename(self) -> str:
        return self.phase_result_original_name or (
            self.phase_result_file_path.split('/')[-1] if self.phase_result_file_path else ''
        )

    @property
    def supplementary_note_file_url(self) -> str:
        if not self.supplementary_note_file_path:
            return ''
        return f'/uploads/research/batches/{self.id}/{self.supplementary_note_file_path}'

    @property
    def supplementary_note_filename(self) -> str:
        return self.supplementary_note_original_name or (
            self.supplementary_note_file_path.split('/')[-1] if self.supplementary_note_file_path else ''
        )

    @property
    def initiation_materials(self) -> list['ResearchBatchAttachment']:
        return self._attachments_of_type('initiation_material')

    @property
    def research_materials(self) -> list['ResearchBatchAttachment']:
        return self._attachments_of_type('research_material')

    @property
    def experiment_plans(self) -> list['ResearchBatchAttachment']:
        return self._attachments_of_type('experiment_plan')

    @property
    def validation_items(self) -> list['ResearchBatchAttachment']:
        return self._attachments_of_type('validation_item')

    @property
    def risk_notes(self) -> list['ResearchBatchAttachment']:
        return self._attachments_of_type('risk_note')

    @property
    def project_display_name(self) -> str:
        """Return the best available display name for the linked research project."""
        if self.project:
            code = (self.project.project_code or '').strip()
            name = (self.project.project_name or '').strip()
            if code and name:
                return f'{code} / {name}'
            if code or name:
                return code or name
        return (self.project_name_snapshot or '').strip() or '-'

    @property
    def signatures_by_role(self) -> dict[str, 'ResearchAcceptanceSignature']:
        return {signature.signer_role: signature for signature in self.signatures}


class ResearchProjectAttachment(db.Model):
    """Attachment for research project templates."""

    __tablename__ = 'research_project_attachments'

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('research_projects.id', ondelete='CASCADE'), nullable=False, index=True)
    attach_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    is_required: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    project: Mapped['ResearchProject'] = relationship(back_populates='attachments')

    @property
    def file_url(self) -> str:
        if not self.file_path:
            return ''
        return f'/uploads/research/projects/{self.project_id}/{self.file_path}'

    @property
    def is_image(self) -> bool:
        return bool(self.file_type and self.file_type.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'])

    @property
    def display_title(self) -> str:
        prefix = RESEARCH_ATTACHMENT_TITLE_PREFIX.get(self.attach_type, '研究附件')
        return self.title or f'{prefix}{self.sort_order + 1}'


class ResearchBatchAttachment(db.Model):
    """Attachment snapshot or runtime upload for a research batch."""

    __tablename__ = 'research_batch_attachments'

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('research_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    attach_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), default='project_snapshot', nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    is_required: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    batch: Mapped['ResearchBatch'] = relationship(back_populates='attachments')
    review_records: Mapped[list['ResearchReviewRecord']] = relationship(
        back_populates='attachment',
        cascade='all, delete-orphan'
    )

    @property
    def file_url(self) -> str:
        if not self.file_path:
            return ''
        return f'/uploads/research/batches/{self.batch_id}/{self.file_path}'

    @property
    def is_image(self) -> bool:
        return bool(self.file_type and self.file_type.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'])

    @property
    def display_title(self) -> str:
        prefix = RESEARCH_ATTACHMENT_TITLE_PREFIX.get(self.attach_type, '研究附件')
        return self.title or f'{prefix}{self.sort_order + 1}'

    @property
    def review_label(self) -> str:
        return RESEARCH_ATTACHMENT_TYPE_DISPLAY.get(self.attach_type, '研究附件')


class ResearchReviewRecord(db.Model):
    """Review record for a research batch attachment."""

    __tablename__ = 'research_review_records'

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('research_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey('research_batch_attachments.id', ondelete='CASCADE'), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default='draft')
    suggestion: Mapped[str] = mapped_column(Text, nullable=True)
    feedback_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    feedback_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    feedback_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    batch: Mapped['ResearchBatch'] = relationship(back_populates='review_records')
    reviewer: Mapped['User'] = relationship(foreign_keys=[reviewer_id])
    attachment: Mapped['ResearchBatchAttachment'] = relationship(back_populates='review_records')

    @property
    def feedback_file_url(self) -> str:
        if not self.feedback_file_path:
            return ''
        return f'/uploads/research/batches/{self.batch_id}/{self.feedback_file_path}'

    @property
    def feedback_filename(self) -> str:
        return self.feedback_original_name or (
            self.feedback_file_path.split('/')[-1] if self.feedback_file_path else ''
        )


class ResearchAcceptanceSignature(db.Model):
    """Acceptance signature for a research batch."""

    __tablename__ = 'research_acceptance_signatures'

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('research_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    acceptance_batch_id: Mapped[int] = mapped_column(ForeignKey('assembly_acceptance_batches.id', ondelete='CASCADE'), nullable=True, index=True)
    signer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    signer_role: Mapped[str] = mapped_column(String(50), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    batch: Mapped['ResearchBatch'] = relationship(back_populates='signatures')
    signer: Mapped['User'] = relationship(foreign_keys=[signer_id])

    @property
    def signer_role_display(self) -> str:
        if self.signer_role == 'researcher':
            return '研发人员'
        if self.signer_role == 'reviewer':
            return '指导/验收人员'
        return self.signer_role


class ResearchBatchHistory(db.Model):
    """Immutable history log for research batches."""

    __tablename__ = 'research_batch_histories'

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('research_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    batch: Mapped['ResearchBatch'] = relationship(back_populates='histories')
    operator: Mapped['User'] = relationship(foreign_keys=[operator_id])

    @property
    def operator_name(self) -> str:
        if not self.operator:
            return '系统'
        return self.operator.real_name or self.operator.username


class AssemblyProduct(db.Model):
    """Product template for the AI CATS assembly/shipping module."""

    __tablename__ = 'assembly_products'

    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    product_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    stock_quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    creator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    creator: Mapped['User'] = relationship(foreign_keys=[creator_id])
    components: Mapped[list['AssemblyProductComponent']] = relationship(
        back_populates='product',
        cascade='all, delete-orphan',
        order_by='AssemblyProductComponent.sort_order',
        foreign_keys='AssemblyProductComponent.product_id'
    )
    attachments: Mapped[list['AssemblyProductAttachment']] = relationship(
        back_populates='product',
        cascade='all, delete-orphan',
        order_by='AssemblyProductAttachment.sort_order'
    )
    orders: Mapped[list['AssemblyOrder']] = relationship(back_populates='product', foreign_keys='AssemblyOrder.product_id')
    stock_histories: Mapped[list['AssemblyProductStockHistory']] = relationship(
        back_populates='product',
        cascade='all, delete-orphan',
        order_by='AssemblyProductStockHistory.created_at.desc(), AssemblyProductStockHistory.id.desc()'
    )

    def __repr__(self):
        return f'<AssemblyProduct {self.product_code}>'

    @property
    def product_level_display(self) -> str:
        return ASSEMBLY_PRODUCT_LEVEL_DISPLAY.get(int(self.product_level or 1), '一级产品库')

    @property
    def assembly_sheet_attachments(self) -> list['AssemblyProductAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'assembly_sheet'
        ]

    @property
    def remark_attachments(self) -> list['AssemblyProductAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'remark'
        ]

    @property
    def coa_template_attachments(self) -> list['AssemblyProductAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'coa_template'
        ]

    @property
    def coa_template_attachment(self) -> 'AssemblyProductAttachment | None':
        return self.coa_template_attachments[0] if self.coa_template_attachments else None


class AssemblyProductComponent(db.Model):
    """BOM row for an assembly product."""

    __tablename__ = 'assembly_product_components'

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('assembly_products.id', ondelete='CASCADE'), nullable=False, index=True)
    component_type: Mapped[str] = mapped_column(String(20), default='workpiece', nullable=False, index=True)
    workpiece_id: Mapped[int] = mapped_column(ForeignKey('qc_workpieces.id', ondelete='RESTRICT'), nullable=True, index=True)
    component_product_id: Mapped[int] = mapped_column(ForeignKey('assembly_products.id', ondelete='RESTRICT'), nullable=True, index=True)
    workpiece_code_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    workpiece_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity_per_unit: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    product: Mapped['AssemblyProduct'] = relationship(back_populates='components', foreign_keys=[product_id])
    workpiece: Mapped['QCWorkpiece'] = relationship(foreign_keys=[workpiece_id])
    component_product: Mapped['AssemblyProduct'] = relationship(foreign_keys=[component_product_id])

    def __repr__(self):
        return f'<AssemblyProductComponent {self.product_id}:{self.workpiece_code_snapshot}>'

    @property
    def component_type_display(self) -> str:
        if self.component_type == 'product':
            return self.component_product.product_level_display if self.component_product else '产品库'
        return '工件库'

    @property
    def component_stock_quantity(self) -> float:
        if self.component_type == 'product':
            return float(self.component_product.stock_quantity or 0) if self.component_product else 0.0
        return float(self.workpiece.stock_quantity or 0) if self.workpiece else 0.0

    @property
    def total_required_for_one(self) -> float:
        return float(self.quantity_per_unit or 0)


class AssemblyProductAttachment(db.Model):
    """Attachment for an assembly product template."""

    __tablename__ = 'assembly_product_attachments'

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('assembly_products.id', ondelete='CASCADE'), nullable=False, index=True)
    attach_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    is_required: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    product: Mapped['AssemblyProduct'] = relationship(back_populates='attachments')

    @property
    def file_url(self) -> str:
        if not self.file_path:
            return ''
        return f'/uploads/assembly/products/{self.product_id}/{self.file_path}'

    @property
    def is_image(self) -> bool:
        return bool(self.file_type and self.file_type.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'])

    @property
    def display_title(self) -> str:
        prefix = ASSEMBLY_PRODUCT_ATTACHMENT_TITLE_PREFIX.get(self.attach_type, '产品附件')
        if self.attach_type == 'coa_template':
            return self.title or 'COA报告模板'
        return self.title or f'{prefix}{self.sort_order + 1}'


class AssemblyProductStockHistory(db.Model):
    """Immutable stock movement history for one assembly product."""

    __tablename__ = 'assembly_product_stock_histories'

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('assembly_products.id', ondelete='CASCADE'), nullable=False, index=True)
    assembly_order_id: Mapped[int] = mapped_column(ForeignKey('assembly_orders.id', ondelete='SET NULL'), nullable=True, index=True)
    assembly_acceptance_batch_id: Mapped[int] = mapped_column(ForeignKey('assembly_acceptance_batches.id', ondelete='SET NULL'), nullable=True, index=True)
    outbound_order_id: Mapped[int] = mapped_column(ForeignKey('assembly_outbound_orders.id', ondelete='SET NULL'), nullable=True, index=True)
    outbound_batch_id: Mapped[int] = mapped_column(ForeignKey('assembly_outbound_batches.id', ondelete='SET NULL'), nullable=True, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False, default='acceptance_in')
    batch_no: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    production_quantity: Mapped[float] = mapped_column(Float, nullable=True)
    accepted_quantity: Mapped[float] = mapped_column(Float, nullable=True)
    quantity_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stock_before: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stock_after: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    product: Mapped['AssemblyProduct'] = relationship(back_populates='stock_histories')
    assembly_order: Mapped['AssemblyOrder'] = relationship(foreign_keys=[assembly_order_id])
    assembly_acceptance_batch: Mapped['AssemblyAcceptanceBatch'] = relationship(foreign_keys=[assembly_acceptance_batch_id])
    outbound_order: Mapped['AssemblyOutboundOrder'] = relationship(foreign_keys=[outbound_order_id])
    outbound_batch: Mapped['AssemblyOutboundBatch'] = relationship(foreign_keys=[outbound_batch_id])
    operator: Mapped['User'] = relationship(foreign_keys=[operator_id])

    @property
    def change_type_display(self) -> str:
        if self.change_type == 'acceptance_in':
            return '验收入库'
        if self.change_type == 'acceptance_reverse':
            return '撤销入库'
        if self.change_type == 'assembly_consumption':
            return '装配扣减'
        if self.change_type == 'assembly_reverse':
            return '装配撤销'
        if self.change_type == 'outbound_out':
            return '出厂扣减'
        return self.change_type

    @property
    def operator_name(self) -> str:
        if self.operator:
            return self.operator.real_name or self.operator.username
        return '系统'


class AssemblyOrder(db.Model):
    """Assembly work order that consumes workpiece inventory."""

    __tablename__ = 'assembly_orders'

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('assembly_products.id', ondelete='SET NULL'), nullable=True, index=True)
    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    controller_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    inspector_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default='draft', index=True)
    assembly_submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    inspection_completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    inventory_posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=True)
    registration_note_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    registration_note_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    registration_note_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    certificate_note_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    certificate_note_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    certificate_note_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    remark_note_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    remark_note_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    remark_note_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    product: Mapped['AssemblyProduct'] = relationship(back_populates='orders', foreign_keys=[product_id])
    controller: Mapped['User'] = relationship(foreign_keys=[controller_id])
    inspector: Mapped['User'] = relationship(foreign_keys=[inspector_id])
    components: Mapped[list['AssemblyOrderComponent']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='AssemblyOrderComponent.sort_order'
    )
    attachments: Mapped[list['AssemblyOrderAttachment']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='AssemblyOrderAttachment.sort_order'
    )
    inspection_records: Mapped[list['AssemblyInspectionRecord']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='AssemblyInspectionRecord.id'
    )
    acceptance_batches: Mapped[list['AssemblyAcceptanceBatch']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='AssemblyAcceptanceBatch.created_at.asc(), AssemblyAcceptanceBatch.id.asc()'
    )
    signatures: Mapped[list['AssemblyAcceptanceSignature']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='AssemblyAcceptanceSignature.id'
    )
    histories: Mapped[list['AssemblyOrderHistory']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='AssemblyOrderHistory.created_at.desc(), AssemblyOrderHistory.id.desc()'
    )

    def __repr__(self):
        return f'<AssemblyOrder {self.batch_no}>'

    def get_status_display(self) -> dict:
        return ASSEMBLY_STATUS_DISPLAY.get(self.status, ASSEMBLY_STATUS_DISPLAY['draft'])

    def get_acceptance_status_display(self) -> dict:
        if self.status == 'accepted':
            return ASSEMBLY_STATUS_DISPLAY['accepted']
        if self.status == 'inspection_completed':
            active_batch = self.active_acceptance_batch
            if active_batch and active_batch.signatures:
                return {'text': '待另一方确认', 'badge': 'bg-warning text-dark'}
            return {'text': '待验收确认', 'badge': 'bg-primary'}
        return self.get_status_display()

    @property
    def completed_acceptance_batches(self) -> list['AssemblyAcceptanceBatch']:
        return [batch for batch in self.acceptance_batches if batch.completed_at]

    @property
    def active_acceptance_batch(self) -> 'AssemblyAcceptanceBatch | None':
        for batch in reversed(self.acceptance_batches):
            if not batch.completed_at:
                return batch
        return None

    @property
    def actual_delivered_quantity(self) -> float:
        return sum(float(batch.accepted_quantity or 0) for batch in self.acceptance_batches if batch.completed_at)

    @property
    def remaining_acceptance_quantity(self) -> float:
        return max(0.0, float(self.quantity or 0) - self.actual_delivered_quantity)

    @property
    def product_display_name(self) -> str:
        if self.product:
            code = (self.product.product_code or '').strip()
            name = (self.product.product_name or '').strip()
            if code and name:
                return f'{code} / {name}'
            if code or name:
                return code or name
        return (self.product_name_snapshot or '').strip() or '-'

    @property
    def assembly_record_attachments(self) -> list['AssemblyOrderAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'assembly_record'
        ]

    @property
    def certificate_attachments(self) -> list['AssemblyOrderAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'certificate'
        ]

    @property
    def remark_attachments(self) -> list['AssemblyOrderAttachment']:
        return [
            attachment for attachment in self.attachments
            if attachment.attach_type == 'remark'
        ]

    @property
    def ordered_attachments(self) -> list['AssemblyOrderAttachment']:
        ordered: list['AssemblyOrderAttachment'] = []
        ordered.extend(self.assembly_record_attachments)
        ordered.extend(self.certificate_attachments)
        ordered.extend(self.remark_attachments)

        remaining = [
            attachment
            for attachment in self.attachments
            if attachment not in ordered
        ]
        ordered.extend(sorted(remaining, key=lambda attachment: (attachment.sort_order, attachment.id)))
        return ordered

    @property
    def signatures_by_role(self) -> dict[str, 'AssemblyAcceptanceSignature']:
        return {signature.signer_role: signature for signature in self.signatures}

    def _build_file_url(self, relative_path: str | None) -> str:
        if not relative_path:
            return ''
        return f'/uploads/assembly/orders/{self.id}/{relative_path}'

    @staticmethod
    def _display_filename(original_name: str | None, relative_path: str | None) -> str:
        if original_name:
            return original_name
        if relative_path:
            return relative_path.split('/')[-1]
        return ''

    @property
    def registration_note_file_url(self) -> str:
        return self._build_file_url(self.registration_note_file_path)

    @property
    def registration_note_filename(self) -> str:
        return self._display_filename(self.registration_note_original_name, self.registration_note_file_path)

    @property
    def certificate_note_file_url(self) -> str:
        return self._build_file_url(self.certificate_note_file_path)

    @property
    def certificate_note_filename(self) -> str:
        return self._display_filename(self.certificate_note_original_name, self.certificate_note_file_path)

    @property
    def remark_note_file_url(self) -> str:
        return self._build_file_url(self.remark_note_file_path)

    @property
    def remark_note_filename(self) -> str:
        return self._display_filename(self.remark_note_original_name, self.remark_note_file_path)


class AssemblyOrderComponent(db.Model):
    """Immutable BOM snapshot row captured on one assembly order."""

    __tablename__ = 'assembly_order_components'

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('assembly_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    component_type: Mapped[str] = mapped_column(String(20), default='workpiece', nullable=False, index=True)
    workpiece_id: Mapped[int] = mapped_column(ForeignKey('qc_workpieces.id', ondelete='SET NULL'), nullable=True, index=True)
    component_product_id: Mapped[int] = mapped_column(ForeignKey('assembly_products.id', ondelete='SET NULL'), nullable=True, index=True)
    workpiece_code_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    workpiece_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity_per_unit: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    total_required_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    order: Mapped['AssemblyOrder'] = relationship(back_populates='components')
    workpiece: Mapped['QCWorkpiece'] = relationship(foreign_keys=[workpiece_id])
    component_product: Mapped['AssemblyProduct'] = relationship(foreign_keys=[component_product_id])

    def __repr__(self):
        return f'<AssemblyOrderComponent {self.order_id}:{self.workpiece_code_snapshot}>'

    @property
    def component_type_display(self) -> str:
        if self.component_type == 'product':
            return self.component_product.product_level_display if self.component_product else '产品库'
        return '工件库'

    @property
    def available_stock(self) -> float:
        if self.component_type == 'product':
            return float(self.component_product.stock_quantity or 0) if self.component_product else 0.0
        return float(self.workpiece.stock_quantity or 0) if self.workpiece else 0.0


class AssemblyOrderAttachment(db.Model):
    """Attachment snapshot or runtime upload for one assembly order."""

    __tablename__ = 'assembly_order_attachments'

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('assembly_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    attach_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), default='product_snapshot', nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    is_required: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    order: Mapped['AssemblyOrder'] = relationship(back_populates='attachments')
    inspection_records: Mapped[list['AssemblyInspectionRecord']] = relationship(
        back_populates='attachment',
        cascade='all, delete-orphan'
    )

    @property
    def file_url(self) -> str:
        if not self.file_path:
            return ''
        return f'/uploads/assembly/orders/{self.order_id}/{self.file_path}'

    @property
    def is_image(self) -> bool:
        return bool(self.file_type and self.file_type.lower() in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'])

    @property
    def display_title(self) -> str:
        if self.attach_type == 'assembly_record':
            return self.title or f'生产登记单{self.sort_order + 1}'
        if self.attach_type == 'certificate':
            return self.title or f'生产合格证{self.sort_order + 1}'
        if self.attach_type == 'remark':
            return self.title or '备注'
        return self.title or '装配附件'

    @property
    def requires_report(self) -> bool:
        return self.attach_type in ['assembly_record', 'certificate']

    @property
    def report_label(self) -> str:
        if self.attach_type == 'assembly_record':
            return '生产登记单确认件（必选）'
        if self.attach_type == 'certificate':
            return '合格报告'
        return '附加文件'


class AssemblyInspectionRecord(db.Model):
    """Quality-inspection record for one assembly attachment."""

    __tablename__ = 'assembly_inspection_records'

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('assembly_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    inspector_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey('assembly_order_attachments.id', ondelete='CASCADE'), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(20), nullable=False, default='draft')
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    report_file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    report_file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    report_original_name: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    order: Mapped['AssemblyOrder'] = relationship(back_populates='inspection_records')
    inspector: Mapped['User'] = relationship(foreign_keys=[inspector_id])
    attachment: Mapped['AssemblyOrderAttachment'] = relationship(back_populates='inspection_records')

    @property
    def report_url(self) -> str:
        if not self.report_file_path:
            return ''
        return f'/uploads/assembly/orders/{self.order_id}/{self.report_file_path}'

    @property
    def report_filename(self) -> str:
        return self.report_original_name or (
            self.report_file_path.split('/')[-1] if self.report_file_path else ''
        )


class AssemblyAcceptanceBatch(db.Model):
    """One partial or final acceptance batch for an assembly order."""

    __tablename__ = 'assembly_acceptance_batches'

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('assembly_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    production_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    accepted_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    inventory_posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    order: Mapped['AssemblyOrder'] = relationship(back_populates='acceptance_batches')
    signatures: Mapped[list['AssemblyAcceptanceSignature']] = relationship(
        back_populates='acceptance_batch',
        cascade='all, delete-orphan',
        order_by='AssemblyAcceptanceSignature.id'
    )

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def signatures_by_role(self) -> dict[str, 'AssemblyAcceptanceSignature']:
        return {signature.signer_role: signature for signature in self.signatures}

    def __repr__(self):
        return f'<AssemblyAcceptanceBatch {self.order_id}:{self.accepted_quantity}>'


class AssemblyAcceptanceSignature(db.Model):
    """Acceptance signature for one assembly order."""

    __tablename__ = 'assembly_acceptance_signatures'

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('assembly_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    acceptance_batch_id: Mapped[int] = mapped_column(ForeignKey('assembly_acceptance_batches.id', ondelete='CASCADE'), nullable=True, index=True)
    signer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    signer_role: Mapped[str] = mapped_column(String(50), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    order: Mapped['AssemblyOrder'] = relationship(back_populates='signatures')
    acceptance_batch: Mapped['AssemblyAcceptanceBatch'] = relationship(back_populates='signatures')
    signer: Mapped['User'] = relationship(foreign_keys=[signer_id])

    @property
    def signer_role_display(self) -> str:
        if self.signer_role == 'qc_controller':
            return '质量控制人'
        if self.signer_role == 'qc_inspector':
            return '供应商'
        return self.signer_role


class AssemblyOrderHistory(db.Model):
    """Immutable history log for assembly orders."""

    __tablename__ = 'assembly_order_histories'

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('assembly_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    order: Mapped['AssemblyOrder'] = relationship(back_populates='histories')
    operator: Mapped['User'] = relationship(foreign_keys=[operator_id])

    @property
    def operator_name(self) -> str:
        if not self.operator:
            return '系统'
        return self.operator.real_name or self.operator.username


class AssemblyOutboundOrder(db.Model):
    """Outbound order for shipping any workpiece or assembly product."""

    __tablename__ = 'assembly_outbound_orders'

    id: Mapped[int] = mapped_column(primary_key=True)
    outbound_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, default='workpiece', index=True)
    workpiece_id: Mapped[int] = mapped_column(ForeignKey('qc_workpieces.id', ondelete='SET NULL'), nullable=True, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('assembly_products.id', ondelete='SET NULL'), nullable=True, index=True)
    item_code_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    item_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    planned_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    outbound_date: Mapped[datetime] = mapped_column(Date, nullable=True)
    initiator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default='confirming', index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    workpiece: Mapped['QCWorkpiece'] = relationship(foreign_keys=[workpiece_id])
    product: Mapped['AssemblyProduct'] = relationship(foreign_keys=[product_id])
    initiator: Mapped['User'] = relationship(foreign_keys=[initiator_id])
    batches: Mapped[list['AssemblyOutboundBatch']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='AssemblyOutboundBatch.created_at.asc(), AssemblyOutboundBatch.id.asc()'
    )
    signatures: Mapped[list['AssemblyOutboundSignature']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='AssemblyOutboundSignature.id'
    )
    histories: Mapped[list['AssemblyOutboundHistory']] = relationship(
        back_populates='order',
        cascade='all, delete-orphan',
        order_by='AssemblyOutboundHistory.created_at.desc(), AssemblyOutboundHistory.id.desc()'
    )

    def __repr__(self):
        return f'<AssemblyOutboundOrder {self.outbound_no}>'

    def get_status_display(self) -> dict:
        return ASSEMBLY_OUTBOUND_STATUS_DISPLAY.get(self.status, ASSEMBLY_OUTBOUND_STATUS_DISPLAY['confirming'])

    @property
    def completed_batches(self) -> list['AssemblyOutboundBatch']:
        return [batch for batch in self.batches if batch.completed_at]

    @property
    def active_batch(self) -> 'AssemblyOutboundBatch | None':
        for batch in reversed(self.batches):
            if not batch.completed_at:
                return batch
        return None

    @property
    def shipped_quantity(self) -> float:
        return sum(float(batch.outbound_quantity or 0) for batch in self.completed_batches)

    @property
    def remaining_quantity(self) -> float:
        return max(0.0, float(self.planned_quantity or 0) - self.shipped_quantity)

    @property
    def item_display_name(self) -> str:
        code = (self.item_code_snapshot or '').strip()
        name = (self.item_name_snapshot or '').strip()
        if code and name:
            return f'{code} / {name}'
        return code or name or '-'

    @property
    def item_type_display(self) -> str:
        if self.item_type == 'product' and self.product:
            return self.product.product_level_display
        if self.item_type == 'product':
            return '产品库'
        return '工件库'

    @property
    def inventory_item(self):
        return self.product if self.item_type == 'product' else self.workpiece

    @property
    def coa_template_attachment(self):
        item = self.inventory_item
        return item.coa_template_attachment if item else None


class AssemblyOutboundBatch(db.Model):
    """One confirmed or pending outbound shipment batch."""

    __tablename__ = 'assembly_outbound_batches'

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('assembly_outbound_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    outbound_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    inventory_posted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    order: Mapped['AssemblyOutboundOrder'] = relationship(back_populates='batches')
    signatures: Mapped[list['AssemblyOutboundSignature']] = relationship(
        back_populates='batch',
        cascade='all, delete-orphan',
        order_by='AssemblyOutboundSignature.id'
    )

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def signatures_by_role(self) -> dict[str, 'AssemblyOutboundSignature']:
        return {signature.signer_role: signature for signature in self.signatures}

    def __repr__(self):
        return f'<AssemblyOutboundBatch {self.order_id}:{self.outbound_quantity}>'


class AssemblyOutboundSignature(db.Model):
    """Signature for one outbound batch."""

    __tablename__ = 'assembly_outbound_signatures'

    id: Mapped[int] = mapped_column(primary_key=True)
    outbound_order_id: Mapped[int] = mapped_column(ForeignKey('assembly_outbound_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    outbound_batch_id: Mapped[int] = mapped_column(ForeignKey('assembly_outbound_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    signer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    signer_role: Mapped[str] = mapped_column(String(50), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    order: Mapped['AssemblyOutboundOrder'] = relationship(back_populates='signatures')
    batch: Mapped['AssemblyOutboundBatch'] = relationship(back_populates='signatures')
    signer: Mapped['User'] = relationship(foreign_keys=[signer_id])

    @property
    def signer_role_display(self) -> str:
        if self.signer_role == 'initiator':
            return '出厂发起人'
        if self.signer_role == 'approver':
            return '出厂验收人'
        return self.signer_role


class AssemblyOutboundHistory(db.Model):
    """Immutable history log for outbound orders."""

    __tablename__ = 'assembly_outbound_histories'

    id: Mapped[int] = mapped_column(primary_key=True)
    outbound_order_id: Mapped[int] = mapped_column(ForeignKey('assembly_outbound_orders.id', ondelete='CASCADE'), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)

    order: Mapped['AssemblyOutboundOrder'] = relationship(back_populates='histories')
    operator: Mapped['User'] = relationship(foreign_keys=[operator_id])

    @property
    def operator_name(self) -> str:
        if not self.operator:
            return '系统'
        return self.operator.real_name or self.operator.username
