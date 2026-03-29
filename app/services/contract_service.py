"""
合同服务类 - v1.2 核心
"""
from typing import Optional, List, Dict
from datetime import datetime, date, timezone, timedelta
from app import db
from app.models import Contract, ContractProduct, Transaction, Product, PaymentRecord


class ContractService:
    """合同服务类"""
    
    @staticmethod
    def create_contract(contract_data: dict, products_data: list) -> Contract:
        """
        创建合同及发货产品计划
        
        Args:
            contract_data: 合同基础信息
                - contract_no: 合同编号
                - company_name: 公司名称
                - total_value: 合同总价（可选，自动计算）
                - remark: 初始备注
            products_data: 产品计划列表
                - product_code, product_name, product_model, product_type
                - quantity, unit, price
        
        Returns:
            创建的合同对象
            
        Raises:
            ValueError: 合同编号已存在
        """
        # 检查合同编号是否已存在
        existing = Contract.query.filter_by(contract_no=contract_data['contract_no']).first()
        if existing:
            raise ValueError(f"合同编号 '{contract_data['contract_no']}' 已存在")
        
        # 检查产品列表不能为空
        if not products_data:
            raise ValueError("请至少添加一种发货产品")
        
        try:
            # 计算合同总价
            total_value = sum(p.get('total', p.get('quantity', 0) * p.get('price', 0)) 
                             for p in products_data)
            
            # 创建合同 [问题4] 添加归属人, [v1.4] 添加创建人
            contract = Contract(
                contract_no=contract_data['contract_no'],
                company_name=contract_data['company_name'],
                owner=contract_data.get('owner'),
                department=contract_data.get('department'),
                manager=contract_data.get('manager'),
                created_by_id=contract_data.get('created_by_id'),
                status='pending',
                total_value=contract_data.get('total_value', total_value),
                remark=None
            )
            db.session.add(contract)
            db.session.flush()  # 获取 contract.id
            
            # 添加初始备注
            tz = timezone(timedelta(hours=8))
            now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
            contract.remark = f"[{now}] 创建合同，计划发货 {len(products_data)} 种产品"
            
            # 创建产品计划 [v1.3] 自动保存新产品到产品库
            from app.services.product_service import ProductService
            for product_data in products_data:
                # [v1.3] 获取或创建产品 - 自动保存新产品到产品库
                product, is_new = ProductService.get_or_create_product(
                    product_code=product_data['product_code'],
                    product_name=product_data.get('product_name'),
                    product_model=product_data.get('product_model'),
                    product_type=product_data.get('product_type'),
                    default_price=float(product_data.get('price', 0)) if product_data.get('price') else None
                )
                
                quantity = float(product_data.get('quantity', 0))
                price = float(product_data.get('price', 0))
                total = quantity * price
                
                cp = ContractProduct(
                    contract_id=contract.id,
                    product_id=product.id if product else None,
                    product_code=product_data['product_code'],
                    product_name=product_data.get('product_name'),
                    product_model=product_data.get('product_model'),
                    product_type=product_data.get('product_type'),
                    quantity=quantity,
                    unit=product_data.get('unit', '个'),
                    price=price,
                    total=total,
                    remark=product_data.get('remark')
                )
                db.session.add(cp)
            
            db.session.commit()
            return contract
            
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def update_contract(contract_id: int, data: dict) -> Contract:
        """更新合同基础信息 [问题4] 支持归属人"""
        contract = Contract.query.get_or_404(contract_id)
        
        contract.contract_no = data.get('contract_no', contract.contract_no)
        contract.company_name = data.get('company_name', contract.company_name)
        
        # [问题4] 更新归属人
        if 'owner' in data:
            old_owner = contract.owner
            contract.owner = data['owner']
            if old_owner != data['owner']:
                if data['owner']:
                    contract.append_remark(f"归属人更新: {old_owner or '无'} -> {data['owner']}")
                else:
                    contract.append_remark(f"归属人更新: {old_owner or '无'} -> 无")
        
        if 'total_value' in data:
            contract.total_value = data['total_value']
        
        # 追加备注
        if data.get('remark_append'):
            contract.append_remark(data['remark_append'])
        
        db.session.commit()
        return contract
    
    @staticmethod
    def add_transaction(contract_id: int, transaction_data: dict, is_new: bool = True) -> Transaction:
        """
        向合同添加发货记录 [v1.3] 移除回款相关逻辑
        
        Args:
            contract_id: 合同ID
            transaction_data:
                - contract_product_id: 关联的产品计划ID
                - quantity, unit, price_with_tax
                - delivery_date, invoice_date
                - handler: 经手人（必填）
                - remark
            - is_new: 是否是新增记录（编辑时使用）
        
        Returns:
            创建的发货记录
            
        Raises:
            ValueError: 发货数量超过合同数量或缺少经手人
        """
        contract = Contract.query.get_or_404(contract_id)
        
        # 获取关联的产品计划
        cp_id = transaction_data.get('contract_product_id')
        cp = ContractProduct.query.get(cp_id) if cp_id else None
        
        # 检查发货数量是否超过合同数量
        quantity = float(transaction_data.get('quantity', 0))
        if cp and is_new:
            # [v1.3修复] 仅对新记录进行数量验证
            delivered = cp.get_delivered_quantity()
            remaining = cp.quantity - delivered
            if quantity > remaining:
                raise ValueError(f"发货数量({quantity})不能超过剩余未发数量({remaining})")
        
        if quantity <= 0:
            raise ValueError("发货数量必须大于0")
        
        # 检查经手人
        handler = transaction_data.get('handler', '').strip()
        if not handler:
            raise ValueError("经手人不能为空")
        
        # 处理日期转换（字符串 -> date对象）
        def parse_date(date_val):
            if isinstance(date_val, str) and date_val:
                try:
                    return datetime.strptime(date_val, '%Y-%m-%d').date()
                except ValueError:
                    raise ValueError(f"日期格式错误: '{date_val}'，请使用 YYYY-MM-DD 格式")
            return date_val if isinstance(date_val, date) else None
        
        delivery_date = parse_date(transaction_data.get('delivery_date'))
        invoice_date = parse_date(transaction_data.get('invoice_date'))
        
        if not delivery_date:
            raise ValueError("发货日期不能为空")
        
        # 获取产品编码（确保不为空）
        product_code = cp.product_code if cp else transaction_data.get('product_code', '').strip()
        if not product_code:
            raise ValueError("产品编码不能为空")
        
        # 创建发货记录
        transaction = Transaction(
            contract_id=contract_id,
            contract_product_id=cp_id,
            company_name=contract.company_name,
            product_id=cp.product_id if cp else None,
            product_code=product_code,
            product_name=cp.product_name if cp else transaction_data.get('product_name'),
            product_model=cp.product_model if cp else transaction_data.get('product_model'),
            product_type=cp.product_type if cp else transaction_data.get('product_type'),
            quantity=float(transaction_data.get('quantity', 0)),
            unit=transaction_data.get('unit', cp.unit if cp else '个') or '个',
            price_with_tax=float(transaction_data.get('price_with_tax', 0) or 0),
            handler=handler,
            delivery_date=delivery_date,
            invoice_date=invoice_date,
            remark=transaction_data.get('remark')
        )
        
        db.session.add(transaction)
        
        # 追加备注
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
        product_code = cp.product_code if cp else transaction_data.get('product_code', '未知')
        contract.append_remark(f"添加发货记录: {product_code} x{quantity}")
        
        db.session.commit()
        
        # 检查合同是否完成
        ContractService.check_completion(contract_id)
        
        return transaction
    
    @staticmethod
    def add_payment_record(contract_id: int, payment_data: dict) -> 'PaymentRecord':
        """
        向合同添加回款记录 [v1.3]
        
        Args:
            contract_id: 合同ID
            payment_data:
                - payment_amount: 回款金额（必填）
                - payment_date: 回款日期（必填）
                - handler: 经手人
                - remark: 备注
        
        Returns:
            创建的回款记录
        """
        from app.models import PaymentRecord
        
        contract = Contract.query.get_or_404(contract_id)
        
        # 验证回款金额
        payment_amount = float(payment_data.get('payment_amount', 0))
        if payment_amount <= 0:
            raise ValueError("回款金额必须大于0")
        
        # 处理日期
        def parse_date(date_val):
            if isinstance(date_val, str) and date_val:
                try:
                    return datetime.strptime(date_val, '%Y-%m-%d').date()
                except ValueError:
                    raise ValueError(f"日期格式错误: '{date_val}'，请使用 YYYY-MM-DD 格式")
            return date_val if isinstance(date_val, date) else None
        
        payment_date = parse_date(payment_data.get('payment_date'))
        if not payment_date:
            raise ValueError("回款日期不能为空")
        
        # 处理关联的产品计划 [v1.3] 支持contract_product_id 或 product_code
        contract_product_id = None
        cp_id_or_code = payment_data.get('contract_product_id')
        if cp_id_or_code:
            from app.models import ContractProduct
            # 先尝试作为整数ID查找
            try:
                cp_id = int(cp_id_or_code)
                cp = ContractProduct.query.get(cp_id)
                if cp and cp.contract_id == contract_id:
                    contract_product_id = cp.id
            except:
                # 如果转换失败，则作为 product_code 查找
                cp = ContractProduct.query.filter_by(
                    contract_id=contract_id,
                    product_code=cp_id_or_code
                ).first()
                if cp:
                    contract_product_id = cp.id
        
        # 创建回款记录
        payment = PaymentRecord(
            contract_id=contract_id,
            contract_product_id=contract_product_id,
            company_name=contract.company_name,
            payment_amount=payment_amount,
            payment_date=payment_date,
            handler=payment_data.get('handler', '').strip() or None,
            remark=payment_data.get('remark')
        )
        
        db.session.add(payment)
        
        # 追加备注
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
        contract.append_remark(f"添加回款记录: {payment_amount:.2f}元")
        
        db.session.commit()
        
        # 检查合同是否完成
        ContractService.check_completion(contract_id)
        
        return payment
    
    @staticmethod
    def get_statistics(contract_id: int) -> Dict:
        """
        获取合同统计信息
        
        Returns:
            {
                'products': [
                    {
                        'product_id': 1,
                        'product_code': 'P0001',
                        'product_name': '产品A',
                        'planned_qty': 100,
                        'delivered_qty': 60,
                        'remaining_qty': 40,
                        'planned_value': 10000,
                        'delivered_value': 6000,
                        'remaining_value': 4000
                    }
                ],
                'total_planned_qty': 100,
                'total_delivered_qty': 60,
                'total_remaining_qty': 40,
                'total_planned_value': 10000,
                'total_delivered_value': 6000,
                'total_remaining_value': 4000,
                'is_completed': False
            }
        """
        contract = Contract.query.get_or_404(contract_id)
        
        products_stats = []
        total_planned_qty = 0
        total_delivered_qty = 0
        total_remaining_qty = 0
        total_planned_value = 0
        total_delivered_value = 0
        total_remaining_value = 0
        
        for cp in contract.contract_products:
            planned_qty = cp.quantity
            delivered_qty = cp.get_delivered_quantity()
            remaining_qty = cp.get_remaining_quantity()
            
            planned_value = cp.total
            delivered_value = cp.get_delivered_value()
            remaining_value = cp.get_remaining_value()
            
            products_stats.append({
                'product_id': cp.id,
                'product_code': cp.product_code,
                'product_name': cp.product_name,
                'planned_qty': planned_qty,
                'delivered_qty': delivered_qty,
                'remaining_qty': remaining_qty,
                'planned_value': planned_value,
                'delivered_value': delivered_value,
                'remaining_value': remaining_value
            })
            
            total_planned_qty += planned_qty
            total_delivered_qty += delivered_qty
            total_remaining_qty += remaining_qty
            total_planned_value += planned_value
            total_delivered_value += delivered_value
            total_remaining_value += remaining_value
        
        is_completed = total_remaining_qty == 0 and total_planned_qty > 0
        
        # [v1.3] 从 PaymentRecord 表计算总回款金额
        total_paid_value = sum(
            (p.payment_amount or 0) for p in contract.payment_records
        )
        total_unpaid_value = total_planned_value - total_paid_value
        
        return {
            'products': products_stats,
            'total_planned_qty': total_planned_qty,
            'total_delivered_qty': total_delivered_qty,
            'total_remaining_qty': total_remaining_qty,
            'total_planned_value': total_planned_value,
            'total_delivered_value': total_delivered_value,
            'total_remaining_value': total_remaining_value,
            'total_paid_value': total_paid_value,  # [LOGIC-7] 已回款金额
            'total_unpaid_value': max(0, total_unpaid_value),  # [LOGIC-7] 未回款金额
            'is_completed': is_completed,
            'contract_status': contract.status,
            'delivery_status': contract.delivery_status,  # [LOGIC-7]
            'payment_status': contract.payment_status  # [LOGIC-7]
        }
    
    @staticmethod
    def check_completion(contract_id: int) -> dict:
        """[LOGIC-7] 检查合同完成状态，分别计算发货和回款状态"""
        stats = ContractService.get_statistics(contract_id)
        contract = Contract.query.get(contract_id)
        
        if not contract:
            return {'delivery_completed': False, 'payment_completed': False}
        
        # 计算发货状态
        total_planned_qty = stats['total_planned_qty']
        total_delivered_qty = stats['total_delivered_qty']
        
        if total_planned_qty == 0:
            delivery_status = 'pending'
        elif total_delivered_qty >= total_planned_qty:
            delivery_status = 'completed'
        elif total_delivered_qty > 0:
            delivery_status = 'partial'
        else:
            delivery_status = 'pending'
        
        # 计算回款状态
        total_planned_value = stats['total_planned_value']
        total_paid_value = stats.get('total_paid_value', 0)
        
        if total_planned_value == 0:
            payment_status = 'pending'
        elif total_paid_value >= total_planned_value:
            payment_status = 'completed'
        elif total_paid_value > 0:
            payment_status = 'partial'
        else:
            payment_status = 'pending'
        
        # 更新状态字段
        old_delivery_status = contract.delivery_status
        old_payment_status = contract.payment_status
        
        contract.delivery_status = delivery_status
        contract.payment_status = payment_status
        
        # 如果发货和回款都完成，则合同总状态为完成
        if delivery_status == 'completed' and payment_status == 'completed':
            if contract.status != 'completed':
                contract.status = 'completed'
                contract.append_remark("合同完成：发货和回款全部完成")
        else:
            if contract.status == 'completed':
                contract.status = 'pending'
                contract.append_remark("合同状态更新：发货或回款未完成")
        
        # 记录状态变化
        if old_delivery_status != delivery_status:
            status_text = {'completed': '完成', 'partial': '部分', 'pending': '未'}[delivery_status]
            contract.append_remark(f"发货状态更新：{status_text}")
        
        if old_payment_status != payment_status:
            status_text = {'completed': '完成', 'partial': '部分', 'pending': '未'}[payment_status]
            contract.append_remark(f"回款状态更新：{status_text}")
        
        db.session.commit()
        
        return {
            'delivery_status': delivery_status,
            'payment_status': payment_status,
            'delivery_completed': delivery_status == 'completed',
            'payment_completed': payment_status == 'completed'
        }
    
    @staticmethod
    def get_owner_list() -> list:
        """[问题4] 获取所有归属人列表"""
        owners = db.session.query(Contract.owner).filter(
            Contract.owner.isnot(None),
            Contract.owner != ''
        ).distinct().order_by(Contract.owner).all()
        return [o[0] for o in owners]
    
    @staticmethod
    def get_department_list() -> list:
        """[v1.3] 获取所有部门列表"""
        from app.models import Department
        departments = Department.query.order_by(Department.name).all()
        return [d.name for d in departments]
    
    @staticmethod
    def get_department_users(department_name: str = None) -> list:
        """[v1.5] 获取部门用户列表，用于PM选择负责人"""
        from app.models import User, Department
        query = db.session.query(User.real_name, User.username, Department.name.label('dept_name')).\
            join(Department, User.department_id == Department.id).\
            filter(User.is_active == True)
        if department_name:
            query = query.filter(Department.name == department_name)
        users = query.order_by(Department.name, User.real_name, User.username).all()
        # 返回格式: "部门名 - 姓名" 或 "部门名 - 用户名"（如果没有real_name）
        result = []
        for u in users:
            display_name = u.real_name or u.username
            result.append(f"{u.dept_name} - {display_name}")
        return result
    
    @staticmethod
    def get_or_create_department(department_name: str) -> 'Department':
        """[v1.3] 获取或创建部门"""
        from app.models import Department
        dept = Department.query.filter_by(name=department_name).first()
        if not dept:
            dept = Department(name=department_name)
            db.session.add(dept)
            db.session.flush()
        return dept
    
    @staticmethod
    def validate_manager_for_department(department_name: str, manager_name: str) -> bool:
        """[v1.5] 验证负责人是否属于该部门（检查是否是部门成员）
        
        Args:
            department_name: 部门名称
            manager_name: 负责人姓名（real_name 或 username）
        
        Returns:
            如果负责人是该部门成员则返回True，否则返回False
        """
        from app.models import User, Department
        
        dept = Department.query.filter_by(name=department_name).first()
        if not dept:
            return False
        
        # 检查是否是部门成员（通过real_name或username匹配）
        user = User.query.filter(
            User.department_id == dept.id,
            User.is_active == True
        ).filter(
            (User.real_name == manager_name) | (User.username == manager_name)
        ).first()
        
        return user is not None
    
    @staticmethod
    def get_contract_list(
        page: int = 1,
        per_page: int = 20,
        contract_no: str = None,
        company_name: str = None,
        status: str = None,
        owner: str = None,
        dept_or_manager: str = None,
        department: str = None,
        created_by: int = None
    ):
        """[v1.3] 获取合同列表 - 支持按部门或负责人筛选, [v1.4] 添加权限过滤"""
        query = Contract.query
        
        if contract_no:
            query = query.filter(Contract.contract_no.contains(contract_no))
        
        if company_name:
            query = query.filter(Contract.company_name.contains(company_name))
        
        if status:
            query = query.filter(Contract.status == status)
        
        # [问题4] 按归属人筛选（兼容旧版）
        if owner:
            query = query.filter(Contract.owner.contains(owner))
        
        # [v1.3] 按部门或负责人筛选
        if dept_or_manager:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    Contract.department.contains(dept_or_manager),
                    Contract.manager.contains(dept_or_manager)
                )
            )
        
        # [v1.4] 按部门筛选（权限过滤）
        if department:
            query = query.filter(Contract.department == department)
        
        # [v1.4] 按创建人筛选（权限过滤）
        if created_by:
            query = query.filter(Contract.created_by_id == created_by)
        
        return query.order_by(Contract.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
    
    @staticmethod
    def delete_contract(contract_id: int) -> bool:
        """删除合同（级联删除产品和交易记录）"""
        contract = Contract.query.get_or_404(contract_id)
        db.session.delete(contract)
        db.session.commit()
        return True
    
    @staticmethod
    def add_contract_product(contract_id: int, data: dict) -> ContractProduct:
        """向合同添加产品计划 - [v1.3] 自动创建新产品到产品库"""
        from app.models import Product
        from app.services.product_service import ProductService
        
        contract = Contract.query.get_or_404(contract_id)
        
        # [v1.3] 获取或创建产品 - 自动保存新产品到产品库
        product, is_new = ProductService.get_or_create_product(
            product_code=data['product_code'],
            product_name=data.get('product_name'),
            product_model=data.get('product_model'),
            product_type=data.get('product_type'),
            default_price=float(data.get('price', 0)) if data.get('price') else None
        )
        
        quantity = float(data.get('quantity', 0))
        price = float(data.get('price', 0))
        total = quantity * price
        
        cp = ContractProduct(
            contract_id=contract_id,
            product_id=product.id if product else None,
            product_code=data['product_code'],
            product_name=data.get('product_name'),
            product_model=data.get('product_model'),
            product_type=data.get('product_type'),
            quantity=quantity,
            unit=data.get('unit', '个'),
            price=price,
            total=total,
            remark=data.get('remark')
        )
        
        db.session.add(cp)
        
        # 更新合同总价
        contract.total_value = sum(p.total for p in contract.contract_products) + total
        action = "新建产品并添加" if is_new else "添加"
        contract.append_remark(f"{action}产品计划: {data['product_code']} x{quantity}")
        
        db.session.commit()
        return cp
    
    @staticmethod
    def update_contract_product(cp_id: int, data: dict) -> ContractProduct:
        """[修复] 更新产品计划 - 移动到ContractService类中"""
        cp = ContractProduct.query.get_or_404(cp_id)
        
        cp.product_code = data.get('product_code', cp.product_code)
        cp.product_name = data.get('product_name', cp.product_name)
        cp.product_model = data.get('product_model', cp.product_model)
        cp.product_type = data.get('product_type', cp.product_type)
        cp.quantity = float(data.get('quantity', cp.quantity))
        cp.unit = data.get('unit', cp.unit)
        cp.price = float(data.get('price', cp.price))
        cp.total = cp.quantity * cp.price
        if 'remark' in data:
            cp.remark = data.get('remark')
        
        db.session.commit()
        
        # 更新合同总价
        contract = Contract.query.get(cp.contract_id)
        if contract:
            total = sum(p.total for p in contract.contract_products)
            contract.total_value = total
            contract.append_remark(f"修改产品计划: {cp.product_code}")
            db.session.commit()
        
        return cp
    
    @staticmethod
    def delete_contract_product(cp_id: int) -> bool:
        """[修复] 删除产品计划（检查是否有交易记录）- 移动到ContractService类中"""
        cp = ContractProduct.query.get_or_404(cp_id)
        
        # 检查是否有交易记录
        if cp.transactions:
            return False  # 有关联交易，不能删除
        
        contract_id = cp.contract_id
        db.session.delete(cp)
        
        # 更新合同备注
        contract = Contract.query.get(contract_id)
        if contract:
            contract.append_remark(f"删除产品计划: {cp.product_code}")
        
        db.session.commit()
        return True
    
    @staticmethod
    def get_contract_by_no(contract_no: str) -> Optional[Contract]:
        """根据编号获取合同"""
        return Contract.query.filter_by(contract_no=contract_no).first()
    
    @staticmethod
    def upload_contract_images(contract_id: int, images: list):
        """上传合同图片 [v1.3]
        
        Args:
            contract_id: 合同ID
            images: 图片文件列表
        """
        from app.models import ContractImage
        from flask import current_app
        import os
        from werkzeug.utils import secure_filename
        
        contract = Contract.query.get_or_404(contract_id)
        
        # 确保上传目录存在 - 使用相对于项目根目录的路径 [v1.3修复]
        upload_folder = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'contracts', str(contract_id))
        os.makedirs(upload_folder, exist_ok=True)
        
        upload_count = 0
        for image in images:
            if not image or not image.filename:
                continue
                
            # 检查文件类型
            if not image.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                continue
            
            # 安全文件名
            filename = secure_filename(image.filename)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{timestamp}_{filename}"
            
            # 保存文件
            filepath = os.path.join(upload_folder, filename)
            image.save(filepath)
            
            # 创建数据库记录 - 使用相对于static的路径
            relative_path = os.path.join('uploads', 'contracts', str(contract_id), filename)
            # 统一使用正斜杠
            relative_path = relative_path.replace('\\', '/')
            
            contract_image = ContractImage(
                contract_id=contract_id,
                filename=filename,
                filepath=relative_path,
                file_type=image.content_type
            )
            db.session.add(contract_image)
            upload_count += 1
        
        if upload_count > 0:
            db.session.commit()
            contract.append_remark(f"上传了 {upload_count} 张图片")
            db.session.commit()
    
    @staticmethod
    def upload_contract_documents(contract_id: int, documents: list):
        """[v1.4] 上传合同文档（PDF、Word等）
        
        Args:
            contract_id: 合同ID
            documents: 文档文件列表
        """
        from app.models import ContractFile
        from flask import current_app
        import os
        from werkzeug.utils import secure_filename
        
        contract = Contract.query.get_or_404(contract_id)
        
        # 确保上传目录存在
        upload_folder = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'contract_documents', str(contract_id))
        os.makedirs(upload_folder, exist_ok=True)
        
        upload_count = 0
        for doc in documents:
            if not doc or not doc.filename:
                continue
            
            # 获取文件扩展名
            filename_lower = doc.filename.lower()
            allowed_exts = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
            if not any(filename_lower.endswith(ext) for ext in allowed_exts):
                continue
            
            # 安全文件名
            filename = secure_filename(doc.filename)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            filename = f"{timestamp}_{filename}"
            
            # 保存文件
            filepath = os.path.join(upload_folder, filename)
            doc.save(filepath)
            
            # 获取文件大小
            file_size = os.path.getsize(filepath)
            
            # 获取文件类型
            file_type = filename_lower.split('.')[-1] if '.' in filename_lower else ''
            
            # 创建数据库记录
            contract_file = ContractFile(
                contract_id=contract_id,
                filename=doc.filename,
                filepath=filename,
                file_type=file_type,
                file_size=file_size
            )
            db.session.add(contract_file)
            upload_count += 1
        
        if upload_count > 0:
            db.session.commit()
            contract.append_remark(f"上传了 {upload_count} 个合同文件")
            db.session.commit()


