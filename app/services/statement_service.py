from datetime import datetime
import json
from app import db
from app.models import Transaction, Statement, StatementItem, Company, Contract


class StatementService:
    """对账单服务类"""

    @staticmethod
    def _to_float2(value, default: float = 0.0) -> float:
        """Convert value to float with 2-decimal precision."""
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return default
    
    @staticmethod
    def generate_statement_no() -> str:
        """生成对账单编号
        
        格式: DZ + 年份(4位) + 序号(3位)
        示例: DZ2024001
        
        Returns:
            新的对账单编号
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
    def create_statement(company_name: str = None,
                        start_date=None,
                        end_date=None,
                        products: list = None,
                        contract_no: str = None,
                        product_codes: list = None,
                        department: str = None,
                        manager: str = None,
                        created_by: int = None,
                        current_user=None) -> dict:
        """[LOGIC-8] 创建对账单 - 支持多维度筛选 [v1.4] 添加创建人筛选和记录
        
        Args:
            company_name: 公司名称（可选）
            start_date: 起始日期（可选）
            end_date: 结束日期（可选）
            products: 产品名称筛选列表（可选，模糊匹配）
            contract_no: 合同编号筛选（可选）
            product_codes: 产品编码筛选列表（可选，精确匹配，支持多个逗号分隔）
            department: 部门筛选（可选）[v1.3]
            manager: 负责人筛选（可选）[v1.3]
            created_by: 创建人ID筛选（可选）[v1.4] 用于销售经理权限控制
            current_user: 当前登录用户（可选）[v1.4] 用于记录发起人
        
        Returns:
            包含对账单信息的字典，如果没有匹配记录返回None
        """
        from sqlalchemy import or_, and_
        
        # 1. 构建基础查询
        query = Transaction.query
        
        # 2. 应用公司筛选
        if company_name:
            query = query.filter(Transaction.company_name == company_name)
        
        # 3. 应用日期筛选
        if start_date:
            query = query.filter(Transaction.delivery_date >= start_date)
        if end_date:
            query = query.filter(Transaction.delivery_date <= end_date)
        
        # 4. 应用合同号筛选 [v1.3] 支持部门和负责人筛选 [v1.4] 添加创建人筛选
        if contract_no or department or manager or created_by:
            query = query.join(Transaction.contract)
            if contract_no:
                query = query.filter(Contract.contract_no.contains(contract_no))
            if department:
                query = query.filter(Contract.department.contains(department))
            if manager:
                query = query.filter(Contract.manager.contains(manager))
            if created_by:
                query = query.filter(Contract.created_by_id == created_by)
        
        # 5. 应用产品编码筛选（精确匹配，支持多个）
        if product_codes and len(product_codes) > 0 and product_codes[0]:
            code_filters = []
            for code in product_codes:
                if code.strip():
                    code_filters.append(Transaction.product_code == code.strip())
            if code_filters:
                query = query.filter(or_(*code_filters))
        
        # 6. 应用产品名称筛选（模糊匹配）
        if products and len(products) > 0 and products[0]:
            name_filters = []
            for product in products:
                if product.strip():
                    name_filters.append(Transaction.product_name.contains(product.strip()))
            if name_filters:
                query = query.filter(or_(*name_filters))
        
        # 7. 按发货日期排序
        transactions = query.order_by(Transaction.delivery_date).all()
        
        if not transactions:
            return None
        
        # 8. 计算总金额
        total_amount = sum(t.total_price_with_tax for t in transactions)
        
        # 9. 构建显示用的公司名（多个公司时显示"多家公司"）
        unique_companies = set(t.company_name for t in transactions)
        display_company = company_name if company_name else (
            list(unique_companies)[0] if len(unique_companies) == 1 else f"{len(unique_companies)}家公司"
        )
        
        # 10. 构建筛选条件JSON
        filter_conditions = {}
        if contract_no:
            filter_conditions['contract_no'] = contract_no
        if product_codes:
            filter_conditions['product_codes'] = product_codes
        if products:
            filter_conditions['product_names'] = products
        
        # 11. 生成对账单记录 [v1.4] 添加发起人信息
        statement = Statement(
            statement_no=StatementService.generate_statement_no(),
            company_name=display_company,
            filter_start_date=start_date,
            filter_end_date=end_date,
            filter_products=json.dumps(filter_conditions) if filter_conditions else None,
            statement_total=total_amount,
            record_count=len(transactions),
            created_by_id=current_user.id if current_user else None,
            department=current_user.department.name if current_user and current_user.department else None
        )
        
        db.session.add(statement)
        db.session.flush()  # 获取statement.id
        
        # 12. 创建明细关联（重新编号）
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
    
    @staticmethod
    def get_statement_by_no(statement_no: str) -> dict:
        """根据编号获取对账单详情
        
        Args:
            statement_no: 对账单编号
        
        Returns:
            对账单详情字典
        """
        statement = Statement.query.filter_by(statement_no=statement_no).first()
        
        if not statement:
            return None
        
        # 获取关联的交易记录
        items = StatementItem.query.filter_by(statement_id=statement.id)\
            .order_by(StatementItem.display_seq).all()
        
        transactions = []
        for item in items:
            trans = item.transaction
            trans.display_seq = item.display_seq
            transactions.append(trans)

        # 对账单详情总金额：按对应合同的实收金额（合同总价）汇总
        contract_ids = {tx.contract_id for tx in transactions if tx.contract_id}
        statement_total_receivable = StatementService._to_float2(statement.statement_total, 0.0)
        if contract_ids:
            contracts = Contract.query.filter(Contract.id.in_(contract_ids)).all()
            statement_total_receivable = StatementService._to_float2(
                sum(
                    (c.actual_received_value if c.actual_received_value is not None else c.total_value or 0.0)
                    for c in contracts
                ),
                statement_total_receivable
            )
        
        # [LOGIC-8] 解析筛选条件
        filter_conditions = {}
        if statement.filter_products:
            try:
                conditions = json.loads(statement.filter_products)
                if isinstance(conditions, list):
                    # 旧格式兼容：产品名称列表
                    filter_conditions = {'product_names': conditions}
                elif isinstance(conditions, dict):
                    # 新格式：条件字典
                    filter_conditions = conditions
            except:
                filter_conditions = {}
        
        return {
            'statement': statement,
            'transactions': transactions,
            'filter_products': filter_conditions.get('product_names'),
            'filter_conditions': filter_conditions,  # [LOGIC-8] 新增
            'statement_total_receivable': statement_total_receivable
        }
    
    @staticmethod
    def get_company_list() -> list:
        """获取所有公司名称列表
        
        Returns:
            公司名称列表
        """
        companies = Company.query.order_by(Company.name).all()
        return [c.name for c in companies]
    
    @staticmethod
    def delete_statement(statement_no: str) -> bool:
        """删除对账单
        
        Args:
            statement_no: 对账单编号
            
        Returns:
            删除成功返回True，否则返回False
        """
        try:
            statement = Statement.query.filter_by(statement_no=statement_no).first()
            if not statement:
                return False
            
            # 先删除关联的明细记录
            StatementItem.query.filter_by(statement_id=statement.id).delete()
            
            # 删除对账单
            db.session.delete(statement)
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            raise e
