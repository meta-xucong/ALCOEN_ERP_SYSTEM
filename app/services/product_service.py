"""
产品库服务类 - 以产品编码为唯一标识
"""
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
        
        Args:
            product_code: 产品编码
            
        Returns:
            找到返回 Product，未找到返回 None
        """
        if not product_code:
            return None
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
        
        Args:
            product_code: 产品编码（必填）
            product_name: 产品名称（可选）
            product_model: 产品型号（可选）
            product_type: 产品类型（可选）
            default_price: 默认单价（可选）
            remark: 备注（可选）
            image_path: 图片路径（可选）
            
        Returns:
            创建的产品对象
        """
        product = Product(
            product_code=product_code,
            product_name=product_name if product_name else None,
            product_model=product_model if product_model else None,
            product_type=product_type if product_type else None,
            default_price=default_price,
            remark=remark if remark else "从交易记录自动创建",
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
        获取或创建产品 - 关键方法
        
        Args:
            product_code: 产品编码（必填）
            product_name: 产品名称（可选）
            product_model: 产品型号（可选）
            product_type: 产品类型（可选）
            default_price: 默认单价（可选）
            
        Returns:
            Tuple[Product, bool] - (产品对象, 是否新创建)
            
        重要规则：
        - 如果产品编码已存在：返回现有产品，不更新数据，is_new=False
        - 如果产品编码不存在：创建新产品，入库，is_new=True
        
        注意：此方法不会更新已存在产品的任何字段！
              修改产品信息必须通过产品库编辑页面
        """
        # 先查找
        existing = ProductService.find_product_by_code(product_code)
        if existing:
            # 已存在，直接返回，不更新任何数据！
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
        product_code: Optional[str] = None,
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
        交易录入页面的修改不调用此方法！
        
        Args:
            product_id: 产品ID
            product_code: 产品编码（可选，如果提供则更新）
            其他字段为要更新的值，None表示不更新
            
        Returns:
            更新后的产品对象
            
        Raises:
            ValueError: 产品不存在
        """
        product = Product.query.get(product_id)
        if not product:
            raise ValueError(f"产品ID {product_id} 不存在")
        
        if product_code is not None:
            product.product_code = product_code
        if product_name is not None:
            product.product_name = product_name if product_name else None
        if product_model is not None:
            product.product_model = product_model if product_model else None
        if product_type is not None:
            product.product_type = product_type if product_type else None
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
        if not product_id:
            return None
        return Product.query.get(product_id)
    
    @staticmethod
    def get_product_choices() -> list:
        """获取产品选项列表（用于下拉框）- 以编码为标识"""
        products = Product.query.order_by(Product.product_code).all()
        choices = [(0, '-- 请选择产品编码 --')]
        for p in products:
            # 显示格式：编码 - 名称（型号）
            display = p.product_code
            if p.product_name:
                display += f" - {p.product_name}"
            if p.product_model:
                display += f" ({p.product_model})"
            choices.append((p.id, display))
        return choices
    
    @staticmethod
    def search_products(keyword: str = '', product_type: str = '') -> list:
        """搜索产品（支持编码、名称、型号模糊搜索，支持产品类型筛选）
        
        Args:
            keyword: 关键词（搜索编码、名称、型号）
            product_type: 产品类型筛选
        """
        from sqlalchemy import or_, and_
        
        query = Product.query
        
        # 关键词搜索
        if keyword:
            query = query.filter(
                or_(
                    Product.product_code.contains(keyword),
                    Product.product_name.contains(keyword),
                    Product.product_model.contains(keyword)
                )
            )
        
        # 产品类型筛选
        if product_type:
            query = query.filter(Product.product_type == product_type)
        
        return query.order_by(Product.product_code).all()
    
    @staticmethod
    def get_product_list_paginated(
        page: int = 1,
        per_page: int = 20,
        keyword: str = '',
        product_type: str = ''
    ):
        """获取分页产品列表
        
        Args:
            page: 当前页码
            per_page: 每页数量
            keyword: 关键词（搜索编码、名称、型号）
            product_type: 产品类型筛选
            
        Returns:
            Pagination 对象，包含 items, pages, page, has_prev, has_next 等属性
        """
        from sqlalchemy import or_
        
        query = Product.query
        
        # 关键词搜索
        if keyword:
            query = query.filter(
                or_(
                    Product.product_code.contains(keyword),
                    Product.product_name.contains(keyword),
                    Product.product_model.contains(keyword)
                )
            )
        
        # 产品类型筛选
        if product_type:
            query = query.filter(Product.product_type == product_type)
        
        return query.order_by(Product.product_code).paginate(
            page=page, per_page=per_page, error_out=False
        )
    
    @staticmethod
    def check_code_exists(product_code: str) -> bool:
        """检查产品编码是否已存在"""
        if not product_code:
            return False
        return Product.query.filter_by(product_code=product_code).first() is not None
    
    @staticmethod
    def delete_product(product_id: int) -> bool:
        """删除产品"""
        product = Product.query.get(product_id)
        if not product:
            return False
        
        # 检查是否有交易记录关联
        if product.transactions:
            # 有交易记录，不允许删除
            return False
        
        db.session.delete(product)
        db.session.commit()
        return True
    
    @staticmethod
    def get_product_types() -> list:
        """获取所有产品类型列表（去重）
        
        Returns:
            产品类型列表（非空）
        """
        types = db.session.query(Product.product_type).filter(
            Product.product_type.isnot(None),
            Product.product_type != ''
        ).distinct().order_by(Product.product_type).all()
        return [t[0] for t in types]