# [修复] ContractProductService 类保留但方法已移动到 ContractService
class ContractProductService:
    """合同产品计划服务类"""
    
    @staticmethod
    def update_contract_product(cp_id: int, data: dict) -> ContractProduct:
        """更新产品计划"""
        cp = ContractProduct.query.get_or_404(cp_id)
        
        cp.product_code = data.get('product_code', cp.product_code)
        cp.product_name = data.get('product_name', cp.product_name)
        cp.product_model = data.get('product_model', cp.product_model)
        cp.product_type = data.get('product_type', cp.product_type)
        cp.quantity = float(data.get('quantity', cp.quantity))
        cp.unit = data.get('unit', cp.unit)
        cp.price = float(data.get('price', cp.price))
        cp.total = cp.quantity * cp.price
        if 'remark' in data:
            cp.remark = data.get('remark')
        
        db.session.commit()
        
        # 更新合同总价
        contract = Contract.query.get(cp.contract_id)
        if contract:
            total = sum(p.total for p in contract.contract_products)
            contract.total_value = total
            contract.append_remark(f"修改产品计划: {cp.product_code}")
            db.session.commit()
        
        return cp
    
    @staticmethod
    def delete_contract_product(cp_id: int) -> bool:
        """删除产品计划（检查是否有交易记录）"""
        cp = ContractProduct.query.get_or_404(cp_id)
        
        # 检查是否有交易记录
        if cp.transactions:
            return False  # 有关联交易，不能删除
        
        contract_id = cp.contract_id
        db.session.delete(cp)
        
        # 更新合同备注
        contract = Contract.query.get(contract_id)
        if contract:
            contract.append_remark(f"删除产品计划: {cp.product_code}")
        
        db.session.commit()
        return True
