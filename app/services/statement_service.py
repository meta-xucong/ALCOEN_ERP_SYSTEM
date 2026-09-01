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
                        company_names: list[str] = None,
                        start_date=None,
                        end_date=None,
                        date_filter_mode: str = 'delivery_date',
                        products: list = None,
                        product_types: list = None,
                        contract_no: str = None,
                        product_codes: list = None,
                        department: str | list[str] = None,
                        manager: str = None,
                        created_by: int = None,
                        current_user=None) -> dict:
        """[LOGIC-8] 创建对账单 - 支持多维度筛选 [v1.4] 添加创建人筛选和记录
        
        Args:
            company_name: 单个公司名称（兼容旧调用，可选）
            company_names: 公司名称列表（可选，聚合多个公司）
            start_date: 起始日期（可选）
            end_date: 结束日期（可选）
            date_filter_mode: 日期范围依据（发货日期或合同创建日期）
            products: 产品名称筛选列表（可选，模糊匹配）
            product_types: 产品类型筛选列表（可选，模糊匹配）
            contract_no: 合同编号筛选（可选）
            product_codes: 产品编码筛选列表（可选，精确匹配，支持多个逗号分隔）
            department: 部门筛选（可选）[v1.3]
            manager: 负责人筛选（可选）[v1.3]
            created_by: 创建人ID筛选（可选）[v1.4] 用于销售经理权限控制
            current_user: 当前登录用户（可选）[v1.4] 用于记录发起人
        
        Returns:
            包含对账单信息的字典，如果没有匹配记录返回None
        """
        from sqlalchemy import func, or_

        if current_user and current_user.is_department_pm():
            if not isinstance(department, str) or not current_user.belongs_to_department(department):
                raise ValueError("Statement department is outside the current user's scope")
        
        # 1. 构建基础查询
        query = Transaction.query
        
        # 2. Apply the selected company cards as one aggregated company scope.
        normalized_company_names = []
        seen_company_names = set()
        for raw_company_name in company_names or []:
            normalized_company_name = (raw_company_name or '').strip()
            if normalized_company_name and normalized_company_name not in seen_company_names:
                normalized_company_names.append(normalized_company_name)
                seen_company_names.add(normalized_company_name)
        if not normalized_company_names and company_name:
            normalized_company_names.append(company_name.strip())

        if normalized_company_names:
            query = query.filter(Transaction.company_name.in_(normalized_company_names))
        elif company_name:
            query = query.filter(Transaction.company_name == company_name)
        
        date_filter_mode = (
            date_filter_mode
            if date_filter_mode in {'delivery_date', 'contract_created_at'}
            else 'delivery_date'
        )
        needs_contract_join = (
            date_filter_mode == 'contract_created_at'
            or bool(contract_no or department or manager or created_by)
        )
        if needs_contract_join:
            query = query.join(Transaction.contract)

        # 3. 应用日期筛选
        if start_date:
            if date_filter_mode == 'contract_created_at':
                query = query.filter(func.date(Contract.created_at) >= start_date.isoformat())
            else:
                query = query.filter(Transaction.delivery_date >= start_date)
        if end_date:
            if date_filter_mode == 'contract_created_at':
                query = query.filter(func.date(Contract.created_at) <= end_date.isoformat())
            else:
                query = query.filter(Transaction.delivery_date <= end_date)

        # 4. 应用合同号筛选 [v1.3] 支持部门和负责人筛选 [v1.4] 添加创建人筛选
        if contract_no or department or manager or created_by:
            if contract_no:
                query = query.filter(Contract.contract_no.contains(contract_no))
            if isinstance(department, (list, tuple, set)):
                department_names = [name for name in department if name]
                query = query.filter(
                    Contract.department.in_(department_names)
                    if department_names
                    else False
                )
            elif department:
                query = query.filter(Contract.department == department)
            if manager:
                query = query.filter(Contract.manager.contains(manager))
            if created_by:
                query = query.filter(Contract.created_by_id == created_by)
        
        # 5. 应用产品编码筛选（模糊匹配，支持多个）
        if product_codes and len(product_codes) > 0 and product_codes[0]:
            code_filters = []
            for code in product_codes:
                if code.strip():
                    code_filters.append(Transaction.product_code.contains(code.strip()))
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

        # 7. 应用产品类型筛选（模糊匹配）
        if product_types and len(product_types) > 0 and product_types[0]:
            type_filters = []
            for product_type in product_types:
                if product_type.strip():
                    type_filters.append(
                        Transaction.product_type.contains(product_type.strip())
                    )
            if type_filters:
                query = query.filter(or_(*type_filters))

        # 8. 对账单明细始终按发货日期展示
        transactions = query.order_by(Transaction.delivery_date).all()
        
        if not transactions:
            return None
        
        # 9. 计算总金额
        total_amount = sum(t.total_price_with_tax for t in transactions)
        
        # 10. 构建显示用的公司名（多个公司时显示"多家公司"）
        unique_companies = set(t.company_name for t in transactions)
        display_company = (
            normalized_company_names[0]
            if len(normalized_company_names) == 1
            else f"{len(normalized_company_names)}家公司"
            if normalized_company_names
            else (
            list(unique_companies)[0] if len(unique_companies) == 1 else f"{len(unique_companies)}家公司"
            )
        )
        
        # 11. 构建筛选条件JSON
        filter_conditions = {}
        if normalized_company_names:
            filter_conditions['company_names'] = normalized_company_names
        if contract_no:
            filter_conditions['contract_no'] = contract_no
        if product_codes:
            filter_conditions['product_codes'] = product_codes
        if products:
            filter_conditions['product_names'] = products
        if product_types:
            filter_conditions['product_types'] = product_types
        filter_conditions['date_filter_mode'] = date_filter_mode
        if isinstance(department, str) and department:
            filter_conditions['department'] = department
        
        # 12. 生成对账单记录 [v1.4] 添加发起人信息
        statement = Statement(
            statement_no=StatementService.generate_statement_no(),
            company_name=display_company,
            filter_start_date=start_date,
            filter_end_date=end_date,
            filter_products=json.dumps(filter_conditions) if filter_conditions else None,
            statement_total=total_amount,
            record_count=len(transactions),
            created_by_id=current_user.id if current_user else None,
            department=(
                department
                if isinstance(department, str) and department
                else (
                    current_user.department.name
                    if current_user and current_user.department
                    else None
                )
            )
        )
        
        db.session.add(statement)
        db.session.flush()  # 获取statement.id
        
        # 13. 创建明细关联（重新编号）
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
