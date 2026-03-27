#!/usr/bin/env python
"""
从原始 Excel 文件导入数据到 v1.1 数据库
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import pandas as pd
from datetime import datetime
from app import create_app, db
from app.models import Transaction, Product, Company
from app.services.product_service import ProductService


def parse_date(date_val):
    """解析日期"""
    if pd.isna(date_val):
        return None
    try:
        if isinstance(date_val, (int, float)):
            date_str = str(int(date_val))
        else:
            date_str = str(date_val)
        
        if len(date_str) == 8:
            return datetime.strptime(date_str, '%Y%m%d').date()
        return None
    except:
        return None


def import_data():
    """从 Excel 导入数据"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("Import data from CHARM.xlsx to v1.1 database")
        print("=" * 60)
        
        # 读取 Excel
        excel_path = os.path.join('profile', 'CHARM.xlsx')
        if not os.path.exists(excel_path):
            print(f"Error: {excel_path} not found")
            return
        
        print(f"\nReading {excel_path}...")
        df = pd.read_excel(excel_path, header=None)
        
        print(f"Total rows in Excel: {len(df)}")
        
        # 跳过表头行（第0行），从第1行开始读取数据
        data_rows = df.iloc[1:].reset_index(drop=True)
        
        # 统计数据
        imported_count = 0
        skipped_count = 0
        products_created = set()
        
        print("\n" + "=" * 60)
        print("Importing transactions...")
        print("=" * 60)
        
        for idx, row in data_rows.iterrows():
            try:
                # 获取数据 (根据实际列索引)
                seq_no = row.iloc[0]          # 序号
                product_info = row.iloc[1]    # 名称及型号
                quantity = row.iloc[2]        # 数量
                unit = row.iloc[3]            # 单位
                price = row.iloc[4]           # 含税价格
                delivery_date = parse_date(row.iloc[10])  # 发货日期
                
                # 检查必要字段
                if pd.isna(seq_no) or pd.isna(product_info):
                    skipped_count += 1
                    continue
                
                # 解析数据
                try:
                    seq_no = int(seq_no)
                    quantity = float(quantity) if not pd.isna(quantity) else 1
                    price = float(price) if not pd.isna(price) else 0
                except:
                    skipped_count += 1
                    continue
                
                product_info = str(product_info).strip()
                unit = str(unit).strip() if not pd.isna(unit) else "个"
                
                # 生成产品编码
                product_code = f"P{seq_no:04d}"
                
                # 检查或创建产品
                if product_code not in products_created:
                    product, is_new = ProductService.get_or_create_product(
                        product_code=product_code,
                        product_name=product_info,
                        product_model=None,
                        product_type=None,
                        default_price=price
                    )
                    if is_new:
                        products_created.add(product_code)
                        print(f"  Created product: {product_code} - {product_info[:30]}")
                else:
                    product = ProductService.find_product_by_code(product_code)
                
                # 创建交易记录
                transaction = Transaction(
                    company_name="江苏纯安",
                    product_id=product.id if product else None,
                    product_code=product_code,
                    product_name=product_info,
                    product_model=None,
                    product_type=None,
                    quantity=quantity,
                    unit=unit,
                    price_with_tax=price,
                    total_price_with_tax=quantity * price,
                    delivery_date=delivery_date or datetime.now().date(),
                    invoice_date=None,
                    payment_date=None,
                    contract_no=None,
                    remark="从Excel导入"
                )
                
                db.session.add(transaction)
                imported_count += 1
                
                if imported_count % 5 == 0:
                    print(f"  Imported {imported_count} transactions...")
                    db.session.commit()  # 分批提交
                
            except Exception as e:
                print(f"  Error at row {idx}: {e}")
                skipped_count += 1
                continue
        
        # 最终提交
        db.session.commit()
        
        # 添加公司记录
        company = Company.query.filter_by(name="江苏纯安").first()
        if not company:
            company = Company(name="江苏纯安")
            db.session.add(company)
            db.session.commit()
        
        print("\n" + "=" * 60)
        print("Import completed!")
        print("=" * 60)
        print(f"Imported: {imported_count} transactions")
        print(f"Products created: {len(products_created)}")
        print(f"Skipped: {skipped_count} rows")
        print("\nNext steps:")
        print("1. Start server: python run.py")
        print("2. Access: http://localhost:8080")
        print("=" * 60)


if __name__ == '__main__':
    import_data()
