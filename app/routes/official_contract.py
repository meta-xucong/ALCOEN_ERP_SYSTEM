"""Routes for the independent official-contract generator."""

from __future__ import annotations

import os
from pathlib import Path

from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from app.models import (
    Department,
    FormalContract,
    FormalContractDocument,
    FormalContractParty,
    FormalContractTemplate,
    Product,
)
from app.services.official_contract_service import (
    OfficialContractService,
    OfficialContractValidationError,
)
from app.utils.decorators import login_required, permission_required


official_contract_bp = Blueprint(
    'official_contract',
    __name__,
    url_prefix='/official-contract',
)


def _can_view(formal_contract: FormalContract) -> bool:
    return bool(
        g.current_user
        and g.current_user.has_permission('formal_contract_view')
    )


def _get_formal_contract(formal_contract_id: int) -> FormalContract:
    formal_contract = FormalContract.query.get_or_404(formal_contract_id)
    if not _can_view(formal_contract):
        flash('您没有权限查看此正式合同', 'error')
        raise PermissionError
    return formal_contract


def _available_departments():
    """Return departments the current user may assign to a formal contract."""
    user = g.current_user
    if user.is_superadmin or (
        user.role and user.role.code in {'general_manager', 'gm_assistant'}
    ):
        return Department.query.order_by(Department.name.asc()).all()
    return sorted(user.departments, key=lambda department: department.name)


def _extract_items(form_data) -> list[dict]:
    rows = []
    row_count = form_data.get('item_count', type=int) or 0
    for index in range(max(row_count, 0)):
        prefix = f'item_{index}_'
        product_id = form_data.get(f'{prefix}product_id') or None
        product_code = form_data.get(f'{prefix}product_code', '')
        product_name = form_data.get(f'{prefix}product_name', '')
        if (
            not product_id
            and not str(product_code or '').strip()
            and not str(product_name or '').strip()
        ):
            continue
        rows.append({
            'product_id': product_id,
            'product_code': product_code,
            'product_name': product_name,
            'product_model': form_data.get(f'{prefix}product_model', ''),
            'unit': form_data.get(f'{prefix}unit', '个'),
            'quantity': form_data.get(f'{prefix}quantity', ''),
            'unit_price': form_data.get(f'{prefix}unit_price', ''),
            'remark': form_data.get(f'{prefix}remark', ''),
        })
    return rows


def _form_data_from_request():
    data = {
        'party_a_name': request.form.get('party_a_name', ''),
        'billing_address': request.form.get('billing_address', ''),
        'phone': request.form.get('phone', ''),
        'tax_no': request.form.get('tax_no', ''),
        'bank_name': request.form.get('bank_name', ''),
        'bank_account': request.form.get('bank_account', ''),
        'party_b_name': request.form.get('party_b_name', ''),
        'party_b_billing_address': request.form.get('party_b_billing_address', ''),
        'party_b_phone': request.form.get('party_b_phone', ''),
        'party_b_tax_no': request.form.get('party_b_tax_no', ''),
        'party_b_bank_name': request.form.get('party_b_bank_name', ''),
        'party_b_bank_account': request.form.get('party_b_bank_account', ''),
        'contract_no': request.form.get('contract_no', ''),
        'sign_place': request.form.get('sign_place', ''),
        'sign_date': request.form.get('sign_date', ''),
        'quality_standard': request.form.get('quality_standard', ''),
        'delivery_terms': request.form.get('delivery_terms', ''),
        'delivery_schedule': request.form.get('delivery_schedule', ''),
        'settlement_terms': request.form.get('settlement_terms', ''),
        'breach_terms': request.form.get('breach_terms', ''),
        'dispute_terms': request.form.get('dispute_terms', ''),
        'department_id': request.form.get('department_id', ''),
    }
    return data, _extract_items(request.form)


