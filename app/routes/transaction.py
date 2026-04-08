"""
交易记录路由
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.models import Transaction
from app.forms import TransactionForm
from app.services.transaction_service import TransactionService
from app.services.statement_service import StatementService
from app.services.product_service import ProductService
from app.utils.decorators import login_required, permission_required
from app import db

transaction_bp = Blueprint('transaction', __name__)


@transaction_bp.route('/')
@login_required
@permission_required('transaction_view')
def list_transactions():
    """交易记录列表 - v1.1 增加产品编码、发货日期筛选"""
    page = request.args.get('page', 1, type=int)
    company_name = request.args.get('company_name', '')
    product_name = request.args.get('product_name', '')
    product_code = request.args.get('product_code', '')  # v1.1: 新增
    delivery_date_start = request.args.get('delivery_date_start', '')
    delivery_date_end = request.args.get('delivery_date_end', '')
    
    # 转换日期
    start_date = None
    end_date = None
    if delivery_date_start:
        from datetime import datetime
        start_date = datetime.strptime(delivery_date_start, '%Y-%m-%d').date()
    if delivery_date_end:
        end_date = datetime.strptime(delivery_date_end, '%Y-%m-%d').date()
    
    pagination = TransactionService.get_transaction_list(
        page=page,
        per_page=20,
        company_name=company_name or None,
        product_name=product_name or None,
        product_code=product_code or None,  # v1.1: 新增
        start_date=start_date,
        end_date=end_date
    )
    
    companies = StatementService.get_company_list()
    
    return render_template('transaction/list.html',
                         transactions=pagination.items,
                         pagination=pagination,
                         company_name=company_name,
                         product_name=product_name,
                         product_code=product_code,  # v1.1: 新增
                         delivery_date_start=delivery_date_start,
                         delivery_date_end=delivery_date_end,
                         companies=companies)


@transaction_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('transaction_create')
def new_transaction():
    """新增交易记录 - v1.1 产品编码版（关键逻辑）"""
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
            
            # ========== 获取产品编码和相关信息 ==========
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
                    return render_template('transaction/form.html',
                                         form=form,
                                         title='新增交易记录',
                                         companies=StatementService.get_company_list())
            
            else:
                # ===== 手动输入 =====
                product_code = form.product_code.data.strip()
                
                if not product_code:
                    flash('请输入产品编码', 'error')
                    return render_template('transaction/form.html',
                                         form=form,
                                         title='新增交易记录',
                                         companies=StatementService.get_company_list())
                
                # 关键逻辑：获取或创建产品
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
                    # 现有产品：使用用户输入的数据（可能已修改！）
                    # 重要：不使用产品库的数据，使用用户表单中的数据
                    product_name = form.product_name.data
                    product_model = form.product_model.data
                    product_type = form.product_type.data
                    price = form.price_with_tax.data
                    # 不更新产品库！这是关键！
            
            # ========== 创建交易记录 ==========
            data = {
                'company_name': form.company_name.data,
                'product_id': product_id,
                'product_code': product_code,       # 必填
                'product_name': product_name,        # 用户输入（可能修改过）
                'product_model': product_model,      # 用户输入（可能修改过）
                'product_type': product_type,        # 用户输入（可能修改过）
                'quantity': form.quantity.data,
                'unit': form.unit.data,
                'price_with_tax': price,
                'handler': '系统录入',
                'delivery_date': form.delivery_date.data,
                'invoice_date': form.invoice_date.data,
                'contract_no': form.contract_no.data,
                'remark': form.remark.data
            }
            
            TransactionService.create_transaction(data)
            flash('交易记录添加成功！', 'success')
            return redirect(url_for('transaction.list_transactions'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'添加失败：{str(e)}', 'error')
    
    companies = StatementService.get_company_list()
    return render_template('transaction/form.html',
                         form=form,
                         title='新增交易记录',
                         companies=companies)


@transaction_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('transaction_edit')
def edit_transaction(id):
    """编辑交易记录"""
    transaction = Transaction.query.get_or_404(id)
    form = TransactionForm(obj=transaction)
    form.product_id.choices = ProductService.get_product_choices()
    
    # 设置产品选择模式为手动（因为是编辑）
    if request.method == 'GET':
        form.product_select_mode.data = 'manual'
        form.product_code.data = transaction.product_code
    
    if form.validate_on_submit():
        try:
            # 编辑时不自动创建新产品，只更新交易记录
            product = ProductService.find_product_by_code(form.product_code.data)
            product_id = product.id if product else transaction.product_id
            
            data = {
                'company_name': form.company_name.data,
                'product_id': product_id,
                'product_code': form.product_code.data,
                'product_name': form.product_name.data,
                'product_model': form.product_model.data,
                'product_type': form.product_type.data,
                'quantity': form.quantity.data,
                'unit': form.unit.data,
                'price_with_tax': form.price_with_tax.data,
                'handler': transaction.handler or '系统录入',
                'delivery_date': form.delivery_date.data,
                'invoice_date': form.invoice_date.data,
                'contract_no': form.contract_no.data,
                'remark': form.remark.data
            }
            
            TransactionService.update_transaction(id, data)
            flash('交易记录更新成功！', 'success')
            return redirect(url_for('transaction.list_transactions'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'更新失败：{str(e)}', 'error')
    
    companies = StatementService.get_company_list()
    return render_template('transaction/form.html',
                         form=form,
                         transaction=transaction,
                         title='编辑交易记录',
                         companies=companies)


@transaction_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('transaction_delete')
def delete_transaction(id):
    """删除交易记录"""
    try:
        TransactionService.delete_transaction(id)
        flash('交易记录删除成功！', 'success')
    except Exception as e:
        flash(f'删除失败：{str(e)}', 'error')
    
    return redirect(url_for('transaction.list_transactions'))


@transaction_bp.route('/api/products-by-company')
@login_required
@permission_required('transaction_view')
def api_products_by_company():
    """API: 获取指定公司的所有产品编码"""
    company_name = request.args.get('company_name', '')
    if company_name:
        codes = TransactionService.get_products_by_company(company_name)
        return jsonify({'codes': codes})
    return jsonify({'codes': []})
