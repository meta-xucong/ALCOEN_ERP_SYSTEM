from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, g
from app.forms import StatementGeneratorForm
from app.services.statement_service import StatementService
from app.services.contract_service import ContractService
from app.utils.excel_export import export_statement_to_excel
from app.utils.decorators import login_required, permission_required
import os
from datetime import datetime

statement_bp = Blueprint('statement', __name__)


@statement_bp.route('/generator', methods=['GET', 'POST'])
@login_required
@permission_required('statement_create')
def generator():
    """[LOGIC-8] 对账单生成器 - 支持多维度筛选 [v1.3] 部门/负责人筛选替代归属人 [v1.4] 添加权限过滤"""
    form = StatementGeneratorForm()
    companies = StatementService.get_company_list()
    # [v1.3] 获取部门列表 [v1.5] 移除从Manager表获取负责人列表
    departments = ContractService.get_department_list()
    managers = ContractService.get_owner_list()
    
    if form.validate_on_submit():
        # 获取所有筛选条件
        company_name = form.company_name.data.strip() if form.company_name.data else None
        contract_no = form.contract_no.data.strip() if form.contract_no.data else None
        department = form.department.data.strip() if form.department.data else None
        manager = form.manager.data.strip() if form.manager.data else None
        start_date = form.start_date.data
        end_date = form.end_date.data
        
        # 解析产品编码筛选（精确匹配）
        product_codes = []
        if form.product_code_filter.data:
            product_codes = [p.strip() for p in form.product_code_filter.data.split(',') if p.strip()]
        
        # 解析产品名称筛选（模糊匹配）
        products = []
        if form.product_filter.data:
            products = [p.strip() for p in form.product_filter.data.split(',') if p.strip()]
        
        # [v1.4] 根据用户权限添加额外的筛选条件
        user = g.current_user
        
        # 部门PM：只能生成本部门的对账单
        if user.is_department_pm():
            if user.department:
                department = user.department.name  # 强制使用本部门
            else:
                flash('您的账号未设置部门，无法生成对账单', 'error')
                return redirect(url_for('main.index'))
        
        # 部门销售经理：只能生成自己创建订单的对账单
        elif user.is_sales_manager():
            # 销售经理需要通过created_by过滤，这个在service层处理
            pass
        
        # 验证至少有一个筛选条件（销售经理可以通过created_by筛选，所以单独判断）
        has_filter = any([company_name, contract_no, department, manager, start_date, end_date, product_codes, products])
        if user.is_sales_manager():
            # 销售经理可以通过created_by查看自己的所有订单
            has_filter = has_filter or True  # 销售经理至少有过滤条件（created_by）
        
        if not has_filter:
            flash('请至少输入一个筛选条件！', 'warning')
            return render_template('statement/generator.html', form=form, companies=companies, 
                                 departments=departments, managers=managers)
        
        # 生成对账单 [v1.4] 传入当前用户记录发起人
        result = StatementService.create_statement(
            company_name=company_name,
            start_date=start_date,
            end_date=end_date,
            products=products if products else None,
            contract_no=contract_no,
            product_codes=product_codes if product_codes else None,
            department=department,
            manager=manager,
            created_by=user.id if user.is_sales_manager() else None,  # [v1.4] 销售经理只能看自己的
            current_user=user  # [v1.4] 记录发起人
        )
        
        if result:
            flash(f'对账单生成成功！编号：{result["statement"].statement_no}', 'success')
            return redirect(url_for('statement.view_statement', 
                                  statement_no=result['statement'].statement_no))
        else:
            flash('未找到符合条件的交易记录，请调整筛选条件。', 'warning')
    
    return render_template('statement/generator.html',
                         form=form,
                         companies=companies,
                         departments=departments,
                         managers=managers)


@statement_bp.route('/<statement_no>')
@login_required
@permission_required('statement_view')
def view_statement(statement_no):
    """查看对账单 [v1.4] 添加权限检查"""
    result = StatementService.get_statement_by_no(statement_no)
    
    if not result:
        flash('对账单不存在！', 'error')
        return redirect(url_for('statement.generator'))
    
    # [v1.4] 检查对账单查看权限
    user = g.current_user
    statement = result['statement']
    
    if user.is_department_pm():
        # 部门PM：只能查看本部门发起的对账单
        if not statement.department or statement.department != (user.department.name if user.department else None):
            flash('您无权查看此对账单！', 'error')
            return redirect(url_for('statement.list_statements'))
    
    elif user.is_sales_manager():
        # 销售经理：只能查看自己发起的对账单
        if statement.created_by_id != user.id:
            flash('您无权查看此对账单！', 'error')
            return redirect(url_for('statement.list_statements'))
    
    # 物流经理已通过权限控制无法访问
    # 总经理和超级管理员可以查看所有
    
    companies = StatementService.get_company_list()
    
    return render_template('statement/result.html',
                         statement=result['statement'],
                         transactions=result['transactions'],
                         statement_total_display=result.get('statement_total_receivable', result['statement'].statement_total),
                         filter_products=result['filter_products'],
                         filter_conditions=result.get('filter_conditions', {}),
                         companies=companies)