def _render_form(formal_contract=None, form_data=None, items=None, title='新建正式合同'):
    defaults = OfficialContractService.get_party_defaults()
    if formal_contract:
        defaults = {
            'party_id': formal_contract.party_id,
            'company_id': formal_contract.party.company_id,
            'department_id': formal_contract.department_id or '',
            'party_a_name': formal_contract.party.party_a_name,
            'billing_address': (
                formal_contract.party_a_billing_address
                if formal_contract.party_a_billing_address is not None
                else formal_contract.party.billing_address
                or ''
            ),
            'phone': (
                formal_contract.party_a_phone
                if formal_contract.party_a_phone is not None
                else formal_contract.party.phone
                or ''
            ),
            'tax_no': (
                formal_contract.party_a_tax_no
                if formal_contract.party_a_tax_no is not None
                else formal_contract.party.tax_no
                or ''
            ),
            'bank_name': (
                formal_contract.party_a_bank_name
                if formal_contract.party_a_bank_name is not None
                else formal_contract.party.bank_name
                or ''
            ),
            'bank_account': (
                formal_contract.party_a_bank_account
                if formal_contract.party_a_bank_account is not None
                else formal_contract.party.bank_account
                or ''
            ),
            'party_b_name': formal_contract.party_b_name or '',
            'party_b_billing_address': formal_contract.party_b_billing_address or '',
            'party_b_phone': formal_contract.party_b_phone or '',
            'party_b_tax_no': formal_contract.party_b_tax_no or '',
            'party_b_bank_name': formal_contract.party_b_bank_name or '',
            'party_b_bank_account': formal_contract.party_b_bank_account or '',
            'contract_no': formal_contract.contract_no or '',
            'sign_place': formal_contract.sign_place or '',
            'sign_date': (
                formal_contract.sign_date.strftime('%Y-%m-%d')
                if formal_contract.sign_date else ''
            ),
            'quality_standard': formal_contract.quality_standard or '',
            'delivery_terms': formal_contract.delivery_terms or '',
            'delivery_schedule': formal_contract.delivery_schedule or '',
            'settlement_terms': formal_contract.settlement_terms or '',
            'breach_terms': formal_contract.breach_terms or '',
            'dispute_terms': formal_contract.dispute_terms or '',
        }
        items = items if items is not None else [
            {
                'product_id': item.product_id or '',
                'product_code': item.product_code or '',
                'product_name': item.product_name or '',
                'product_model': item.product_model or '',
                'unit': item.unit or '个',
                'quantity': item.quantity,
                'unit_price': item.unit_price,
                'remark': item.remark or '',
            }
            for item in formal_contract.items
        ]

    merged = {**defaults, **(form_data or {})}
    departments = _available_departments()
    selected_department_id = merged.get('department_id') or ''
    if not selected_department_id and len(departments) == 1:
        selected_department_id = departments[0].id
        merged['department_id'] = selected_department_id
    if selected_department_id and not any(
        str(department.id) == str(selected_department_id)
        for department in departments
    ):
        selected_department = Department.query.get(int(selected_department_id))
        if selected_department:
            departments = sorted(
                [*departments, selected_department],
                key=lambda department: department.name,
            )
    products = Product.query.order_by(Product.product_code.asc()).all()
    return render_template(
        'official_contract/form.html',
        title=title,
        formal_contract=formal_contract,
        form_data=merged,
        items=items or [{}],
        departments=departments,
        product_options=products,
    )


@official_contract_bp.route('/')
@login_required
@permission_required('formal_contract_view')
def list_formal_contracts():
    """List formal contracts, newest first."""
    keyword = (request.args.get('keyword') or '').strip()
    query = FormalContract.query.join(FormalContract.party)
    if keyword:
        pattern = f'%{keyword}%'
        query = query.filter(
            FormalContract.contract_no.ilike(pattern)
            | FormalContractParty.party_a_name.ilike(pattern)
        )
    formal_contracts = query.order_by(
        FormalContract.updated_at.desc(),
        FormalContract.id.desc(),
    ).limit(100).all()
    return render_template(
        'official_contract/list.html',
        formal_contracts=formal_contracts,
        keyword=keyword,
    )


@official_contract_bp.route('/new', methods=['GET', 'POST'])
@login_required
@permission_required('formal_contract_create')
def new_formal_contract():
    """Create a formal contract draft."""
    if request.method == 'POST':
        data, items = _form_data_from_request()
        try:
            formal_contract = OfficialContractService.save_formal_contract(
                data,
                items,
                g.current_user.id,
            )
            flash('正式合同草稿已保存', 'success')
            return redirect(
                url_for(
                    'official_contract.view_formal_contract',
                    formal_contract_id=formal_contract.id,
                )
            )
        except (OfficialContractValidationError, ValueError) as exc:
            flash(str(exc), 'error')
            return _render_form(form_data=data, items=items)
    return _render_form()


