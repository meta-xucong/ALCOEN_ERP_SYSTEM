"""
交易记录服务类
"""
from app import db
from app.models import Transaction


class TransactionService:
    """交易记录服务类"""
    
    @staticmethod
    def create_transaction(data: dict) -> Transaction:
        """创建交易记录
        
        Args:
            data: 交易数据字典
            
        Returns:
            创建的交易记录对象
        """
        transaction = Transaction(
            company_name=data['company_name'],
            product_id=data.get('product_id'),
            product_code=data['product_code'],
            product_name=data.get('product_name'),
            product_model=data.get('product_model'),
            product_type=data.get('product_type'),
            quantity=float(data['quantity']),
            unit=data['unit'],
            price_with_tax=float(data['price_with_tax']),
            handler=data.get('handler') or '系统录入',
            delivery_date=data['delivery_date'],
            invoice_date=data.get('invoice_date'),
            contract_no=data.get('contract_no'),
            remark=data.get('remark')
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        return transaction
    
    @staticmethod
    def update_transaction(transaction_id: int, data: dict) -> Transaction:
        """更新交易记录
        
        Args:
            transaction_id: 记录ID
            data: 更新数据字典
            
        Returns:
            更新后的交易记录对象
        """
        transaction = Transaction.query.get_or_404(transaction_id)
        
        transaction.company_name = data['company_name']
        transaction.product_id = data.get('product_id')
        transaction.product_code = data['product_code']
        transaction.product_name = data.get('product_name')
        transaction.product_model = data.get('product_model')
        transaction.product_type = data.get('product_type')
        transaction.quantity = float(data['quantity'])
        transaction.unit = data['unit']
        transaction.price_with_tax = float(data['price_with_tax'])
        transaction.handler = data.get('handler') or transaction.handler or '系统录入'
        transaction.delivery_date = data['delivery_date']
        transaction.invoice_date = data.get('invoice_date')
        transaction.contract_no = data.get('contract_no')
        transaction.remark = data.get('remark')
        
        db.session.commit()
        
        return transaction
    
    @staticmethod
    def delete_transaction(transaction_id: int) -> bool:
        """删除交易记录
        
        Args:
            transaction_id: 记录ID
            
        Returns:
            是否删除成功
        """
        transaction = Transaction.query.get_or_404(transaction_id)
        db.session.delete(transaction)
        db.session.commit()
        return True
    
    @staticmethod
    def get_transaction_list(
        page: int = 1, 
        per_page: int = 20,
        company_name: str = None,
        product_name: str = None,
        product_code: str = None,
        start_date=None,
        end_date=None
    ):
        """获取交易记录列表（分页）
        
        Args:
            page: 页码
            per_page: 每页数量
            company_name: 公司名称筛选
            product_name: 产品名称筛选
            product_code: 产品编码筛选（v1.1新增）
            start_date: 开始日期（v1.1新增）
            end_date: 结束日期（v1.1新增）
            
        Returns:
            Pagination对象
        """
        query = Transaction.query
        
        if company_name:
            query = query.filter(Transaction.company_name.contains(company_name))
        
        if product_name:
            query = query.filter(Transaction.product_name.contains(product_name))
        
        # v1.1: 新增产品编码筛选
        if product_code:
            query = query.filter(Transaction.product_code.contains(product_code))
        
        # v1.1: 新增发货日期范围筛选
        if start_date:
            query = query.filter(Transaction.delivery_date >= start_date)
        
        if end_date:
            query = query.filter(Transaction.delivery_date <= end_date)
        
        return query.order_by(Transaction.delivery_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    
    @staticmethod
    def get_products_by_company(company_name: str) -> list:
        """获取指定公司的所有产品编码（用于筛选）
        
        Args:
            company_name: 公司名称
            
        Returns:
            产品编码列表
        """
        codes = db.session.query(Transaction.product_code)\
            .filter(Transaction.company_name == company_name)\
            .distinct()\
            .order_by(Transaction.product_code)\
            .all()
        
        return [c[0] for c in codes]
    
    @staticmethod
    def get_transaction_by_id(transaction_id: int) -> Transaction:
        """根据ID获取交易记录"""
        return Transaction.query.get_or_404(transaction_id)