@statement_bp.route('/<statement_no>/export')
@login_required
@permission_required('statement_export')
def export_statement(statement_no):
    """导出对账单为Excel [v1.4] 添加权限检查"""
    result = StatementService.get_statement_by_no(statement_no)
    
    if not result:
        flash('对账单不存在！', 'error')
        return redirect(url_for('statement.generator'))
    
    # [v1.4] 检查对账单导出权限（与查看权限一致）
    user = g.current_user
    statement = result['statement']
    
    if user.is_department_pm():
        if not statement.department or statement.department != (user.department.name if user.department else None):
            flash('您无权导出此对账单！', 'error')
            return redirect(url_for('statement.list_statements'))
    
    elif user.is_sales_manager():
        if statement.created_by_id != user.id:
            flash('您无权导出此对账单！', 'error')
            return redirect(url_for('statement.list_statements'))
    
    try:
        # 生成文件名
        filename = f"对账单_{result['statement'].statement_no}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', '..', 'exports', filename)
        
        # 导出Excel
        export_statement_to_excel(
            result['statement'],
            result['transactions'],
            filepath
        )
        
        # 发送文件
        return send_file(filepath, as_attachment=True, download_name=filename)
    
    except Exception as e:
        flash(f'导出失败：{str(e)}', 'error')
        return redirect(url_for('statement.view_statement', statement_no=statement_no))


@statement_bp.route('/list')
@login_required
@permission_required('statement_view')
def list_statements():
    """历史对账单列表 [v1.4] 按权限过滤"""
    from app.models import Statement
    from app import db
    
    page = request.args.get('page', 1, type=int)
    company_name = request.args.get('company_name', '')
    
    user = g.current_user
    query = Statement.query
    
    # [v1.4] 按权限过滤对账单
    if user.is_department_pm():
        # 部门PM：查看本部门所有成员发起的对账单
        if user.department:
            query = query.filter(Statement.department == user.department.name)
        else:
            query = query.filter(False)  # 无部门则看不到任何对账单
    
    elif user.is_sales_manager():
        # 销售经理：只能看自己发起的对账单
        query = query.filter(Statement.created_by_id == user.id)
    
    # 物流经理：已通过权限控制无法访问此页面
    # 总经理和超级管理员：查看所有（不添加过滤）
    
    if company_name:
        query = query.filter(Statement.company_name.contains(company_name))
    
    pagination = query.order_by(Statement.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    companies = StatementService.get_company_list()
    
    return render_template('statement/list.html',
                         statements=pagination.items,
                         pagination=pagination,
                         company_name=company_name,
                         companies=companies)


@statement_bp.route('/<statement_no>/delete', methods=['POST'])
@login_required
def delete_statement(statement_no):
    """删除对账单 [v1.4] 每个用户可删除自己对账单"""
    from app.models import Statement
    
    # 先查询对账单检查权限
    statement = Statement.query.filter_by(statement_no=statement_no).first()
    
    if not statement:
        flash('对账单不存在！', 'error')
        return redirect(url_for('statement.list_statements'))
    
    user = g.current_user
    can_delete = False
    
    # 超级管理员和总经理可以删除任何对账单
    if user.is_superadmin or user.role.code == 'general_manager':
        can_delete = True
    
    # 部门PM可以删除本部门的对账单
    elif user.is_department_pm():
        if statement.department and user.department and statement.department == user.department.name:
            can_delete = True
    
    # 销售经理可以删除自己对账单
    elif user.is_sales_manager():
        if statement.created_by_id == user.id:
            can_delete = True
    
    # 所有用户（包括物流经理）都可以删除自己对账单
    elif statement.created_by_id == user.id:
        can_delete = True
    
    if not can_delete:
        flash('您无权删除此对账单！', 'error')
        return redirect(url_for('statement.list_statements'))
    
    try:
        result = StatementService.delete_statement(statement_no)
        if result:
            flash(f'对账单 {statement_no} 删除成功！', 'success')
        else:
            flash('对账单不存在！', 'error')
    except Exception as e:
        flash(f'删除失败：{str(e)}', 'error')
    
    return redirect(url_for('statement.list_statements'))