@official_contract_bp.route('/<int:formal_contract_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('formal_contract_edit')
def edit_formal_contract(formal_contract_id: int):
    """Edit a formal contract that has not been synchronized."""
    formal_contract = _get_formal_contract(formal_contract_id)
    if formal_contract.is_synced:
        flash('已同步交易合同的正式合同不能直接编辑，请复制为新合同', 'warning')
        return redirect(
            url_for(
                'official_contract.view_formal_contract',
                formal_contract_id=formal_contract.id,
            )
        )
    if request.method == 'POST':
        data, items = _form_data_from_request()
        try:
            OfficialContractService.save_formal_contract(
                data,
                items,
                g.current_user.id,
                formal_contract_id=formal_contract.id,
            )
            flash('正式合同已保存', 'success')
            return redirect(
                url_for(
                    'official_contract.view_formal_contract',
                    formal_contract_id=formal_contract.id,
                )
            )
        except (OfficialContractValidationError, ValueError) as exc:
            flash(str(exc), 'error')
            return _render_form(
                formal_contract=formal_contract,
                form_data=data,
                items=items,
                title='编辑正式合同',
            )
    return _render_form(
        formal_contract=formal_contract,
        title='编辑正式合同',
    )


@official_contract_bp.route('/<int:formal_contract_id>')
@login_required
@permission_required('formal_contract_view')
def view_formal_contract(formal_contract_id: int):
    """Show one formal contract and its generated files."""
    formal_contract = _get_formal_contract(formal_contract_id)
    return render_template(
        'official_contract/detail.html',
        formal_contract=formal_contract,
        context=OfficialContractService.build_context(formal_contract),
        history=OfficialContractService.get_history(formal_contract.id),
    )


@official_contract_bp.route('/<int:formal_contract_id>/generate', methods=['POST'])
@login_required
@permission_required('formal_contract_generate')
def generate_formal_contract(formal_contract_id: int):
    """Generate a DOCX file from the active template."""
    formal_contract = _get_formal_contract(formal_contract_id)
    if not g.current_user.can_view_financial() and formal_contract.total_amount:
        flash('当前账号没有查看合同金额的权限，无法生成正式合同', 'error')
        return redirect(
            url_for(
                'official_contract.view_formal_contract',
                formal_contract_id=formal_contract.id,
            )
        )
    try:
        document = OfficialContractService.generate_document(
            formal_contract.id,
            user_id=g.current_user.id,
        )
        flash('正式合同 DOCX 已生成', 'success')
        if request.form.get('next') == 'print':
            return redirect(
                url_for(
                    'official_contract.print_formal_contract',
                    formal_contract_id=formal_contract.id,
                    document_id=document.id,
                    autoprint=1,
                )
            )
    except (OfficialContractValidationError, ValueError) as exc:
        flash(str(exc), 'error')
    return redirect(
        url_for(
            'official_contract.view_formal_contract',
            formal_contract_id=formal_contract.id,
        )
    )


@official_contract_bp.route('/<int:formal_contract_id>/print')
@login_required
@permission_required('formal_contract_print')
def print_formal_contract(formal_contract_id: int):
    """Render the browser-printable official contract page."""
    formal_contract = _get_formal_contract(formal_contract_id)
    document_id = request.args.get('document_id', type=int)
    document = (
        FormalContractDocument.query.filter_by(
            id=document_id,
            formal_contract_id=formal_contract.id,
        ).first()
        if document_id else formal_contract.latest_document
    )
    if not document:
        if not g.current_user.has_permission('formal_contract_generate'):
            flash('请先生成正式合同文件', 'warning')
            return redirect(
                url_for(
                    'official_contract.view_formal_contract',
                    formal_contract_id=formal_contract.id,
                )
            )
        try:
            document = OfficialContractService.generate_document(
                formal_contract.id,
                user_id=g.current_user.id,
            )
        except OfficialContractValidationError as exc:
            flash(str(exc), 'error')
            return redirect(
                url_for(
                    'official_contract.view_formal_contract',
                    formal_contract_id=formal_contract.id,
                )
            )

    OfficialContractService.mark_printed(document.id)
    return render_template(
        'official_contract/print.html',
        formal_contract=formal_contract,
        context=OfficialContractService.get_document_context(
            document,
            fallback_formal_contract=formal_contract,
        ),
        document=document,
        auto_print=request.args.get('autoprint', '1') != '0',
        embedded=request.args.get('embedded', '0') == '1',
    )


@official_contract_bp.route('/<int:formal_contract_id>/documents/<int:document_id>/download')
@login_required
@permission_required('formal_contract_print')
def download_formal_contract(formal_contract_id: int, document_id: int):
    """Download a generated DOCX file."""
    formal_contract = _get_formal_contract(formal_contract_id)
    document = FormalContractDocument.query.filter_by(
        id=document_id,
        formal_contract_id=formal_contract.id,
    ).first_or_404()
    file_path = Path(document.docx_path)
    if not file_path.is_file():
        flash('正式合同文件不存在，请重新生成', 'error')
        return redirect(
            url_for(
                'official_contract.view_formal_contract',
                formal_contract_id=formal_contract.id,
            )
        )
    return send_file(
        file_path,
        as_attachment=True,
        download_name=f'正式合同_{formal_contract.id}_{document.id}.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )


@official_contract_bp.route('/<int:formal_contract_id>/sync', methods=['POST'])
@login_required
@permission_required('formal_contract_sync')
def sync_formal_contract(formal_contract_id: int):
    """Create the equivalent ERP transaction contract once."""
    formal_contract = _get_formal_contract(formal_contract_id)
    if not g.current_user.has_permission('contract_create'):
        flash('当前账号没有创建交易合同的权限', 'error')
        return redirect(
            url_for(
                'official_contract.view_formal_contract',
                formal_contract_id=formal_contract.id,
            )
        )
    try:
        sync = OfficialContractService.sync_to_transaction_contract(
            formal_contract.id,
            user_id=g.current_user.id,
        )
        flash('已同步到交易合同', 'success')
        if sync.contract_id:
            return redirect(url_for('contract.view_contract', id=sync.contract_id))
    except OfficialContractValidationError as exc:
        flash(str(exc), 'error')
    return redirect(
        url_for(
            'official_contract.view_formal_contract',
            formal_contract_id=formal_contract.id,
        )
    )


@official_contract_bp.route('/api/parties')
@login_required
@permission_required('formal_contract_view')
def api_parties():
    """Search party-A profiles and existing ERP companies."""
    return jsonify({
        'parties': OfficialContractService.search_parties(
            request.args.get('keyword', ''),
            limit=min(request.args.get('limit', 20, type=int) or 20, 50),
        )
    })


@official_contract_bp.route('/api/parties/defaults')
@login_required
@permission_required('formal_contract_view')
def api_party_defaults():
    """Return recent defaults for a selected party-A record."""
    defaults = OfficialContractService.get_party_defaults(
        party_id=request.args.get('party_id', type=int),
        party_name=request.args.get('party_name'),
    )
    return jsonify(defaults)


@official_contract_bp.route('/api/products')
@login_required
@permission_required('formal_contract_view')
def api_products():
    """Search existing ERP products for a formal-contract line."""
    keyword = (request.args.get('keyword') or '').strip()
    query = Product.query
    if keyword:
        pattern = f'%{keyword}%'
        query = query.filter(
            Product.product_code.ilike(pattern)
            | Product.product_name.ilike(pattern)
            | Product.product_model.ilike(pattern)
        )
    products = query.order_by(Product.product_code.asc()).limit(30).all()
    return jsonify({
        'products': [product.to_dict() for product in products]
    })


@official_contract_bp.route('/templates')
@login_required
@permission_required('formal_contract_template_manage')
def list_templates():
    """List uploaded formal-contract template versions."""
    templates = FormalContractTemplate.query.order_by(
        FormalContractTemplate.created_at.desc(),
        FormalContractTemplate.id.desc(),
    ).all()
    return render_template(
        'official_contract/template_list.html',
        templates=templates,
        departments=Department.query.order_by(Department.name.asc()).all(),
    )


@official_contract_bp.route('/templates/upload', methods=['POST'])
@login_required
@permission_required('formal_contract_template_manage')
def upload_template():
    """Upload a DOCX template version."""
    try:
        template = OfficialContractService.create_template(
            request.files.get('template_file'),
            name=request.form.get('name', ''),
            version=request.form.get('version', ''),
            description=request.form.get('description', ''),
            uploaded_by_id=g.current_user.id,
            department_id=request.form.get('department_id', type=int),
        )
        warnings = getattr(template, 'validation', {}).get('warnings', [])
        for warning in warnings:
            flash(warning, 'warning')
        flash('正式合同模板上传成功，请校验后启用', 'success')
    except OfficialContractValidationError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('official_contract.list_templates'))


@official_contract_bp.route('/templates/<int:template_id>/activate', methods=['POST'])
@login_required
@permission_required('formal_contract_template_manage')
def activate_template(template_id: int):
    """Activate one template and deactivate the previous active version."""
    try:
        OfficialContractService.activate_template(template_id)
        flash('正式合同模板已启用', 'success')
    except OfficialContractValidationError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('official_contract.list_templates'))
