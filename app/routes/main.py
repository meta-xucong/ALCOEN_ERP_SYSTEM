from flask import Blueprint, render_template, g
from app.models import Contract, Transaction, Statement
from app.services.statement_service import StatementService
from app.utils.decorators import login_required
from sqlalchemy import func

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def index():
    """首页 - 数据概览 [v1.4] 最近交易记录改为最近交易合同，按权限过滤"""
    from app import db
    user = g.current_user
    
    # [v1.4] 统计数据 - 根据权限过滤
    # 交易合同统计 - 显示所有合同数量
    total_contracts_count = Contract.query.count()
    
    # 对账单统计 - 根据权限过滤
    statement_count_query = Statement.query
    if user.is_department_pm():
        if user.department:
            statement_count_query = statement_count_query.filter(Statement.department == user.department.name)
        else:
            statement_count_query = statement_count_query.filter(False)
    elif user.is_sales_manager():
        statement_count_query = statement_count_query.filter(Statement.created_by_id == user.id)
    # 物流经理、总经理、超级管理员：查看所有
    
    total_statements = statement_count_query.count()
    
    # [v1.4] 构建合同查询 - 根据权限过滤
    contract_query = Contract.query
    
    # 部门PM：只能看到本部门合同
    if user.is_department_pm():
        if user.department:
            contract_query = contract_query.filter(Contract.department == user.department.name)
        else:
            contract_query = contract_query.filter(False)  # 无部门则看不到任何合同
    
    # 销售经理：只能看到自己创建的合同
    elif user.is_sales_manager():
        contract_query = contract_query.filter(Contract.created_by_id == user.id)
    
    # 总经理、物流经理、超级管理员：看到所有（不添加过滤）
    
    # [v1.4] 最近交易合同（有发货记录且最新的合同）
    latest_transaction = db.session.query(
        Transaction.contract_id,
        func.max(Transaction.created_at).label('latest_trans_at')
    ).group_by(Transaction.contract_id).subquery()
    
    recent_contracts = contract_query.join(
        latest_transaction, Contract.id == latest_transaction.c.contract_id
    ).order_by(
        latest_transaction.c.latest_trans_at.desc()
    ).limit(5).all()
    
    # 如果没有交易记录，显示最近的合同
    if not recent_contracts:
        recent_contracts = contract_query.order_by(
            Contract.created_at.desc()
        ).limit(5).all()
    
    # [v1.4] 最近对账单 - 根据权限过滤（使用新的department和created_by_id字段）
    statement_query = Statement.query
    
    if user.is_department_pm():
        # 部门PM：查看本部门所有成员发起的对账单
        if user.department:
            statement_query = statement_query.filter(Statement.department == user.department.name)
        else:
            statement_query = statement_query.filter(False)
    
    elif user.is_sales_manager():
        # 销售经理：只能看自己发起的对账单
        statement_query = statement_query.filter(Statement.created_by_id == user.id)
    
    # 物流经理：已通过权限控制无法访问
    # 总经理和超级管理员：查看所有（不添加过滤）
    
    recent_statements = statement_query.order_by(
        Statement.created_at.desc()
    ).limit(5).all()
    
    # 获取公司列表（用于自动补全）
    companies = StatementService.get_company_list()
    
    return render_template('index.html',
                         total_contracts=total_contracts_count,
                         total_statements=total_statements,
                         recent_contracts=recent_contracts,
                         recent_statements=recent_statements,
                         companies=companies)


@main_bp.route('/api/companies')
def api_companies():
    """API: 获取公司名称列表（用于自动补全）"""
    companies = StatementService.get_company_list()
    return {'companies': [{'name': c} for c in companies]}
