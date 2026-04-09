"""
合同路由 - v1.3 核心（发货/回款分离）
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, g, current_app
import os
from datetime import datetime
from app.forms import ContractForm, ContractProductForm, ContractTransactionForm
from app.services.contract_service import ContractService, ContractProductService
from app.services.product_service import ProductService
from app.services.statement_service import StatementService
from app.utils.excel_export import export_delivery_note_to_excel
from app.models import Contract, ContractProduct, Transaction, PaymentRecord
from app import db
from app.utils.decorators import login_required, permission_required

contract_bp = Blueprint('contract', __name__, url_prefix='/contract')


def _get_multi_query_values(param_name: str) -> list:
    """读取 GET 多选参数，兼容重复参数与逗号拼接两种格式。"""
    values = [v.strip() for v in request.args.getlist(param_name) if v and v.strip()]
    if values:
        return values
    csv_value = (request.args.get(param_name, '') or '').strip()
    if not csv_value:
        return []
    return [v.strip() for v in csv_value.split(',') if v.strip()]


def _to_float2(value, default: float = 0.0) -> float:
    """将输入转换为两位小数浮点数。"""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


@contract_bp.route('/')
@contract_bp.route('/list')
@login_required
@permission_required('contract_view')
def list_contracts():
    """[v1.3] 合同列表 - 支持部门或负责人搜索，[v1.4] 添加权限过滤"""
    from flask import g
    
    page = request.args.get('page', 1, type=int)
    contract_no = request.args.get('contract_no', '')
    company_name = request.args.get('company_name', '')
    status = request.args.get('status', '')
    dept_or_manager = request.args.get('dept_or_manager', '')
    delivery_statuses = _get_multi_query_values('delivery_status')
    payment_statuses = _get_multi_query_values('payment_status')
    invoice_statuses = _get_multi_query_values('invoice_status')
    
    # [v1.4] 根据用户角色过滤合同
    user = g.current_user
    department_filter = None
    created_by_filter = None
    
    if user.is_department_pm():
        # 部门PM只能看到本部门的合同
        department_filter = user.department.name if user.department else None
    elif user.is_sales_manager():
        # 部门销售经理只能看到自己创建的合同
        created_by_filter = user.id
    # 超级管理员、总经理、物流经理可以看到所有合同
    
    pagination = ContractService.get_contract_list(
        page=page,
        per_page=20,
        contract_no=contract_no or None,
        company_name=company_name or None,
        status=status or None,
        delivery_statuses=delivery_statuses or None,
        payment_statuses=payment_statuses or None,
        invoice_statuses=invoice_statuses or None,
        dept_or_manager=dept_or_manager or None,
        department=department_filter,
        created_by=created_by_filter
    )
    
    companies = StatementService.get_company_list()
    
    return render_template('contract/list.html',
                         contracts=pagination.items,
                         pagination=pagination,
                         contract_no=contract_no,
                         company_name=company_name,
                         status=status,
                         delivery_statuses=delivery_statuses,
                         payment_statuses=payment_statuses,
                         invoice_statuses=invoice_statuses,
                         delivery_status_csv=','.join(delivery_statuses),
                         payment_status_csv=','.join(payment_statuses),
                         invoice_status_csv=','.join(invoice_statuses),
                         dept_or_manager=dept_or_manager,
                         companies=companies)


@contract_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('contract_create')
def new_contract():
    """
    新增合同页面
    包含：合同信息、发货产品计划、交易记录
    """
    form = ContractForm()
    product_form = ContractProductForm()
    transaction_form = ContractTransactionForm()
    
    # 设置产品选择下拉
    product_form.product_id.choices = ProductService.get_product_choices()
    
    if form.validate_on_submit():
        try:
            # 获取合同基础信息 [问题4] 添加归属人
            contract_data = {
                'contract_no': form.contract_no.data,
                'company_name': form.company_name.data,
                'owner': form.owner.data.strip() if form.owner.data else None
            }
            actual_received_raw = request.form.get('actual_received_value')
            if actual_received_raw not in (None, ''):
                contract_data['actual_received_value'] = _to_float2(actual_received_raw)
            
            # [问题3] 获取产品计划数据（从动态表单）- 适配下拉/手输双模式
            products_data = []
            product_count = int(request.form.get('product_count', 0))
            
            for i in range(product_count):
                prefix = f'product_{i}_'
                # 优先获取手动输入的编码，如果没有则获取下拉选择的编码
                product_code = request.form.get(f'{prefix}code') or request.form.get(f'{prefix}code_select')
                product_data = {
                    'product_code': product_code,
                    'product_name': request.form.get(f'{prefix}name'),
                    'product_model': request.form.get(f'{prefix}model'),
                    'product_type': request.form.get(f'{prefix}type'),
                    'quantity': _to_float2(request.form.get(f'{prefix}quantity', 0)),
                    'unit': request.form.get(f'{prefix}unit', '个'),
                    'price': _to_float2(request.form.get(f'{prefix}price', 0)),
                    'remark': request.form.get(f'{prefix}remark')
                }
                if product_data['product_code'] and product_data['quantity'] > 0:
                    products_data.append(product_data)
            
            if not products_data:
                flash('请至少添加一种发货产品', 'error')
                return render_template('contract/form.html',
                                     form=form,
                                     product_form=product_form,
                                     transaction_form=transaction_form,
                                     companies=StatementService.get_company_list())
            
            # 处理部门/负责人 [v1.3] [v1.5] 简化逻辑，直接使用表单值
            department = request.form.get('department', '').strip()
            manager = request.form.get('manager', '').strip()
            if department:
                contract_data['department'] = department
            if manager:
                contract_data['manager'] = manager
            if department and manager:
                contract_data['owner'] = f"{department} - {manager}"
            
            # [v1.4] 记录合同创建人
            contract_data['created_by_id'] = g.current_user.id
            
            # 创建合同
            contract = ContractService.create_contract(contract_data, products_data)
            
            # 添加发货记录（如果有）
            transaction_count = int(request.form.get('transaction_count', 0))
            for i in range(transaction_count):
                prefix = f'transaction_{i}_'
                product_code = request.form.get(f'{prefix}contract_product_id')
                if product_code:
                    contract_product = ContractProduct.query.filter_by(
                        contract_id=contract.id,
                        product_code=product_code
                    ).first()
                    
                    if contract_product:
                        transaction_data = {
                            'contract_product_id': contract_product.id,
                            'quantity': _to_float2(request.form.get(f'{prefix}quantity', 0)),
                            'unit': request.form.get(f'{prefix}unit'),
                            'price_with_tax': _to_float2(request.form.get(f'{prefix}price', 0)),
                            'handler': request.form.get(f'{prefix}handler', '').strip(),
                            'delivery_date': request.form.get(f'{prefix}delivery_date'),
                            'invoice_date': request.form.get(f'{prefix}invoice_date') or None,
                            'remark': request.form.get(f'{prefix}remark')
                        }
                        if transaction_data['quantity'] > 0:
                            ContractService.add_transaction(contract.id, transaction_data)
            
            # 添加回款记录（如果有）[v1.3]
            payment_count = int(request.form.get('payment_count', 0))
            for i in range(payment_count):
                prefix = f'payment_{i}_'
                payment_amount = request.form.get(f'{prefix}amount')
                if payment_amount and _to_float2(payment_amount) > 0:
                    payment_data = {
                        'payment_amount': _to_float2(payment_amount),
                        'payment_date': request.form.get(f'{prefix}date'),
                        'invoice_date': request.form.get(f'{prefix}invoice_date') or None,
                        'handler': request.form.get(f'{prefix}handler', '').strip() or None,
                        'remark': request.form.get(f'{prefix}remark'),
                        'contract_product_id': request.form.get(f'{prefix}contract_product_id') or None
                    }
                    if payment_data['payment_date']:
                        ContractService.add_payment_record(contract.id, payment_data)
            
            # 处理图片上传 [v1.3]
            images = request.files.getlist('images')
            if images:
                ContractService.upload_contract_images(contract.id, images)
            
            # [v1.4] 处理合同文件上传
            contract_documents = request.files.getlist('contract_documents')
            if contract_documents:
                ContractService.upload_contract_documents(contract.id, contract_documents)
            
            flash(f'合同 {contract.contract_no} 创建成功！', 'success')
            return redirect(url_for('contract.view_contract', id=contract.id))
        
        except ValueError as e:
            # 合同编号重复等验证错误
            db.session.rollback()
            flash(f'创建失败：{str(e)}', 'error')
        except Exception as e:
            # 其他错误，确保回滚
            db.session.rollback()
            flash(f'创建失败：{str(e)}', 'error')
    
    companies = StatementService.get_company_list()
    products = ProductService.get_all_products()
    # [v1.4] 从部门管理模块获取部门列表
    from app.models import Department
    departments = Department.query.order_by(Department.name).all()
    owners = ContractService.get_owner_list()
    
    # [v1.4] 获取当前用户部门（用于自动填充）
    current_user_dept = None
    if g.current_user.department:
        current_user_dept = g.current_user.department.name
    
    # [v1.5] 获取部门用户列表（用于PM选择负责人）
    department_users = []
    if g.current_user.department:
        from app.models import User
        dept_users = User.query.filter_by(
            department_id=g.current_user.department.id,
            is_active=True
        ).all()
        department_users = [u.real_name or u.username for u in dept_users]
    
    # 兼容模板中的 managers 变量
    managers = ContractService.get_department_users()
    if g.current_user.is_department_pm() and department_users:
        managers = department_users
    
    return render_template('contract/form.html',
                         form=form,
                         product_form=product_form,
                         transaction_form=transaction_form,
                         companies=companies,
                         products=products,
                         departments=departments,
                         department_users=department_users,
                         managers=managers,
                         owners=owners,
                         is_new=True,
                         current_user_dept=current_user_dept,
                         current_user_manager=g.current_user.real_name or g.current_user.username)


@contract_bp.route('/<int:id>')
@login_required
@permission_required('contract_view')
def view_contract(id):
    """查看合同详情"""
    from flask import g
    contract = Contract.query.get_or_404(id)
    
    # [v1.4] 权限检查
    if not g.current_user.can_view_contract(contract):
        flash('您没有权限查看此合同', 'error')
        return redirect(url_for('contract.list_contracts'))
    
    # [v1.5.2] 检查并更新合同完成状态
    ContractService.check_completion(contract.id)
    db.session.commit()
    
    stats = ContractService.get_statistics(id)
    
    return render_template('contract/detail.html',
                         contract=contract,
                         stats=stats)


@contract_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('contract_edit')
def edit_contract(id):
    """编辑合同 - 可继续添加交易记录"""
    from flask import g
    contract = Contract.query.get_or_404(id)
    
    # [v1.4] 权限检查
    if not g.current_user.can_edit_contract(contract):
        flash('您没有权限编辑此合同', 'error')
        return redirect(url_for('contract.view_contract', id=id))
    form = ContractForm(obj=contract)
    transaction_form = ContractTransactionForm()
    
    # 设置交易表单的产品选择（从合同产品中）
    transaction_form.contract_product_id.choices = [
        (cp.id, f"{cp.product_code} - {cp.product_name or '未命名'} (计划:{cp.quantity})")
        for cp in contract.contract_products
    ]
    
    if form.validate_on_submit():
        try:
            # [v1.5.2] 导入依赖
            from app.models import PaymentRecord
            from datetime import datetime, timezone, timedelta
            
            # 更新合同基础信息 [问题4] 添加归属人
            contract_data = {
                'contract_no': form.contract_no.data,
                'company_name': form.company_name.data,
                'owner': form.owner.data.strip() if form.owner.data else None
            }
            actual_received_raw = request.form.get('actual_received_value')
            if actual_received_raw not in (None, ''):
                contract_data['actual_received_value'] = _to_float2(actual_received_raw)
            ContractService.update_contract(id, contract_data)
            
            # [问题4] 处理产品计划的修改和新增
            product_count = int(request.form.get('product_count', 0))
            existing_product_ids = {cp.id for cp in contract.contract_products}
            submitted_product_ids = set()
            
            for i in range(product_count):
                prefix = f'product_{i}_'
                # 优先获取手动输入的编码，如果没有则获取下拉选择的编码
                product_code = request.form.get(f'{prefix}code') or request.form.get(f'{prefix}code_select')
                if not product_code:
                    continue

                product_id_raw = (request.form.get(f'{prefix}id') or '').strip()
                product_id = int(product_id_raw) if product_id_raw.isdigit() else None

                product_data = {
                    'product_code': product_code,
                    'product_name': request.form.get(f'{prefix}name'),
                    'product_model': request.form.get(f'{prefix}model'),
                    'product_type': request.form.get(f'{prefix}type'),
                    'quantity': _to_float2(request.form.get(f'{prefix}quantity', 0)),
                    'unit': request.form.get(f'{prefix}unit', '个'),
                    'price': _to_float2(request.form.get(f'{prefix}price', 0)),
                    'remark': request.form.get(f'{prefix}remark')
                }

                # 优先按前端提交的产品计划ID更新，避免修改产品编码时“保存后看似不生效”
                if product_id and product_id in existing_product_ids:
                    ContractService.update_contract_product(product_id, product_data)
                    submitted_product_ids.add(product_id)
                    continue

                # 兼容旧前端：没有 product_id 时，按产品编码匹配已有记录
                existing_cp = ContractProduct.query.filter_by(contract_id=id, product_code=product_code).first()
                if existing_cp:
                    ContractService.update_contract_product(existing_cp.id, product_data)
                    submitted_product_ids.add(existing_cp.id)
                else:
                    new_cp = ContractService.add_contract_product(id, product_data)
                    submitted_product_ids.add(new_cp.id)
            
            # 删除未被提交的产品计划（已被删除的）
            for cp in contract.contract_products:
                if cp.id not in submitted_product_ids:
                    # 检查是否有交易记录，没有则删除
                    if not cp.transactions:
                        ContractService.delete_contract_product(cp.id)
            
            # 处理发货记录 - 包括更新、新增和删除
            transaction_count = int(request.form.get('transaction_count', 0))
            existing_transaction_ids = {t.id for t in contract.transactions}
            submitted_transaction_ids = set()
            
            for i in range(transaction_count):
                prefix = f'transaction_{i}_'
                trans_id = request.form.get(f'{prefix}id')  # 如果有id则是已有记录
                product_code = request.form.get(f'{prefix}contract_product_id')
                
                if trans_id:
                    submitted_transaction_ids.add(int(trans_id))
                    # [v1.4] 更新已有发货记录
                    if int(trans_id) in existing_transaction_ids:
                        transaction = Transaction.query.get(int(trans_id))
                        if transaction:
                            selected_product_code = (request.form.get(f'{prefix}contract_product_id') or '').strip()
                            selected_contract_product = None
                            if selected_product_code:
                                selected_contract_product = ContractProduct.query.filter_by(
                                    contract_id=id,
                                    product_code=selected_product_code
                                ).first()
                                if selected_contract_product:
                                    # 同步产品计划关联及冗余字段，避免“前端显示已变更但保存后回滚”
                                    transaction.contract_product_id = selected_contract_product.id
                                    transaction.product_id = selected_contract_product.product_id
                                    transaction.product_code = selected_contract_product.product_code
                                    transaction.product_name = selected_contract_product.product_name
                                    transaction.product_model = selected_contract_product.product_model
                                    transaction.product_type = selected_contract_product.product_type
                                else:
                                    current_app.logger.warning(
                                        f"[v1.5.3] Transaction update product not found: "
                                        f"contract_id={id}, product_code={selected_product_code}"
                                    )

                            # 更新可编辑字段
                            quantity = request.form.get(f'{prefix}quantity')
                            if quantity is not None:
                                transaction.quantity = _to_float2(quantity, transaction.quantity)
                            
                            handler = request.form.get(f'{prefix}handler')
                            if handler is not None:
                                transaction.handler = handler.strip()
                            
                            delivery_date = request.form.get(f'{prefix}delivery_date')
                            if delivery_date:
                                transaction.delivery_date = datetime.strptime(delivery_date, '%Y-%m-%d').date()
                            
                            # 更新其他可选字段
                            price = request.form.get(f'{prefix}price')
                            if price not in (None, ''):
                                transaction.price_with_tax = _to_float2(price, transaction.price_with_tax)
                            elif selected_contract_product and selected_contract_product.price is not None:
                                transaction.price_with_tax = _to_float2(
                                    selected_contract_product.price,
                                    transaction.price_with_tax
                                )
                            
                            unit = request.form.get(f'{prefix}unit')
                            if unit:
                                transaction.unit = unit
                            elif selected_contract_product and selected_contract_product.unit:
                                transaction.unit = selected_contract_product.unit
                            
                            remark = request.form.get(f'{prefix}remark')
                            if remark is not None:
                                transaction.remark = remark
                            
                            # [v1.5.2] 恢复 invoice_date 处理
                            invoice_date = request.form.get(f'{prefix}invoice_date')
                            if invoice_date:
                                transaction.invoice_date = datetime.strptime(invoice_date, '%Y-%m-%d').date()
                            else:
                                transaction.invoice_date = None
                        continue
                
                if product_code:
                    contract_product = ContractProduct.query.filter_by(
                        contract_id=id,
                        product_code=product_code
                    ).first()
                    
                    # [v1.5.2] 调试日志
                    current_app.logger.info(f"[v1.5.2] Looking for ContractProduct: contract_id={id}, product_code={product_code}, found={contract_product is not None}")
                    
                    if contract_product:
                        transaction_data = {
                            'contract_product_id': contract_product.id,
                            'quantity': _to_float2(request.form.get(f'{prefix}quantity', 0)),
                            'unit': request.form.get(f'{prefix}unit'),
                            'price_with_tax': _to_float2(request.form.get(f'{prefix}price', 0)),
                            'handler': request.form.get(f'{prefix}handler', '').strip(),
                            'delivery_date': request.form.get(f'{prefix}delivery_date'),
                            'invoice_date': request.form.get(f'{prefix}invoice_date') or None,
                            'remark': request.form.get(f'{prefix}remark')
                        }
                        # [v1.5.2] 添加调试和错误处理
                        current_app.logger.info(f"[v1.5.2] Creating transaction: {transaction_data}")
                        if transaction_data['quantity'] > 0:
                            try:
                                trans = ContractService.add_transaction(id, transaction_data, is_new=True)
                                current_app.logger.info(f"[v1.5.2] Transaction created: id={trans.id}")
                            except Exception as e:
                                current_app.logger.error(f"[v1.5.2] Error adding trans: {e}")
                                raise
                    else:
                        current_app.logger.error(f"[v1.5.2] ContractProduct not found: contract_id={id}, product_code={product_code}")
            
            # 删除未被提交的发货记录（已在页面上删除的）
            # 仅删除“提交前已存在”的记录，避免误删本次新增记录
            for trans in contract.transactions:
                if trans.id in existing_transaction_ids and trans.id not in submitted_transaction_ids:
                    # [v1.3] 先删除关联的对账单明细，避免外键约束错误
                    for item in trans.statement_items:
                        db.session.delete(item)
                    db.session.delete(trans)
            
            # 处理回款记录 - 包括更新、新增和删除 [v1.3]
            payment_count = int(request.form.get('payment_count', 0))
            existing_payment_ids = {p.id for p in contract.payment_records}
            submitted_payment_ids = set()
            
            for i in range(payment_count):
                prefix = f'payment_{i}_'
                payment_id = request.form.get(f'{prefix}id')
                
                if payment_id:
                    submitted_payment_ids.add(int(payment_id))
                    # [v1.4] 更新已有回款记录
                    if int(payment_id) in existing_payment_ids:
                        payment = PaymentRecord.query.get(int(payment_id))
                        if payment:
                            payment_amount = request.form.get(f'{prefix}amount')
                            if payment_amount is not None:
                                payment.payment_amount = _to_float2(payment_amount)
                            
                            payment_date = request.form.get(f'{prefix}date')
                            if payment_date:
                                payment.payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()

                            invoice_date = request.form.get(f'{prefix}invoice_date')
                            if invoice_date:
                                payment.invoice_date = datetime.strptime(invoice_date, '%Y-%m-%d').date()
                            else:
                                payment.invoice_date = None
                            
                            handler = request.form.get(f'{prefix}handler')
                            if handler is not None:
                                payment.handler = handler.strip() or None
                            
                            remark = request.form.get(f'{prefix}remark')
                            if remark is not None:
                                payment.remark = remark
                            
                            # [v1.5.2] 修复：前端传的是 product_code，需要查询获取 contract_product_id
                            product_code = request.form.get(f'{prefix}contract_product_id')
                            if product_code:
                                cp = ContractProduct.query.filter_by(contract_id=id, product_code=product_code).first()
                                payment.contract_product_id = cp.id if cp else None
                        continue
                
                payment_amount = request.form.get(f'{prefix}amount')
                if payment_amount and _to_float2(payment_amount) > 0:
                    # [v1.5.2] 修复：直接创建PaymentRecord对象，避免Service方法中的重复commit
                    payment_date_str = request.form.get(f'{prefix}date')
                    payment_date_obj = datetime.strptime(payment_date_str, '%Y-%m-%d').date() if payment_date_str else None
                    
                    # 前端传的是 product_code，需要查询获取 contract_product_id
                    product_code = request.form.get(f'{prefix}contract_product_id')
                    cp = ContractProduct.query.filter_by(contract_id=id, product_code=product_code).first() if product_code else None
                    
                    new_payment = PaymentRecord(
                        contract_id=id,
                        contract_product_id=cp.id if cp else None,
                        company_name=contract.company_name,
                        payment_amount=_to_float2(payment_amount),
                        payment_date=payment_date_obj,
                        invoice_date=datetime.strptime(request.form.get(f'{prefix}invoice_date'), '%Y-%m-%d').date() if request.form.get(f'{prefix}invoice_date') else None,
                        handler=request.form.get(f'{prefix}handler', '').strip() or None,
                        remark=request.form.get(f'{prefix}remark')
                    )
                    db.session.add(new_payment)
            
            # 删除未被提交的回款记录（已在页面上删除的）
            # 仅删除“提交前已存在”的记录，避免误删本次新增记录
            for payment in contract.payment_records:
                if payment.id in existing_payment_ids and payment.id not in submitted_payment_ids:
                    db.session.delete(payment)
            
            # 处理部门/负责人 [v1.3] [v1.5] 简化逻辑，直接使用表单值
            department = request.form.get('department', '').strip()
            manager = request.form.get('manager', '').strip()
            if department:
                contract.department = department
            if manager:
                contract.manager = manager
            if department and manager:
                contract.owner = f"{department} - {manager}"
            db.session.commit()
            
            # 处理图片上传 [v1.3]
            images = request.files.getlist('images')
            if images:
                ContractService.upload_contract_images(id, images)
            
            # [v1.4] 处理合同文件上传
            contract_documents = request.files.getlist('contract_documents')
            if contract_documents:
                ContractService.upload_contract_documents(id, contract_documents)
            
            # [v1.5.2] 修复：更新合同发货/回款状态
            ContractService.check_completion(contract.id)
            db.session.commit()
            
            flash('合同更新成功！', 'success')
            return redirect(url_for('contract.view_contract', id=id))
        
        except Exception as e:
            db.session.rollback()
            import traceback
            current_app.logger.error(f"[v1.5.2] ERROR in edit_contract: {e}")
            current_app.logger.error(traceback.format_exc())
            flash(f'更新失败：{str(e)}', 'error')
    
    stats = ContractService.get_statistics(id)
    companies = StatementService.get_company_list()
    from app.services.product_service import ProductService
    products = ProductService.get_all_products()
    # [v1.4] 从部门管理模块获取部门列表
    from app.models import Department
    departments = Department.query.order_by(Department.name).all()
    owners = ContractService.get_owner_list()
    
    # [v1.5] 获取部门用户列表（用于PM选择负责人）
    department_users = []
    if g.current_user.department:
        from app.models import User
        dept_users = User.query.filter_by(
            department_id=g.current_user.department.id,
            is_active=True
        ).all()
        department_users = [u.real_name or u.username for u in dept_users]
    
    # 兼容模板中的 managers 变量
    managers = ContractService.get_department_users()
    if g.current_user.is_department_pm() and department_users:
        managers = department_users
    
    return render_template('contract/form.html',
                         form=form,
                         transaction_form=transaction_form,
                         contract=contract,
                         stats=stats,
                         companies=companies,
                         products=products,
                         departments=departments,
                         department_users=department_users,
                         managers=managers,
                         owners=owners,
                         is_new=False)


@contract_bp.route('/<int:id>/logistics-edit', methods=['GET', 'POST'])
@login_required
def logistics_edit_contract(id):
    """[v1.4] 物流经理专用编辑页面 - 仅可编辑发货记录和附件"""
    from flask import g
    contract = Contract.query.get_or_404(id)
    
    # 仅限物流经理访问
    if not g.current_user.is_logistics_manager():
        flash('此页面仅限物流经理访问', 'error')
        return redirect(url_for('contract.view_contract', id=id))
    
    if request.method == 'POST':
        try:
            # 处理发货记录
            transaction_count = int(request.form.get('transaction_count', 0))
            existing_transaction_ids = {t.id for t in contract.transactions}
            submitted_transaction_ids = set()
            
            for i in range(transaction_count):
                prefix = f'transaction_{i}_'
                trans_id = request.form.get(f'{prefix}id')
                product_code = request.form.get(f'{prefix}contract_product_id')
                
                if trans_id:
                    # [v1.4] 更新已有发货记录
                    submitted_transaction_ids.add(int(trans_id))
                    transaction = Transaction.query.get(int(trans_id))
                    if transaction:
                        selected_product_code = (product_code or '').strip()
                        selected_contract_product = None
                        if selected_product_code:
                            selected_contract_product = ContractProduct.query.filter_by(
                                contract_id=contract.id,
                                product_code=selected_product_code
                            ).first()
                            if selected_contract_product:
                                # 同步产品计划关联及冗余字段，避免保存后产品信息未更新
                                transaction.contract_product_id = selected_contract_product.id
                                transaction.product_id = selected_contract_product.product_id
                                transaction.product_code = selected_contract_product.product_code
                                transaction.product_name = selected_contract_product.product_name
                                transaction.product_model = selected_contract_product.product_model
                                transaction.product_type = selected_contract_product.product_type
                            else:
                                current_app.logger.warning(
                                    f"[v1.5.3] Logistics update product not found: "
                                    f"contract_id={contract.id}, product_code={selected_product_code}"
                                )

                        # 更新可编辑字段
                        quantity = _to_float2(request.form.get(f'{prefix}quantity', 0))
                        handler = request.form.get(f'{prefix}handler', '').strip()
                        delivery_date_str = request.form.get(f'{prefix}delivery_date')
                        
                        if quantity > 0:
                            transaction.quantity = quantity
                        if handler:
                            transaction.handler = handler
                        if delivery_date_str:
                            from datetime import datetime
                            transaction.delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
                        
                        # 更新其他可选字段
                        price = request.form.get(f'{prefix}price')
                        if price not in (None, ''):
                            transaction.price_with_tax = _to_float2(price, transaction.price_with_tax)
                        elif selected_contract_product and selected_contract_product.price is not None:
                            transaction.price_with_tax = _to_float2(
                                selected_contract_product.price,
                                transaction.price_with_tax
                            )
                        
                        unit = request.form.get(f'{prefix}unit')
                        if unit:
                            transaction.unit = unit
                        elif selected_contract_product and selected_contract_product.unit:
                            transaction.unit = selected_contract_product.unit
                        
                        remark = request.form.get(f'{prefix}remark')
                        if remark is not None:
                            transaction.remark = remark
                    continue
                
                # 新增发货记录
                if product_code:
                    from app.models import ContractProduct
                    contract_product = ContractProduct.query.filter_by(
                        contract_id=contract.id,
                        product_code=product_code
                    ).first()
                    
                    if contract_product:
                        quantity = _to_float2(request.form.get(f'{prefix}quantity', 0))
                        handler = request.form.get(f'{prefix}handler', '').strip()
                        delivery_date_str = request.form.get(f'{prefix}delivery_date')
                        
                        if quantity > 0 and handler and delivery_date_str:
                            from datetime import datetime
                            
                            delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
                            
                            transaction = Transaction(
                                contract_id=contract.id,
                                contract_product_id=contract_product.id,
                                company_name=contract.company_name,
                                product_id=contract_product.product_id,
                                product_code=contract_product.product_code,
                                product_name=contract_product.product_name,
                                product_model=contract_product.product_model,
                                product_type=contract_product.product_type,
                                quantity=quantity,
                                unit=request.form.get(f'{prefix}unit') or contract_product.unit or '个',
                                price_with_tax=_to_float2(request.form.get(f'{prefix}price', 0)),
                                handler=handler,
                                delivery_date=delivery_date,
                                remark=request.form.get(f'{prefix}remark')
                            )
                            db.session.add(transaction)
            
            # 删除未提交的发货记录
            # 仅删除“提交前已存在”的记录，避免误删本次新增记录
            for trans in contract.transactions:
                if trans.id in existing_transaction_ids and trans.id not in submitted_transaction_ids:
                    for item in trans.statement_items:
                        db.session.delete(item)
                    db.session.delete(trans)
            
            # 处理图片上传
            images = request.files.getlist('images')
            if images:
                ContractService.upload_contract_images(contract.id, images)
            
            # 追加备注
            contract.append_remark(f"物流经理 [{g.current_user.real_name or g.current_user.username}] 更新了发货记录")
            
            db.session.commit()
            
            # [v1.4] 更新合同发货状态
            ContractService.check_completion(contract.id)
            db.session.commit()
            
            flash('发货记录和附件保存成功！', 'success')
            return redirect(url_for('contract.view_contract', id=contract.id))
        
        except Exception as e:
            db.session.rollback()
            flash(f'保存失败：{str(e)}', 'error')
    
    return render_template('contract/logistics_edit.html', contract=contract)


@contract_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('contract_delete')
def delete_contract(id):
    """删除合同"""
    contract = Contract.query.get_or_404(id)
    if not g.current_user.can_edit_contract_basic(contract):
        flash('您没有权限删除此合同', 'error')
        return redirect(url_for('contract.list_contracts'))

    try:
        ContractService.delete_contract(id)
        flash('合同删除成功！', 'success')
    except Exception as e:
        flash(f'删除失败：{str(e)}', 'error')
    
    return redirect(url_for('contract.list_contracts'))


@contract_bp.route('/<int:contract_id>/file/<int:file_id>/delete', methods=['POST'])
@login_required
def delete_contract_file(contract_id, file_id):
    """[v1.4] 删除合同文件"""
    from app.models import ContractFile
    
    contract_file = ContractFile.query.get_or_404(file_id)
    
    # 检查权限：上传者本人或管理员可以删除
    can_delete = False
    if g.current_user.is_superadmin or g.current_user.role.code == 'general_manager':
        can_delete = True
    elif contract_file.contract.created_by_id == g.current_user.id:
        can_delete = True
    
    if not can_delete:
        flash('您无权删除此文件！', 'error')
        return redirect(url_for('contract.edit_contract', id=contract_id))
    
    try:
        # 删除物理文件
        import os
        from flask import current_app
        file_path = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'contract_documents', 
                                 str(contract_id), contract_file.filepath)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # 删除数据库记录
        db.session.delete(contract_file)
        db.session.commit()
        
        flash(f'文件 "{contract_file.filename}" 删除成功！', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除失败：{str(e)}', 'error')
    
    return redirect(url_for('contract.edit_contract', id=contract_id))


@contract_bp.route('/<int:contract_id>/file/<int:file_id>/download')
@login_required
def download_contract_file(contract_id, file_id):
    """[v1.4] 下载合同文件 - 物流经理无权限"""
    from app.models import ContractFile
    
    # 物流经理无权限
    if g.current_user.is_logistics_manager():
        flash('您无权下载合同文件！', 'error')
        return redirect(url_for('main.index'))
    
    contract_file = ContractFile.query.get_or_404(file_id)
    
    # 检查查看权限
    if not g.current_user.can_view_contract(contract_file.contract):
        flash('您无权查看此合同文件！', 'error')
        return redirect(url_for('main.index'))
    
    try:
        import os
        from flask import current_app, send_file
        
        file_path = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'contract_documents',
                                 str(contract_id), contract_file.filepath)
        
        if not os.path.exists(file_path):
            flash('文件不存在！', 'error')
            return redirect(url_for('contract.edit_contract', id=contract_id))
        
        return send_file(file_path, as_attachment=True, download_name=contract_file.filename)
    except Exception as e:
        flash(f'下载失败：{str(e)}', 'error')
        return redirect(url_for('contract.edit_contract', id=contract_id))


# ============ API 接口 ============

@contract_bp.route('/api/stats/<int:id>')
@login_required
def api_get_stats(id):
    """API: 获取合同统计信息"""
    contract = Contract.query.get_or_404(id)
    if not g.current_user.can_view_contract(contract):
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    
    stats = ContractService.get_statistics(id)
    return jsonify(stats)


@contract_bp.route('/api/check-completion/<int:id>')
@login_required
def api_check_completion(id):
    """API: 检查合同完成状态"""
    contract = Contract.query.get_or_404(id)
    if not g.current_user.can_view_contract(contract):
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    
    is_completed = ContractService.check_completion(id)
    return jsonify({
        'is_completed': is_completed,
        'status': contract.status if contract else 'unknown'
    })


@contract_bp.route('/api/contract-products/<int:contract_id>')
@login_required
def api_get_contract_products(contract_id):
    """API: 获取合同产品列表（用于交易记录选择）"""
    contract = Contract.query.get_or_404(contract_id)
    if not g.current_user.can_view_contract(contract):
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    
    products = [
        {
            'id': cp.id,
            'product_code': cp.product_code,
            'product_name': cp.product_name,
            'planned_qty': cp.quantity,
            'delivered_qty': cp.get_delivered_quantity(),
            'remaining_qty': cp.get_remaining_quantity(),
            'unit': cp.unit,
            'price': cp.price
        }
        for cp in contract.contract_products
    ]
    return jsonify({'products': products})


@contract_bp.route('/api/append-remark/<int:id>', methods=['POST'])
@login_required
def api_append_remark(id):
    """API: 追加备注"""
    contract = Contract.query.get_or_404(id)
    if not g.current_user.can_edit_contract(contract):
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    
    payload = request.get_json(silent=True) or {}
    message = payload.get('message', '')
    if message:
        contract.append_remark(message)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'No message provided'})


@contract_bp.route('/api/delete-image/<int:image_id>', methods=['POST'])
@login_required
def api_delete_image(image_id):
    """API: 删除合同图片"""
    from app.models import ContractImage
    try:
        image = ContractImage.query.get_or_404(image_id)
        contract = Contract.query.get(image.contract_id)
        if not contract or not g.current_user.can_edit_contract(contract):
            return jsonify({'success': False, 'error': 'forbidden'}), 403
        
        # 删除文件
        import os
        from flask import current_app
        if os.path.exists(image.filepath):
            os.remove(image.filepath)
        # 删除数据库记录
        db.session.delete(image)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


# ============ 发货单导出功能 ============

@contract_bp.route('/<int:id>/export-delivery-note')
@login_required
def export_delivery_note(id):
    """导出发货单为Excel文件 [v1.3]"""
    from flask import current_app
    
    contract = Contract.query.get_or_404(id)
    if not g.current_user.can_view_contract(contract):
        flash('您没有权限导出此合同的发货单', 'error')
        return redirect(url_for('contract.list_contracts'))
    
    if not contract.transactions:
        flash('没有发货记录，无法导出发货单', 'warning')
        return redirect(url_for('contract.view_contract', id=id))
    
    # 生成发货单编号
    note_no = f"FH{contract.contract_no}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # 输出文件路径
    filename = f"发货单_{contract.contract_no}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
    output_path = os.path.join(current_app.root_path, '..', 'exports', filename)
    output_path = os.path.abspath(output_path)
    
    # 确保exports目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 导出发货单
    export_delivery_note_to_excel(contract, contract.transactions, output_path, note_no)
    
    # 返回文件
    return send_file(
        output_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
