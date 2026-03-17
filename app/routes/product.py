"""
产品库路由
"""
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from app.forms import ProductForm
from app.services.product_service import ProductService
from app.models import Product
from app.utils.decorators import login_required, permission_required

product_bp = Blueprint('product', __name__, url_prefix='/product')


@product_bp.route('/')
@login_required
@permission_required('product_view')
def list_products():
    """产品库列表"""
    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '')
    product_type = request.args.get('product_type', '')
    
    if keyword or product_type:
        products = ProductService.search_products(keyword, product_type)
    else:
        products = ProductService.get_all_products()
    
    # 简单分页
    per_page = 20
    total = len(products)
    start = (page - 1) * per_page
    end = start + per_page
    products_page = products[start:end]
    
    # 获取所有产品类型列表（去重）
    product_types = ProductService.get_product_types()
    
    return render_template('product/list.html',
                         products=products_page,
                         page=page,
                         total_pages=(total + per_page - 1) // per_page,
                         total=total,
                         keyword=keyword,
                         product_type=product_type,
                         product_types=product_types)


@product_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('product_create')
def new_product():
    """新增产品"""
    form = ProductForm()
    
    if form.validate_on_submit():
        # 检查产品编码是否已存在
        if ProductService.check_code_exists(form.product_code.data):
            flash(f'产品编码 "{form.product_code.data}" 已存在，请使用其他编码', 'error')
            return render_template('product/form.html', form=form, title='新增产品')
        
        try:
            # 保存图片
            image_filename = None
            if form.image.data:
                upload_folder = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'products')
                os.makedirs(upload_folder, exist_ok=True)
                image_filename = ProductService.save_image(form.image.data, upload_folder)
            
            product = ProductService.create_product(
                product_code=form.product_code.data,
                product_name=form.product_name.data,
                product_model=form.product_model.data,
                product_type=form.product_type.data,
                default_price=form.default_price.data,
                remark=form.remark.data,
                image_path=image_filename
            )
            
            flash(f'产品 "{product.product_code}" 添加成功！', 'success')
            return redirect(url_for('product.list_products'))
        
        except Exception as e:
            flash(f'添加失败：{str(e)}', 'error')
    
    return render_template('product/form.html', form=form, title='新增产品')


@product_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('product_edit')
def edit_product(id):
    """编辑产品 - 这是修改产品库信息的唯一途径"""
    product = Product.query.get_or_404(id)
    form = ProductForm(obj=product)
    
    if form.validate_on_submit():
        try:
            # 如果修改了编码，检查新编码是否已存在
            new_code = form.product_code.data
            if new_code != product.product_code and ProductService.check_code_exists(new_code):
                flash(f'产品编码 "{new_code}" 已存在', 'error')
                return render_template('product/form.html', form=form, product=product, title='编辑产品')
            
            # 更新图片
            image_filename = product.image_path
            if form.image.data:
                upload_folder = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'products')
                os.makedirs(upload_folder, exist_ok=True)
                new_image = ProductService.save_image(form.image.data, upload_folder)
                if new_image:
                    image_filename = new_image
            
            # 更新产品信息
            ProductService.update_product(
                product_id=id,
                product_code=new_code,
                product_name=form.product_name.data,
                product_model=form.product_model.data,
                product_type=form.product_type.data,
                default_price=form.default_price.data,
                remark=form.remark.data,
                image_path=image_filename
            )
            
            flash(f'产品 "{new_code}" 更新成功！', 'success')
            return redirect(url_for('product.list_products'))
        
        except Exception as e:
            flash(f'更新失败：{str(e)}', 'error')
    
    return render_template('product/form.html', form=form, product=product, title='编辑产品')


@product_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('product_delete')
def delete_product(id):
    """删除产品"""
    try:
        result = ProductService.delete_product(id)
        if result:
            flash('产品删除成功！', 'success')
        else:
            flash('该产品有关联的交易记录，无法删除', 'error')
    except Exception as e:
        flash(f'删除失败：{str(e)}', 'error')
    
    return redirect(url_for('product.list_products'))


# ============ API 接口 ============

@product_bp.route('/api/list')
@login_required
def api_product_list():
    """API: 获取产品列表（JSON）"""
    products = ProductService.get_all_products()
    return jsonify({
        'products': [p.to_dict() for p in products]
    })


@product_bp.route('/api/<int:id>')
@login_required
def api_product_detail(id):
    """API: 获取单个产品详情"""
    product = ProductService.get_product_by_id(id)
    if product:
        return jsonify(product.to_dict())
    return jsonify({'error': 'Product not found'}), 404


@product_bp.route('/api/by-code/<string:code>')
@login_required
def api_product_by_code(code):
    """API: 根据编码获取产品详情"""
    product = ProductService.find_product_by_code(code)
    if product:
        return jsonify(product.to_dict())
    return jsonify({'error': 'Product not found'}), 404


@product_bp.route('/api/check-code')
@login_required
def api_check_code():
    """API: 检查产品编码是否已存在"""
    code = request.args.get('code', '')
    exists = ProductService.check_code_exists(code)
    
    response = {'exists': exists}
    
    if exists:
        product = ProductService.find_product_by_code(code)
        if product:
            response['product'] = product.to_dict()
    
    return jsonify(response)
