"""QC routes."""

from __future__ import annotations

import re
from io import BytesIO
from datetime import datetime

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, send_file, url_for
from sqlalchemy import or_

from app import db
from app.models import (
    AI_CATS_IDENTITY_DEFINITIONS,
    AI_CATS_LEGACY_ROLE_IDENTITY_MAP,
    QC_ADMIN_ROLE_CODES,
    QC_MANAGER_ROLE_CODES,
    QC_ROLE_CODES,
    QC_ROLE_EDITABLE_PERMISSIONS,
    QC_WORKPIECE_TYPE_DISPLAY,
    QCAcceptanceSignature,
    AssemblyOrder,
    AICatsAccountProfile,
    AICatsIdentityAuditLog,
    AICatsUserIdentity,
    QCUserBinding,
    QCWorkOrder,
    QCWorkOrderAttachment,
    QCWorkpiece,
    Role,
    User,
)
from app.services.auth_service import AuthService
from app.services.assembly_service import AssemblyService
from app.services.ai_cats_access_service import AICatsAccessService
from app.services.qc_service import QCService
from app.services.research_service import ResearchService
from app.services.user_service import UserService
from app.utils.decorators import login_required

qc_bp = Blueprint('qc', __name__, url_prefix='/qc')

RESEARCH_PROJECT_CATEGORY_OPTIONS = [
    '方法开发',
    '样品验证',
    '问题排查',
    '其他研究',
]
RESEARCH_ENDPOINT_PREFIX = 'qc.research_'
ASSEMBLY_ENDPOINT_PREFIX = 'qc.assembly_'


def _extract_dynamic_indexes(form_data, prefix: str) -> list[int]:
    """Extract and sort numeric suffixes from dynamic field names."""
    pattern = re.compile(rf'^{re.escape(prefix)}([0-9]+)$')
    indexes = []
    for key in form_data.keys():
        match = pattern.match(key)
        if match:
            indexes.append(int(match.group(1)))
    return sorted(set(indexes))


def _active_suppliers(module_code: str = 'production') -> list[User]:
    """Return active supplier users for one operational module."""
    return AICatsAccessService.eligible_users('supplier', module_code)


def _active_research_reviewers() -> list[User]:
    """Return active reviewer users for the research module."""
    return AICatsAccessService.eligible_users('research_reviewer', 'research')


def _active_assembly_reviewers() -> list[User]:
    """Return active inspector/reviewer candidates for the assembly module."""
    return _active_suppliers('assembly')


def _can_sign_research_acceptance_as(user: User, batch, signer_role: str) -> bool:
    """Return whether the current user should see one research acceptance button."""
    if signer_role not in ['researcher', 'reviewer']:
        return False
    if batch.signatures_by_role.get(signer_role):
        return False
    return ResearchService.can_accept_batch(user, batch, signer_role=signer_role)


def _current_qc_module() -> str:
    """Return the current AI CATS module key for template rendering."""
    endpoint = request.endpoint or ''
    if endpoint.startswith(ASSEMBLY_ENDPOINT_PREFIX):
        return 'assembly'
    if endpoint.startswith(RESEARCH_ENDPOINT_PREFIX):
        return 'research'
    return 'production'


def _build_qc_nav_context(user) -> dict:
    """Build independent navigation permissions for production, assembly, and research modules."""
    if not user:
        return {
            'production': {
                'workpieces': False,
                'quality_control': False,
                'inspection': False,
                'acceptance': False,
            },
            'assembly': {
                'products': False,
                'workpieces': False,
                'launch': False,
                'inspection': False,
                'acceptance': False,
                'outbound': False,
            },
            'research': {
                'projects': False,
                'batch_launch': False,
                'review': False,
                'acceptance': False,
            },
            'admin': False,
        }

    return {
        'production': {
            'workpieces': QCService.can_access_workpiece_library(user),
            'quality_control': QCService.can_access_quality_control(user),
            'inspection': QCService.can_access_inspection(user),
            'acceptance': QCService.can_access_acceptance(user),
        },
        'assembly': {
            'products': AssemblyService.can_access_product_library(user),
            'workpieces': QCService.can_access_workpiece_library(user),
            'launch': AssemblyService.can_access_assembly_launch(user),
            'inspection': AssemblyService.can_access_inspection(user),
            'acceptance': AssemblyService.can_access_acceptance(user),
            'outbound': AssemblyService.can_access_outbound(user),
        },
        'research': {
            'projects': ResearchService.can_access_project_library(user),
            'batch_launch': ResearchService.can_access_batch_launch(user),
            'review': ResearchService.can_access_review(user),
            'acceptance': ResearchService.can_access_acceptance(user),
        },
        'admin': _is_qc_admin(user),
    }


@qc_bp.app_context_processor
def inject_qc_shell_context() -> dict:
    """Inject independent module-shell context into all AI CATS templates."""
    user = getattr(g, 'current_user', None)
    return {
        'qc_module': _current_qc_module(),
        'qc_nav': _build_qc_nav_context(user),
    }


def _build_guide_items(form_data, files, title_prefix: str = 'guide_title_', content_prefix: str = 'guide_content_', file_prefix: str = 'guide_file_') -> list[dict]:
    """Build guide items from dynamic form inputs."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, title_prefix):
        item = {
            'title': form_data.get(f'{title_prefix}{idx}', '').strip(),
            'content': form_data.get(f'{content_prefix}{idx}', '').strip(),
            'file': files.get(f'{file_prefix}{idx}'),
        }
        if item['title'] or item['content'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_material_items(form_data, files) -> list[dict]:
    """Build outsourced quality-material items from dynamic form inputs."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, 'material_title_'):
        item = {
            'title': form_data.get(f'material_title_{idx}', '').strip(),
            'content': form_data.get(f'material_content_{idx}', '').strip(),
            'file': files.get(f'material_file_{idx}'),
        }
        if item['title'] or item['content'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_drawing_items(form_data, files) -> list[dict]:
    """Build self-produced drawing items from dynamic form inputs."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, 'drawing_title_'):
        item = {
            'title': form_data.get(f'drawing_title_{idx}', '').strip(),
            'content': form_data.get(f'drawing_content_{idx}', '').strip(),
            'file': files.get(f'drawing_file_{idx}'),
        }
        if item['title'] or item['content'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_legacy_point_items(form_data, files) -> list[dict]:
    """Build legacy inspection-point items for backward-compatible handlers."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, 'inspection_point_title_'):
        item = {
            'title': form_data.get(f'inspection_point_title_{idx}', '').strip(),
            'content': form_data.get(f'inspection_point_content_{idx}', '').strip(),
            'file': files.get(f'inspection_point_file_{idx}'),
        }
        if item['title'] or item['content'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_remark_items(form_data, files) -> list[dict]:
    """Build remark items from dynamic form inputs."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, 'remark_content_'):
        item = {
            'content': form_data.get(f'remark_content_{idx}', '').strip(),
            'is_required': form_data.get(f'remark_required_{idx}') == '1',
            'file': files.get(f'remark_file_{idx}'),
        }
        if item['content'] or item['is_required'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_research_attachment_items(
    form_data,
    files,
    title_prefix: str,
    content_prefix: str,
    file_prefix: str,
) -> list[dict]:
    """Build one research attachment section from dynamic form inputs."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, title_prefix):
        item = {
            'title': form_data.get(f'{title_prefix}{idx}', '').strip(),
            'content': form_data.get(f'{content_prefix}{idx}', '').strip(),
            'file': files.get(f'{file_prefix}{idx}'),
        }
        if item['title'] or item['content'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_research_attachment_map(form_data, files) -> dict[str, list[dict]]:
    """Build all research project attachment sections from the request payload."""
    return {
        'initiation_material': _build_research_attachment_items(
            form_data, files, 'initiation_title_', 'initiation_content_', 'initiation_file_'
        ),
        'research_material': _build_research_attachment_items(
            form_data, files, 'research_title_', 'research_content_', 'research_file_'
        ),
        'experiment_plan': _build_research_attachment_items(
            form_data, files, 'plan_title_', 'plan_content_', 'plan_file_'
        ),
        'validation_item': _build_research_attachment_items(
            form_data, files, 'validation_title_', 'validation_content_', 'validation_file_'
        ),
        'risk_note': _build_research_attachment_items(
            form_data, files, 'risk_title_', 'risk_content_', 'risk_file_'
        ),
    }


def _build_assembly_component_items(form_data) -> list[dict]:
    """Build BOM component rows for the assembly product form."""
    items = []
    indexes = set(_extract_dynamic_indexes(form_data, 'component_item_id_'))
    indexes.update(_extract_dynamic_indexes(form_data, 'component_workpiece_id_'))
    for idx in sorted(indexes):
        component_type = form_data.get(f'component_item_type_{idx}', '').strip() or 'workpiece'
        item_id = form_data.get(f'component_item_id_{idx}', '').strip()
        workpiece_id = form_data.get(f'component_workpiece_id_{idx}', '').strip()
        product_id = form_data.get(f'component_product_id_{idx}', '').strip()
        if not item_id:
            item_id = product_id if component_type == 'product' else workpiece_id
        quantity_per_unit = form_data.get(f'component_quantity_{idx}', '').strip()
        code = form_data.get(f'component_code_{idx}', '').strip() or form_data.get(f'component_workpiece_code_{idx}', '').strip()
        name = form_data.get(f'component_name_{idx}', '').strip() or form_data.get(f'component_workpiece_name_{idx}', '').strip()
        if item_id or code or name or quantity_per_unit:
            items.append(
                {
                    'component_type': component_type,
                    'item_id': item_id,
                    'workpiece_id': item_id if component_type == 'workpiece' else workpiece_id,
                    'component_product_id': item_id if component_type == 'product' else product_id,
                    'workpiece_code': code,
                    'workpiece_name': name,
                    'quantity_per_unit': quantity_per_unit,
                }
            )
    return items


def _build_assembly_sheet_items(form_data, files) -> list[dict]:
    """Build assembly-sheet rows from dynamic form inputs."""
    items = []
    for idx in _extract_dynamic_indexes(form_data, 'assembly_sheet_title_'):
        item = {
            'title': form_data.get(f'assembly_sheet_title_{idx}', '').strip(),
            'content': form_data.get(f'assembly_sheet_content_{idx}', '').strip(),
            'file': files.get(f'assembly_sheet_file_{idx}'),
        }
        if item['title'] or item['content'] or (item['file'] and item['file'].filename):
            items.append(item)
    return items


def _build_research_review_results(batch, form_data, files) -> list[dict]:
    """Build review payload rows for research attachments."""
    results = []
    for attachment in batch.attachments:
        result = form_data.get(f'result_{attachment.id}', '').strip()
        suggestion = form_data.get(f'suggestion_{attachment.id}', '').strip()
        feedback_file = files.get(f'feedback_file_{attachment.id}')
        has_payload = bool(result or suggestion or (feedback_file and feedback_file.filename))
        if has_payload:
            results.append(
                {
                    'attachment_id': attachment.id,
                    'result': result or 'draft',
                    'suggestion': suggestion or None,
                    'feedback_file': feedback_file,
                }
            )
    return results


def _build_inspection_record_map(work_order: QCWorkOrder) -> dict[int, object]:
    """Build an attachment-to-record mapping for templates."""
    return {record.attachment_id: record for record in work_order.inspection_records}


def _send_docx_text_report(lines: list[str], filename: str):
    """Send a simple Word-compatible .docx report built from text lines."""
    document_bytes = AssemblyService._minimal_docx_bytes('\n'.join(lines))
    return send_file(
        BytesIO(document_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )


def _is_qc_admin(user) -> bool:
    """Return whether the user can access QC admin pages."""
    return AICatsAccessService.is_qc_admin(user)


def _require_qc_access(user):
    """Enforce access to the AI CATS subsystem."""
    if AICatsAccessService.can_enter(user):
        return None

    flash('当前账号尚未绑定 AI CATS 权限，请先登录或申请权限', 'warning')
    return redirect(url_for('auth.qc_login'))


def _require_qc_admin():
    """Enforce QC admin access and redirect when missing."""
    if _is_qc_admin(g.current_user):
        return None
    flash('需要 AI CATS 管理员权限', 'error')
    return redirect(url_for('qc.index'))


def _require_module_scope(user: User, module_code: str):
    """Enforce one AI CATS module scope before rendering its dashboard."""
    if AICatsAccessService.has_scope(user, module_code):
        return None
    flash('当前身份未开通该 AI CATS 模块', 'warning')
    return redirect(url_for('qc.index'))


def _block_workpiece_access(user):
    """Redirect users without workpiece-library access."""
    if QCService.can_access_workpiece_library(user):
        return None

    flash('您没有权限访问工件库模块', 'warning')
    if QCService.can_access_quality_control(user):
        return redirect(url_for('qc.quality_control_list'))
    if QCService.can_access_inspection(user):
        return redirect(url_for('qc.quality_inspection_list'))
    if QCService.can_access_acceptance(user):
        return redirect(url_for('qc.acceptance_list'))
    return redirect(url_for('qc.index'))


def _block_quality_control_for_inspector(user):
    """Redirect users without quality-control access."""
    if QCService.can_access_quality_control(user):
        return None

    flash('当前无权限或条件未满足', 'warning')
    if QCService.can_access_workpiece_library(user):
        return redirect(url_for('qc.workpiece_list'))
    if QCService.can_access_inspection(user):
        return redirect(url_for('qc.quality_inspection_list'))
    if QCService.can_access_acceptance(user):
        return redirect(url_for('qc.acceptance_list'))
    return redirect(url_for('qc.index'))


def _require_qc_inspection_access(user):
    """Redirect users without inspection access."""
    if QCService.can_access_inspection(user):
        return None

    flash('当前无权限或条件未满足', 'warning')
    if QCService.can_access_quality_control(user):
        return redirect(url_for('qc.quality_control_list'))
    if QCService.can_access_acceptance(user):
        return redirect(url_for('qc.acceptance_list'))
    return redirect(url_for('qc.index'))


def _require_qc_acceptance_access(user):
    """Redirect users without acceptance access."""
    if QCService.can_access_acceptance(user):
        return None

    flash('当前无权限或条件未满足', 'warning')
    if QCService.can_access_inspection(user):
        return redirect(url_for('qc.quality_inspection_list'))
    if QCService.can_access_quality_control(user):
        return redirect(url_for('qc.quality_control_list'))
    return redirect(url_for('qc.index'))


def _block_research_project_access(user):
    """Redirect users without research project-library access."""
    if ResearchService.can_access_project_library(user):
        return None

    flash('您没有权限访问研究项目库', 'warning')
    if ResearchService.can_access_batch_launch(user):
        return redirect(url_for('qc.research_batch_list'))
    if ResearchService.can_access_review(user):
        return redirect(url_for('qc.research_review_list'))
    if ResearchService.can_access_acceptance(user):
        return redirect(url_for('qc.research_acceptance_list'))
    return redirect(url_for('qc.research_home'))


def _block_research_batch_access(user):
    """Redirect users without research launch access."""
    if ResearchService.can_access_batch_launch(user):
        return None

    flash('当前无权限或条件未满足', 'warning')
    if ResearchService.can_access_project_library(user):
        return redirect(url_for('qc.research_project_list'))
    if ResearchService.can_access_review(user):
        return redirect(url_for('qc.research_review_list'))
    if ResearchService.can_access_acceptance(user):
        return redirect(url_for('qc.research_acceptance_list'))
    return redirect(url_for('qc.research_home'))


def _block_research_review_access(user):
    """Redirect users without research review access."""
    if ResearchService.can_access_review(user):
        return None

    flash('当前无权限或条件未满足', 'warning')
    if ResearchService.can_access_batch_launch(user):
        return redirect(url_for('qc.research_batch_list'))
    if ResearchService.can_access_acceptance(user):
        return redirect(url_for('qc.research_acceptance_list'))
    return redirect(url_for('qc.research_home'))


def _block_research_acceptance_access(user):
    """Redirect users without research acceptance access."""
    if ResearchService.can_access_acceptance(user):
        return None

    flash('当前无权限或条件未满足', 'warning')
    if ResearchService.can_access_review(user):
        return redirect(url_for('qc.research_review_list'))
    if ResearchService.can_access_batch_launch(user):
        return redirect(url_for('qc.research_batch_list'))
    return redirect(url_for('qc.research_home'))


def _block_assembly_product_access(user):
    """Redirect users without assembly product-library access."""
    if AssemblyService.can_access_product_library(user):
        return None

    flash('您没有权限访问产品库', 'warning')
    if AssemblyService.can_access_assembly_launch(user):
        return redirect(url_for('qc.assembly_launch_list'))
    if AssemblyService.can_access_inspection(user):
        return redirect(url_for('qc.assembly_inspection_list'))
    if AssemblyService.can_access_acceptance(user):
        return redirect(url_for('qc.assembly_acceptance_list'))
    if QCService.can_access_workpiece_library(user):
        return redirect(url_for('qc.workpiece_list'))
    return redirect(url_for('qc.assembly_home'))


def _block_assembly_launch_access(user):
    """Redirect users without assembly launch access."""
    if AssemblyService.can_access_assembly_launch(user):
        return None

    flash('当前无权限或条件未满足', 'warning')
    if AssemblyService.can_access_product_library(user):
        return redirect(url_for('qc.assembly_product_list'))
    if AssemblyService.can_access_inspection(user):
        return redirect(url_for('qc.assembly_inspection_list'))
    if AssemblyService.can_access_acceptance(user):
        return redirect(url_for('qc.assembly_acceptance_list'))
    if QCService.can_access_workpiece_library(user):
        return redirect(url_for('qc.workpiece_list'))
    return redirect(url_for('qc.assembly_home'))


def _block_assembly_inspection_access(user):
    """Redirect users without assembly inspection access."""
    if AssemblyService.can_access_inspection(user):
        return None

    flash('当前无权限或条件未满足', 'warning')
    if AssemblyService.can_access_assembly_launch(user):
        return redirect(url_for('qc.assembly_launch_list'))
    if AssemblyService.can_access_acceptance(user):
        return redirect(url_for('qc.assembly_acceptance_list'))
    if AssemblyService.can_access_product_library(user):
        return redirect(url_for('qc.assembly_product_list'))
    return redirect(url_for('qc.assembly_home'))


def _block_assembly_acceptance_access(user):
    """Redirect users without assembly acceptance access."""
    if AssemblyService.can_access_acceptance(user):
        return None

    flash('您没有权限访问验收模块', 'warning')
    if AssemblyService.can_access_inspection(user):
        return redirect(url_for('qc.assembly_inspection_list'))
    if AssemblyService.can_access_assembly_launch(user):
        return redirect(url_for('qc.assembly_launch_list'))
    if AssemblyService.can_access_product_library(user):
        return redirect(url_for('qc.assembly_product_list'))
    return redirect(url_for('qc.assembly_home'))


def _block_assembly_outbound_access(user):
    """Redirect users without assembly outbound access."""
    if AssemblyService.can_access_outbound(user):
        return None

    flash('您没有权限访问出厂模块', 'warning')
    if AssemblyService.can_access_acceptance(user):
        return redirect(url_for('qc.assembly_acceptance_list'))
    if AssemblyService.can_access_inspection(user):
        return redirect(url_for('qc.assembly_inspection_list'))
    if AssemblyService.can_access_assembly_launch(user):
        return redirect(url_for('qc.assembly_launch_list'))
    if AssemblyService.can_access_product_library(user):
        return redirect(url_for('qc.assembly_product_list'))
    return redirect(url_for('qc.assembly_home'))


@qc_bp.route('/')
@login_required
def index():
    """AI CATS module selector."""
    user = g.current_user
    blocked = _require_qc_access(user)
    if blocked:
        return blocked

    production_enabled = AICatsAccessService.has_scope(user, 'production')
    assembly_enabled = AICatsAccessService.has_scope(user, 'assembly')
    research_enabled = AICatsAccessService.has_scope(user, 'research')
    modules = [
        {
            'title': '配件生产',
            'subtitle': '工件库、质量控制、质量检测、验收模块',
            'description': '承接当前 AI CATS 生产质量追溯流程，管理配件从工件建档到验收闭环。',
            'icon': 'bi-box-seam',
            'tone': 'production',
            'href': url_for('qc.production_home') if production_enabled else None,
            'disabled': not production_enabled,
        },
        {
            'title': '装配/出厂',
            'subtitle': 'Assembly & Release',
            'description': '管理产品库、装配发起、质量检测和最终出厂验收。',
            'icon': 'bi-tools',
            'tone': 'assembly',
            'href': url_for('qc.assembly_home') if assembly_enabled else None,
            'disabled': not assembly_enabled,
        },
        {
            'title': '研究/实验',
            'subtitle': 'Research & Experiment',
            'description': '管理研究项目立项、指导审批、实验验证和共同验收。',
            'icon': 'bi-lightbulb',
            'tone': 'research',
            'href': url_for('qc.research_home') if research_enabled else None,
            'disabled': not research_enabled,
        },
        {
            'title': 'coming soon',
            'subtitle': 'More modules',
            'description': '为未来 AI CATS 扩展模块预留位置。',
            'icon': 'bi-hourglass-split',
            'tone': 'soon',
            'href': None,
            'disabled': True,
        },
    ]

    return render_template('qc/module_select.html', modules=modules, qc_shell='landing')


@qc_bp.route('/production/')
@login_required
def production_home():
    """Production-accessories dashboard."""
    user = g.current_user
    blocked = _require_qc_access(user)
    if blocked:
        return blocked
    blocked = _require_module_scope(user, 'production')
    if blocked:
        return blocked

    stats = QCService.get_dashboard_stats(user)
    recent_orders = QCService.get_recent_work_orders(user, limit=5)
    inspectors = _active_suppliers()

    return render_template(
        'qc/dashboard.html',
        stats=stats,
        recent_orders=recent_orders,
        inspectors=inspectors,
    )


@qc_bp.route('/assembly/')
@login_required
def assembly_home():
    """Assembly and release dashboard."""
    user = g.current_user
    blocked = _require_qc_access(user)
    if blocked:
        return blocked
    blocked = _require_module_scope(user, 'assembly')
    if blocked:
        return blocked

    stats = AssemblyService.get_dashboard_stats(user)
    recent_orders = AssemblyService.get_recent_orders(user, limit=5)

    return render_template(
        'qc/assembly_dashboard.html',
        stats=stats,
        recent_orders=recent_orders,
    )


@qc_bp.route('/research/')
@login_required
def research_home():
    """Research and experiment dashboard."""
    user = g.current_user
    blocked = _require_qc_access(user)
    if blocked:
        return blocked
    blocked = _require_module_scope(user, 'research')
    if blocked:
        return blocked

    return render_template(
        'qc/research_dashboard.html',
        stats=ResearchService.get_dashboard_stats(user),
        recent_batches=ResearchService.get_recent_batches(user, limit=5),
    )


@qc_bp.route('/assembly/products/')
@login_required
def assembly_product_list():
    """Assembly product-library list."""
    user = g.current_user
    blocked = _block_assembly_product_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    product_level = AssemblyService.normalize_product_level(request.args.get('level', 1))
    pagination = AssemblyService.get_product_list(user=user, keyword=keyword or None, page=page, product_level=product_level)
    return render_template(
        'qc/assembly_product_list.html',
        products=pagination.items,
        pagination=pagination,
        keyword=keyword,
        product_level=product_level,
        product_level_display=AssemblyService.product_level_display(product_level),
        product_level_options=[(level, AssemblyService.product_level_display(level)) for level in AssemblyService.PRODUCT_LEVEL_CHOICES],
        can_create_product=AssemblyService.can_create_product(user),
    )


@qc_bp.route('/assembly/launch/')
@login_required
def assembly_launch_list():
    """Assembly launch list."""
    user = g.current_user
    blocked = _block_assembly_launch_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    status = request.args.get('status', '').strip()
    pagination = AssemblyService.get_order_list(
        user=user,
        keyword=keyword or None,
        status=status or None,
        page=page,
    )
    return render_template(
        'qc/assembly_order_list.html',
        orders=pagination.items,
        pagination=pagination,
        keyword=keyword,
        status=status,
        page_title='发起装配',
        page_icon='bi-tools',
        detail_endpoint='qc.assembly_launch_detail',
        new_endpoint='qc.assembly_launch_new',
        back_endpoint='qc.assembly_home',
        empty_text='暂无装配单，点击新增发起装配。',
        can_create_new=AssemblyService.can_create_order(user),
    )


@qc_bp.route('/assembly/inspection/')
@login_required
def assembly_inspection_list():
    """Assembly inspection queue."""
    user = g.current_user
    blocked = _block_assembly_inspection_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    pagination = AssemblyService.get_inspection_list(user=user, keyword=keyword or None, page=page)
    return render_template(
        'qc/assembly_order_list.html',
        orders=pagination.items,
        pagination=pagination,
        keyword=keyword,
        status='',
        page_title='质量检测',
        page_icon='bi-search',
        detail_endpoint='qc.assembly_inspection_detail',
        new_endpoint=None,
        back_endpoint='qc.assembly_home',
        empty_text='暂无待质量检测的装配单。',
        can_create_new=False,
    )


@qc_bp.route('/assembly/acceptance/')
@login_required
def assembly_acceptance_list():
    """Assembly acceptance queue."""
    user = g.current_user
    blocked = _block_assembly_acceptance_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    pagination = AssemblyService.get_acceptance_list(user=user, keyword=keyword or None, page=page)
    return render_template(
        'qc/assembly_order_list.html',
        orders=pagination.items,
        pagination=pagination,
        keyword=keyword,
        status='',
        page_title='验收',
        page_icon='bi-patch-check',
        detail_endpoint='qc.assembly_acceptance_detail',
        new_endpoint=None,
        back_endpoint='qc.assembly_home',
        empty_text='暂无待验收的装配单。',
        can_create_new=False,
    )


@qc_bp.route('/assembly/workpieces/search')
@login_required
def assembly_workpiece_search():
    """Fuzzy-search workpieces for assembly BOM editing."""
    user = g.current_user
    blocked = _block_assembly_product_access(user)
    if blocked:
        return jsonify({'success': False, 'message': '没有权限访问当前内容'}), 403

    keyword = request.args.get('keyword', '').strip()
    results = AssemblyService.search_workpieces(user, keyword)
    return jsonify(
        {
            'success': True,
            'items': [
                {
                    'id': workpiece.id,
                    'workpiece_code': workpiece.workpiece_code,
                    'workpiece_name': workpiece.workpiece_name,
                    'workpiece_type': workpiece.normalized_type,
                    'workpiece_type_display': workpiece.workpiece_type_display,
                    'stock_quantity': float(workpiece.stock_quantity or 0),
                }
                for workpiece in results
            ],
        }
    )


@qc_bp.route('/assembly/components/search')
@login_required
def assembly_component_search():
    """Fuzzy-search selectable workpieces or lower-level products for assembly BOM editing."""
    user = g.current_user
    blocked = _block_assembly_product_access(user)
    if blocked:
        return jsonify({'success': False, 'message': '没有权限访问当前内容'}), 403

    keyword = request.args.get('keyword', '').strip()
    product_level = AssemblyService.normalize_product_level(request.args.get('level', 1))
    return jsonify({'success': True, 'items': AssemblyService.search_components(user, keyword, product_level=product_level)})


@qc_bp.route('/assembly/products/new', methods=['GET', 'POST'])
@login_required
def assembly_product_new():
    """Create a new assembly product template."""
    user = g.current_user
    blocked = _block_assembly_product_access(user)
    if blocked:
        return blocked

    product_level = AssemblyService.normalize_product_level(request.args.get('level', 1))
    component_choices = AssemblyService.get_component_choices(user, product_level=product_level)
    if not AssemblyService.can_create_product(user):
        flash('没有权限新增产品', 'error')
        return redirect(url_for('qc.assembly_product_list'))

    if request.method == 'POST':
        component_items = _build_assembly_component_items(request.form)
        assembly_sheet_items = _build_assembly_sheet_items(request.form, request.files)
        remark_items = _build_remark_items(request.form, request.files)
        coa_template_file = request.files.get('coa_template_file')
        try:
            product = AssemblyService.create_product(
                data={
                    'product_code': request.form.get('product_code', '').strip(),
                    'product_name': request.form.get('product_name', '').strip(),
                    'product_level': product_level,
                },
                creator_id=user.id,
                auto_commit=False,
            )
            AssemblyService.sync_product_components(product.id, component_items, user, auto_commit=False)
            AssemblyService.sync_product_attachments(
                product.id,
                assembly_sheet_items,
                remark_items,
                user,
                coa_template_file=coa_template_file,
                auto_commit=False,
            )
            db.session.commit()
            flash('操作成功', 'success')
            return redirect(url_for('qc.assembly_product_detail', product_id=product.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/assembly_product_form.html',
        component_choices=component_choices,
        workpiece_choices=component_choices['workpieces'],
        component_product_choices=component_choices['products'],
        product_level=product_level,
        product_level_display=AssemblyService.product_level_display(product_level),
        product_level_options=[(level, AssemblyService.product_level_display(level)) for level in AssemblyService.PRODUCT_LEVEL_CHOICES],
    )


@qc_bp.route('/assembly/products/<int:product_id>')
@login_required
def assembly_product_detail(product_id: int):
    """Assembly product detail."""
    user = g.current_user
    blocked = _block_assembly_product_access(user)
    if blocked:
        return blocked

    product = AssemblyService.get_product(product_id, user)
    if not product:
        flash('产品不存在或没有权限查看', 'error')
        return redirect(url_for('qc.assembly_product_list'))

    return render_template(
        'qc/assembly_product_detail.html',
        product=product,
        can_edit_product=AssemblyService.can_edit_product(user, product),
        can_delete_product=AssemblyService.can_delete_product(user, product),
    )


@qc_bp.route('/assembly/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
def assembly_product_edit(product_id: int):
    """Edit an assembly product template."""
    user = g.current_user
    blocked = _block_assembly_product_access(user)
    if blocked:
        return blocked

    product = AssemblyService.get_product(product_id, user)
    if not product:
        flash('产品不存在或没有权限查看', 'error')
        return redirect(url_for('qc.assembly_product_list'))
    product_level = AssemblyService.normalize_product_level(product.product_level)
    component_choices = AssemblyService.get_component_choices(user, product_level=product_level, exclude_product_id=product_id)
    if not AssemblyService.can_edit_product(user, product):
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.assembly_product_detail', product_id=product_id))

    if request.method == 'POST':
        component_items = _build_assembly_component_items(request.form)
        assembly_sheet_items = _build_assembly_sheet_items(request.form, request.files)
        remark_items = _build_remark_items(request.form, request.files)
        coa_template_file = request.files.get('coa_template_file')
        try:
            AssemblyService.update_product(
                product_id=product_id,
                data={
                    'product_code': request.form.get('product_code', '').strip(),
                    'product_name': request.form.get('product_name', '').strip(),
                    'product_level': product_level,
                },
                user=user,
                auto_commit=False,
            )
            AssemblyService.sync_product_components(product_id, component_items, user, auto_commit=False)
            AssemblyService.sync_product_attachments(
                product_id,
                assembly_sheet_items,
                remark_items,
                user,
                coa_template_file=coa_template_file,
                auto_commit=False,
            )
            db.session.commit()
            flash('产品更新成功', 'success')
            return redirect(url_for('qc.assembly_product_detail', product_id=product_id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/assembly_product_form.html',
        product=product,
        is_edit=True,
        component_choices=component_choices,
        workpiece_choices=component_choices['workpieces'],
        component_product_choices=component_choices['products'],
        product_level=product_level,
        product_level_display=AssemblyService.product_level_display(product_level),
        product_level_options=[(level, AssemblyService.product_level_display(level)) for level in AssemblyService.PRODUCT_LEVEL_CHOICES],
    )


@qc_bp.route('/assembly/products/<int:product_id>/delete', methods=['POST'])
@login_required
def assembly_product_delete(product_id: int):
    """Delete an assembly product template."""
    user = g.current_user
    blocked = _block_assembly_product_access(user)
    if blocked:
        return blocked

    try:
        AssemblyService.delete_product(product_id, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.assembly_product_list'))


@qc_bp.route('/assembly/products/<int:product_id>/snapshot')
@login_required
def assembly_product_snapshot(product_id: int):
    """Return assembly product preview data for the order form."""
    user = g.current_user
    product = AssemblyService.get_product(product_id, user)
    if not product:
        return jsonify({'success': False, 'message': '产品不存在或没有权限查看'}), 404
    return jsonify({'success': True, 'product': AssemblyService.serialize_product_preview(product)})


@qc_bp.route('/assembly/launch/new', methods=['GET', 'POST'])
@login_required
def assembly_launch_new():
    """Create a new assembly order."""
    user = g.current_user
    blocked = _block_assembly_launch_access(user)
    if blocked:
        return blocked

    if not AssemblyService.can_create_order(user):
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.assembly_launch_list'))

    products = AssemblyService.get_product_choices(user)
    reviewers = _active_assembly_reviewers()

    if request.method == 'POST':
        action = request.form.get('submit_action', 'draft').strip()
        if action not in ['draft', 'submit']:
            flash('操作失败，请检查后重试', 'error')
            return render_template(
                'qc/assembly_order_form.html',
                products=products,
                reviewers=reviewers,
            )

        strict_submit = action == 'submit'
        product_id = request.form.get('product_id', type=int)
        reviewer_id = request.form.get('inspector_id', type=int) if strict_submit else None
        product = AssemblyService.get_product(product_id, user) if product_id else None

        try:
            if not product:
                raise ValueError('请选择有效产品')
            if strict_submit and not reviewer_id:
                raise ValueError('请选择供应商')

            order = AssemblyService.create_order(
                data={
                    'batch_no': request.form.get('batch_no', '').strip(),
                    'product_id': product.id,
                    'product_name_snapshot': product.product_name,
                    'quantity': request.form.get('quantity', '').strip(),
                },
                controller_id=user.id,
                status='draft' if action == 'draft' else 'assembly_pending',
                allow_partial=(action == 'draft'),
                auto_commit=False,
            )
            AssemblyService.apply_product_to_order(order.id, product.id, user, auto_commit=False)
            AssemblyService.sync_order_section_files(
                order.id,
                request.files.get('registration_note_file'),
                None,
                request.files.get('remark_note_file'),
                user,
                auto_commit=False,
            )
            if strict_submit:
                AssemblyService.submit_assembly(order.id, reviewer_id, user, auto_commit=False)
                db.session.commit()
                flash('操作成功', 'success')
                return redirect(url_for('qc.assembly_inspection_detail', order_id=order.id))

            db.session.commit()
            flash('装配单已保存为草稿，完成后可进入质量检测', 'success')
            return redirect(url_for('qc.assembly_launch_detail', order_id=order.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/assembly_order_form.html',
        products=products,
        reviewers=reviewers,
    )


@qc_bp.route('/assembly/launch/<int:order_id>')
@login_required
def assembly_launch_detail(order_id: int):
    """Assembly launch detail."""
    user = g.current_user
    blocked = _block_assembly_launch_access(user)
    if blocked:
        return blocked

    order = AssemblyService.get_order(order_id, user)
    if not order:
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.assembly_launch_list'))

    reviewers = _active_assembly_reviewers()
    return render_template(
        'qc/assembly_order_detail_qc.html',
        order=order,
        reviewers=reviewers,
        inspection_records_by_attachment=AssemblyService.inspection_record_map(order),
    )


@qc_bp.route('/assembly/launch/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def assembly_launch_edit(order_id: int):
    """Edit an assembly order."""
    user = g.current_user
    blocked = _block_assembly_launch_access(user)
    if blocked:
        return blocked

    order = AssemblyService.get_order(order_id, user)
    if not order:
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.assembly_launch_list'))
    if not AssemblyService.can_edit_order(user, order):
        flash('当前装配单状态不允许编辑', 'error')
        return redirect(url_for('qc.assembly_launch_detail', order_id=order_id))

    products = AssemblyService.get_product_choices(user)
    reviewers = _active_assembly_reviewers()

    if request.method == 'POST':
        try:
            product_id = request.form.get('product_id', type=int)
            previous_product_id = order.product_id
            AssemblyService.update_order(
                order_id=order_id,
                data={
                    'batch_no': request.form.get('batch_no', '').strip(),
                    'product_id': product_id,
                    'product_name_snapshot': request.form.get('product_name_snapshot', '').strip(),
                    'quantity': request.form.get('quantity', '').strip(),
                },
                user=user,
                allow_partial=(order.status == 'draft'),
                auto_commit=False,
            )
            if product_id and previous_product_id != product_id:
                AssemblyService.apply_product_to_order(order_id, product_id, user, auto_commit=False)
            else:
                refreshed_order = AssemblyOrder.query.get(order_id)
                for component in refreshed_order.components:
                    component.total_required_quantity = float(component.quantity_per_unit or 0) * float(refreshed_order.quantity or 0)
                db.session.flush()

            AssemblyService.sync_order_section_files(
                order_id,
                request.files.get('registration_note_file'),
                None,
                request.files.get('remark_note_file'),
                user,
                auto_commit=False,
            )
            db.session.commit()
            flash('操作成功', 'success')
            return redirect(url_for('qc.assembly_launch_detail', order_id=order_id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/assembly_order_form.html',
        order=order,
        products=products,
        reviewers=reviewers,
        is_edit=True,
    )


@qc_bp.route('/assembly/launch/<int:order_id>/delete', methods=['POST'])
@login_required
def assembly_launch_delete(order_id: int):
    """Delete an assembly order."""
    user = g.current_user
    blocked = _block_assembly_launch_access(user)
    if blocked:
        return blocked

    try:
        AssemblyService.delete_order(order_id, user)
        flash('装配单已删除', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.assembly_launch_list'))


@qc_bp.route('/assembly/launch/<int:order_id>/complete', methods=['POST'])
@login_required
def assembly_launch_complete(order_id: int):
    """Complete assembly launch and assign the inspector/reviewer."""
    user = g.current_user
    blocked = _block_assembly_launch_access(user)
    if blocked:
        return blocked

    inspector_id = request.form.get('inspector_id', type=int)
    try:
        AssemblyService.submit_assembly(order_id, inspector_id, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.assembly_launch_detail', order_id=order_id))


@qc_bp.route('/assembly/inspection/<int:order_id>', methods=['GET', 'POST'])
@login_required
def assembly_inspection_detail(order_id: int):
    """Assembly inspection detail."""
    user = g.current_user
    blocked = _block_assembly_inspection_access(user)
    if blocked:
        return blocked

    order = AssemblyService.get_order(order_id, user)
    if not order:
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.assembly_inspection_list'))

    if request.method == 'POST':
        if not AssemblyService.can_inspect_order(user, order):
            flash('没有权限提交质检结果', 'error')
            return redirect(url_for('qc.assembly_inspection_detail', order_id=order_id))

        action = request.form.get('submit_action', 'submit').strip()
        final_submit = action != 'draft'
        try:
            results = []
            for attachment in order.attachments:
                result = request.form.get(f'result_{attachment.id}', '').strip()
                remark = request.form.get(f'remark_{attachment.id}', '').strip()
                report_file = request.files.get(f'report_file_{attachment.id}')
                has_payload = bool(result or remark or (report_file and report_file.filename))
                if final_submit or has_payload:
                    results.append(
                        {
                            'attachment_id': attachment.id,
                            'result': result,
                            'remark': remark or None,
                            'report_file': report_file,
                        }
                    )

            updated_order = AssemblyService.submit_inspection(
                order_id=order_id,
                results=results,
                user=user,
                final_submit=final_submit,
            )

            if not final_submit:
                flash('操作成功', 'success')
                return redirect(url_for('qc.assembly_inspection_detail', order_id=order_id))

            if updated_order.status == 'inspection_completed':
                flash('质检合格，已进入验收模块', 'success')
                return redirect(url_for('qc.assembly_acceptance_detail', order_id=order_id))

            flash('当前无权限或条件未满足', 'warning')
            return redirect(url_for('qc.assembly_launch_detail', order_id=order_id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/assembly_order_detail_inspector.html',
        order=order,
        inspection_records_by_attachment=AssemblyService.inspection_record_map(order),
    )


@qc_bp.route('/assembly/acceptance/<int:order_id>')
@login_required
def assembly_acceptance_detail(order_id: int):
    """Assembly acceptance detail."""
    user = g.current_user
    blocked = _block_assembly_acceptance_access(user)
    if blocked:
        return blocked

    order = AssemblyService.get_order(order_id, user)
    if not order:
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.assembly_acceptance_list'))

    active_acceptance_batch = order.active_acceptance_batch
    signatures = active_acceptance_batch.signatures_by_role if active_acceptance_batch else {}
    can_cancel_signatures = {
        role: AssemblyService.can_cancel_acceptance_signature(user, order, role)
        for role in ['qc_controller', 'qc_inspector']
    }
    eligible_signer_roles = AssemblyService.eligible_acceptance_signer_roles(user, order)
    return render_template(
        'qc/assembly_acceptance_detail.html',
        order=order,
        signatures=signatures,
        acceptance_batches=order.acceptance_batches,
        active_acceptance_batch=active_acceptance_batch,
        can_cancel_signatures=can_cancel_signatures,
        eligible_signer_roles=eligible_signer_roles,
        inspection_records_by_attachment=AssemblyService.inspection_record_map(order),
    )


@qc_bp.route('/assembly/acceptance/<int:order_id>/batch/new', methods=['POST'])
@login_required
def assembly_acceptance_start_batch(order_id: int):
    """Start a new partial assembly acceptance batch."""
    user = g.current_user
    blocked = _block_assembly_acceptance_access(user)
    if blocked:
        return blocked

    try:
        AssemblyService.start_acceptance_batch(order_id, user)
        flash('已发起新的验收批次', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.assembly_acceptance_detail', order_id=order_id))


@qc_bp.route('/assembly/acceptance/<int:order_id>/sign', methods=['POST'])
@login_required
def assembly_acceptance_sign(order_id: int):
    """Assembly acceptance sign action."""
    user = g.current_user
    blocked = _block_assembly_acceptance_access(user)
    if blocked:
        return blocked

    try:
        result = AssemblyService.sign_acceptance(
            order_id,
            user,
            signer_role=request.form.get('signer_role'),
            production_quantity=request.form.get('production_quantity'),
            accepted_quantity=request.form.get('accepted_quantity'),
        )
        flash(result['message'], 'success' if result['completed'] else 'info')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.assembly_acceptance_detail', order_id=order_id))


@qc_bp.route('/assembly/acceptance/<int:order_id>/signature/<signer_role>/cancel', methods=['POST'])
@login_required
def assembly_acceptance_cancel_signature(order_id: int, signer_role: str):
    """Cancel one assembly acceptance signature."""
    user = g.current_user
    blocked = _block_assembly_acceptance_access(user)
    if blocked:
        return blocked

    try:
        AssemblyService.cancel_acceptance_signature(order_id, signer_role, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.assembly_acceptance_detail', order_id=order_id))


@qc_bp.route('/assembly/acceptance/<int:order_id>/rollback', methods=['POST'])
@login_required
def assembly_acceptance_rollback(order_id: int):
    """Rollback assembly acceptance and return the workflow."""
    user = g.current_user
    blocked = _block_assembly_acceptance_access(user)
    if blocked:
        return blocked

    target = request.form.get('target', '').strip()
    reason = request.form.get('reason', '').strip()
    try:
        AssemblyService.rollback_acceptance(order_id, target, reason, user)
        flash('已退回上一流程', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.assembly_acceptance_detail', order_id=order_id))


@qc_bp.route('/assembly/acceptance/<int:order_id>/print')
@login_required
def assembly_acceptance_print(order_id: int):
    """Printable assembly acceptance report."""
    user = g.current_user
    blocked = _block_assembly_acceptance_access(user)
    if blocked:
        return blocked

    order = AssemblyService.get_order(order_id, user)
    if not order:
        flash('装配单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.assembly_acceptance_list'))

    active_acceptance_batch = order.active_acceptance_batch
    signatures = active_acceptance_batch.signatures_by_role if active_acceptance_batch else {}
    return render_template(
        'qc/assembly_acceptance_print.html',
        order=order,
        signatures=signatures,
        inspection_records_by_attachment=AssemblyService.inspection_record_map(order),
        download_url=url_for('qc.assembly_acceptance_print_download', order_id=order.id),
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )


@qc_bp.route('/assembly/acceptance/<int:order_id>/print/download')
@login_required
def assembly_acceptance_print_download(order_id: int):
    """Download the assembly acceptance report as a Word document."""
    user = g.current_user
    blocked = _block_assembly_acceptance_access(user)
    if blocked:
        return blocked

    order = AssemblyService.get_order(order_id, user)
    if not order:
        flash('装配单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.assembly_acceptance_list'))
    records = AssemblyService.inspection_record_map(order)
    lines = [
        '装配验收报告',
        f'批次编号：{order.batch_no}',
        f'产品名称：{order.product_name_snapshot}',
        f'计划装配数量：{float(order.quantity or 0):g}',
        f'实际合格数量：{float(order.actual_delivered_quantity or 0):g}',
        f"验收日期：{order.accepted_at.strftime('%Y-%m-%d') if order.accepted_at else '-'}",
        f'质量控制人：{order.controller.real_name or order.controller.username if order.controller else "-"}',
        f'供应商：{order.inspector.real_name or order.inspector.username if order.inspector else "-"}',
        '',
        '装配结构',
    ]
    for component in order.components:
        lines.append(
            f'{component.workpiece_code_snapshot} / {component.workpiece_name_snapshot}：'
            f'单件用量 {float(component.quantity_per_unit or 0):g}，本批消耗 {float(component.total_required_quantity or 0):g}'
        )
    lines.extend(['', '质检记录明细'])
    for attachment in order.ordered_attachments:
        record = records.get(attachment.id)
        result_text = {'pass': '通过', 'fail': '不通过', 'draft': '草稿'}.get(record.result if record else '', '-')
        lines.append(
            f'{attachment.display_title}：{result_text}；'
            f'报告：{record.report_filename if record and record.report_file_path else "-"}；'
            f'备注：{record.remark or "" if record else ""}'
        )
    lines.extend(['', '签字确认区', '质量控制人签字：', '供应商签字：'])
    return _send_docx_text_report(lines, f'装配验收报告_{order.batch_no}.docx')


@qc_bp.route('/assembly/acceptance/<int:order_id>/coa')
@login_required
def assembly_acceptance_coa_print(order_id: int):
    """Deprecated acceptance COA entry; COA is now printed from outbound batches."""
    blocked = _block_assembly_acceptance_access(g.current_user)
    if blocked:
        return blocked
    flash('COA 报告已移动到出厂模块，请在已完成的出厂批次中打印。', 'info')
    return redirect(url_for('qc.assembly_outbound_list'))


@qc_bp.route('/assembly/outbound/')
@login_required
def assembly_outbound_list():
    """Assembly outbound list."""
    user = g.current_user
    blocked = _block_assembly_outbound_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    pagination = AssemblyService.get_outbound_list(user=user, keyword=keyword or None, page=page)
    return render_template(
        'qc/assembly_outbound_list.html',
        orders=pagination.items,
        pagination=pagination,
        keyword=keyword,
        can_create_new=AssemblyService.can_create_outbound(user),
    )


@qc_bp.route('/assembly/outbound/items/search')
@login_required
def assembly_outbound_item_search():
    """Fuzzy-search outbound selectable items."""
    user = g.current_user
    blocked = _block_assembly_outbound_access(user)
    if blocked:
        return jsonify({'success': False, 'message': '没有权限访问当前内容'}), 403
    keyword = request.args.get('keyword', '').strip()
    return jsonify({'success': True, 'items': AssemblyService.search_outbound_items(user, keyword)})


@qc_bp.route('/assembly/outbound/new', methods=['GET', 'POST'])
@login_required
def assembly_outbound_new():
    """Create a new outbound order."""
    user = g.current_user
    blocked = _block_assembly_outbound_access(user)
    if blocked:
        return blocked
    if request.method == 'POST':
        try:
            item_type = request.form.get('item_type', '').strip()
            item_id = request.form.get('item_id', '').strip()
            if not item_id and request.form.get('item_select'):
                item_type, item_id = (request.form.get('item_select') or ':').split(':', 1)
            order = AssemblyService.create_outbound_order(
                {
                    'outbound_no': request.form.get('outbound_no', '').strip(),
                    'item_type': item_type,
                    'item_id': item_id,
                    'outbound_date': request.form.get('outbound_date', '').strip(),
                    'planned_quantity': request.form.get('planned_quantity', '').strip(),
                },
                initiator=user,
            )
            flash('出厂订单已创建', 'success')
            return redirect(url_for('qc.assembly_outbound_detail', order_id=order.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/assembly_outbound_form.html',
        item_choices=AssemblyService.get_outbound_item_choices(user),
        today=datetime.now().strftime('%Y-%m-%d'),
    )


@qc_bp.route('/assembly/outbound/<int:order_id>')
@login_required
def assembly_outbound_detail(order_id: int):
    """Outbound order detail."""
    user = g.current_user
    blocked = _block_assembly_outbound_access(user)
    if blocked:
        return blocked

    order = AssemblyService.get_outbound_order(order_id, user)
    if not order:
        flash('出厂订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.assembly_outbound_list'))
    active_batch = order.active_batch
    signatures = active_batch.signatures_by_role if active_batch else {}
    return render_template(
        'qc/assembly_outbound_detail.html',
        order=order,
        batches=order.batches,
        active_batch=active_batch,
        signatures=signatures,
        eligible_signer_roles=AssemblyService.eligible_outbound_signer_roles(user, order),
    )


@qc_bp.route('/assembly/outbound/<int:order_id>/batch/new', methods=['POST'])
@login_required
def assembly_outbound_start_batch(order_id: int):
    """Start a new outbound batch."""
    user = g.current_user
    blocked = _block_assembly_outbound_access(user)
    if blocked:
        return blocked
    try:
        AssemblyService.start_outbound_batch(order_id, user)
        flash('已发起新的出厂批次', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.assembly_outbound_detail', order_id=order_id))


@qc_bp.route('/assembly/outbound/<int:order_id>/sign', methods=['POST'])
@login_required
def assembly_outbound_sign(order_id: int):
    """Sign one outbound batch role."""
    user = g.current_user
    blocked = _block_assembly_outbound_access(user)
    if blocked:
        return blocked
    try:
        result = AssemblyService.sign_outbound_batch(
            order_id,
            user,
            signer_role=request.form.get('signer_role'),
            outbound_quantity=request.form.get('outbound_quantity'),
        )
        flash(result['message'], 'success' if result['completed'] else 'info')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.assembly_outbound_detail', order_id=order_id))


@qc_bp.route('/assembly/outbound/<int:order_id>/batch/<int:batch_id>/coa')
@login_required
def assembly_outbound_coa(order_id: int, batch_id: int):
    """Preview a generated COA report for one completed outbound batch."""
    user = g.current_user
    blocked = _block_assembly_outbound_access(user)
    if blocked:
        return blocked
    try:
        payload = AssemblyService.get_outbound_coa_preview(order_id, batch_id, user)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('qc.assembly_outbound_detail', order_id=order_id))
    return render_template(
        'qc/assembly_outbound_coa_print.html',
        order=payload['order'],
        batch=payload['batch'],
        batch_no=payload['batch_no'],
        replacements=payload['replacements'],
        template_lines=payload['template_lines'],
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        download_url=url_for('qc.assembly_outbound_coa_download', order_id=order_id, batch_id=batch_id),
    )


@qc_bp.route('/assembly/outbound/<int:order_id>/batch/<int:batch_id>/coa/download')
@login_required
def assembly_outbound_coa_download(order_id: int, batch_id: int):
    """Download a generated COA Word report for one completed outbound batch."""
    user = g.current_user
    blocked = _block_assembly_outbound_access(user)
    if blocked:
        return blocked
    try:
        document_bytes, filename = AssemblyService.generate_outbound_coa_docx(order_id, batch_id, user)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('qc.assembly_outbound_detail', order_id=order_id))
    return send_file(
        BytesIO(document_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )


@qc_bp.route('/research/projects/')
@login_required
def research_project_list():
    """Research project library list."""
    user = g.current_user
    blocked = _block_research_project_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    pagination = ResearchService.get_project_list(user=user, keyword=keyword or None, page=page)
    return render_template(
        'qc/research_project_list.html',
        projects=pagination.items,
        pagination=pagination,
        keyword=keyword,
        can_create_project=ResearchService.can_create_project(user),
    )


@qc_bp.route('/research/batches/')
@login_required
def research_batch_list():
    """Research initiation list."""
    user = g.current_user
    blocked = _block_research_batch_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    pagination = ResearchService.get_batch_list(
        user=user,
        keyword=keyword or None,
        page=page,
        statuses=['draft', 'research_pending', 'research_submitted', 'returned'],
    )
    return render_template(
        'qc/research_batch_list.html',
        batches=pagination.items,
        pagination=pagination,
        keyword=keyword,
        page_title='研究批次',
        page_icon='bi-flask',
        empty_text='暂无研究批次，可从新建批次开始。',
        detail_endpoint='qc.research_batch_detail',
        new_endpoint='qc.research_batch_new',
        can_create_new=ResearchService.can_create_batch(user),
    )


@qc_bp.route('/research/reviews/')
@login_required
def research_review_list():
    """Research review queue."""
    user = g.current_user
    blocked = _block_research_review_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    pagination = ResearchService.get_batch_list(
        user=user,
        keyword=keyword or None,
        page=page,
        statuses=['research_submitted', 'review_completed'],
    )
    return render_template(
        'qc/research_batch_list.html',
        batches=pagination.items,
        pagination=pagination,
        keyword=keyword,
        page_title='指导审批',
        page_icon='bi-chat-square-text',
        empty_text='暂无待指导审批的研究批次。',
        detail_endpoint='qc.research_review_detail',
        new_endpoint=None,
        can_create_new=False,
    )


@qc_bp.route('/research/acceptance/')
@login_required
def research_acceptance_list():
    """Research acceptance list."""
    user = g.current_user
    blocked = _block_research_acceptance_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    pagination = ResearchService.get_batch_list(
        user=user,
        keyword=keyword or None,
        page=page,
        statuses=['review_completed', 'accepted'],
    )
    return render_template(
        'qc/research_batch_list.html',
        batches=pagination.items,
        pagination=pagination,
        keyword=keyword,
        page_title='共同验收',
        page_icon='bi-patch-check',
        empty_text='暂无待共同验收的研究批次。',
        detail_endpoint='qc.research_acceptance_detail',
        new_endpoint=None,
        can_create_new=False,
    )


@qc_bp.route('/research/projects/new', methods=['GET', 'POST'])
@login_required
def research_project_new():
    """Create a research project template."""
    user = g.current_user
    blocked = _block_research_project_access(user)
    if blocked:
        return blocked

    if not ResearchService.can_create_project(user):
        flash('没有权限创建研究项目', 'error')
        return redirect(url_for('qc.research_project_list'))

    if request.method == 'POST':
        attachment_map = _build_research_attachment_map(request.form, request.files)
        try:
            project = ResearchService.create_project(
                data={
                    'project_code': request.form.get('project_code', '').strip(),
                    'project_name': request.form.get('project_name', '').strip(),
                    'project_category': request.form.get('project_category', '').strip(),
                    'research_direction': request.form.get('research_direction', '').strip(),
                },
                creator_id=user.id,
                auto_commit=False,
            )
            ResearchService.sync_project_attachments(project.id, attachment_map, user)
            flash('操作成功', 'success')
            return redirect(url_for('qc.research_project_detail', project_id=project.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/research_project_form.html',
        category_options=RESEARCH_PROJECT_CATEGORY_OPTIONS,
    )


@qc_bp.route('/research/projects/<int:project_id>')
@login_required
def research_project_detail(project_id: int):
    """Research project detail."""
    user = g.current_user
    blocked = _block_research_project_access(user)
    if blocked:
        return blocked

    project = ResearchService.get_project(project_id, user)
    if not project:
        flash('研究项目不存在或没有权限查看', 'error')
        return redirect(url_for('qc.research_project_list'))

    return render_template(
        'qc/research_project_detail.html',
        project=project,
        can_edit_project=ResearchService.can_edit_project(user, project),
        can_delete_project=ResearchService.can_delete_project(user, project),
    )


@qc_bp.route('/research/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def research_project_edit(project_id: int):
    """Edit a research project template."""
    user = g.current_user
    blocked = _block_research_project_access(user)
    if blocked:
        return blocked

    project = ResearchService.get_project(project_id, user)
    if not project:
        flash('研究项目不存在或没有权限查看', 'error')
        return redirect(url_for('qc.research_project_list'))
    if not ResearchService.can_edit_project(user, project):
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.research_project_detail', project_id=project_id))

    if request.method == 'POST':
        attachment_map = _build_research_attachment_map(request.form, request.files)
        try:
            ResearchService.update_project(
                project_id=project_id,
                data={
                    'project_code': request.form.get('project_code', '').strip(),
                    'project_name': request.form.get('project_name', '').strip(),
                    'project_category': request.form.get('project_category', '').strip(),
                    'research_direction': request.form.get('research_direction', '').strip(),
                },
                user=user,
            )
            ResearchService.sync_project_attachments(project_id, attachment_map, user)
            flash('研究项目更新成功', 'success')
            return redirect(url_for('qc.research_project_detail', project_id=project_id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/research_project_form.html',
        project=project,
        is_edit=True,
        category_options=RESEARCH_PROJECT_CATEGORY_OPTIONS,
    )


@qc_bp.route('/research/projects/<int:project_id>/delete', methods=['POST'])
@login_required
def research_project_delete(project_id: int):
    """Delete a research project template."""
    user = g.current_user
    blocked = _block_research_project_access(user)
    if blocked:
        return blocked

    try:
        ResearchService.delete_project(project_id, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.research_project_list'))


@qc_bp.route('/research/projects/<int:project_id>/snapshot')
@login_required
def research_project_snapshot(project_id: int):
    """Return research project preview data for the batch form."""
    user = g.current_user
    project = ResearchService.get_project(project_id, user)
    if not project:
        return jsonify({'success': False, 'message': '研究项目不存在或没有权限查看'}), 404
    return jsonify({'success': True, 'project': ResearchService.serialize_project_preview(project)})


@qc_bp.route('/research/batches/new', methods=['GET', 'POST'])
@login_required
def research_batch_new():
    """Create a new research batch."""
    user = g.current_user
    blocked = _block_research_batch_access(user)
    if blocked:
        return blocked

    if not ResearchService.can_create_batch(user):
        flash('没有权限发起研究批次', 'error')
        return redirect(url_for('qc.research_batch_list'))

    projects = ResearchService.get_project_choices(user)
    reviewers = _active_research_reviewers()

    if request.method == 'POST':
        action = request.form.get('submit_action', 'draft').strip()
        if action not in ['draft', 'submit']:
            flash('操作失败，请检查后重试', 'error')
            return render_template(
                'qc/research_batch_form.html',
                projects=projects,
                reviewers=reviewers,
                category_options=RESEARCH_PROJECT_CATEGORY_OPTIONS,
            )

        strict_submit = action == 'submit'
        project_id = request.form.get('project_id', type=int)
        reviewer_id = request.form.get('reviewer_id', type=int)
        project = ResearchService.get_project(project_id, user) if project_id else None

        try:
            if not project:
                raise ValueError('提交数据无效，请检查后重试')
            if strict_submit and not reviewer_id:
                raise ValueError('请选择指导/验收人员')

            batch = ResearchService.create_batch(
                data={
                    'batch_no': request.form.get('batch_no', '').strip(),
                    'project_id': project.id,
                    'project_name_snapshot': project.project_name,
                    'sample_quantity': request.form.get('sample_quantity', '').strip(),
                    'reviewer_id': reviewer_id,
                },
                researcher_id=user.id,
                status='draft',
                allow_partial=not strict_submit,
                auto_commit=False,
            )
            ResearchService.apply_project_to_batch(batch.id, project.id, user)
            ResearchService.sync_batch_section_files(
                batch.id,
                request.files.get('initiation_note_file'),
                request.files.get('phase_result_file'),
                request.files.get('supplementary_note_file'),
                user,
            )
            ResearchService.add_batch_history(
                batch,
                '保存研究批次',
                '保存研究批次草稿' if not strict_submit else '提交研究批次至指导审批',
                user,
            )
            db.session.commit()

            if strict_submit:
                ResearchService.submit_batch_for_review(batch.id, reviewer_id, user)
                flash('操作成功', 'success')
            else:
                flash('操作成功', 'success')
            return redirect(url_for('qc.research_batch_detail', batch_id=batch.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/research_batch_form.html',
        projects=projects,
        reviewers=reviewers,
        category_options=RESEARCH_PROJECT_CATEGORY_OPTIONS,
    )


@qc_bp.route('/research/batches/<int:batch_id>')
@login_required
def research_batch_detail(batch_id: int):
    """Research batch detail."""
    user = g.current_user
    blocked = _block_research_batch_access(user)
    if blocked:
        return blocked

    batch = ResearchService.get_batch(batch_id, user)
    if not batch:
        flash('研究批次不存在或没有权限查看', 'error')
        return redirect(url_for('qc.research_batch_list'))

    return render_template(
        'qc/research_batch_detail.html',
        batch=batch,
        review_records_by_attachment=ResearchService.review_record_map(batch),
        can_edit_batch=ResearchService.can_edit_batch(user, batch),
    )


@qc_bp.route('/research/batches/<int:batch_id>/edit', methods=['GET', 'POST'])
@login_required
def research_batch_edit(batch_id: int):
    """Edit a research batch."""
    user = g.current_user
    blocked = _block_research_batch_access(user)
    if blocked:
        return blocked

    batch = ResearchService.get_batch(batch_id, user)
    if not batch:
        flash('研究批次不存在或没有权限查看', 'error')
        return redirect(url_for('qc.research_batch_list'))
    if not ResearchService.can_edit_batch(user, batch):
        flash('当前研究批次状态不允许编辑', 'error')
        return redirect(url_for('qc.research_batch_detail', batch_id=batch_id))

    projects = ResearchService.get_project_choices(user)
    reviewers = _active_research_reviewers()

    if request.method == 'POST':
        action = request.form.get('submit_action', 'draft').strip()
        if action not in ['draft', 'submit']:
            flash('操作失败，请检查后重试', 'error')
            return render_template(
                'qc/research_batch_form.html',
                batch=batch,
                is_edit=True,
                projects=projects,
                reviewers=reviewers,
                category_options=RESEARCH_PROJECT_CATEGORY_OPTIONS,
            )

        strict_submit = action == 'submit'
        project_id = request.form.get('project_id', type=int)
        reviewer_id = request.form.get('reviewer_id', type=int)
        previous_project_id = batch.project_id
        had_attachments = bool(batch.attachments)
        project = ResearchService.get_project(project_id, user) if project_id else None

        try:
            if not project:
                raise ValueError('提交数据无效，请检查后重试')
            if strict_submit and not reviewer_id:
                raise ValueError('请选择指导/验收人员')

            ResearchService.update_batch(
                batch_id=batch_id,
                data={
                    'batch_no': request.form.get('batch_no', '').strip(),
                    'project_id': project.id,
                    'project_name_snapshot': project.project_name,
                    'sample_quantity': request.form.get('sample_quantity', '').strip(),
                    'reviewer_id': reviewer_id,
                },
                user=user,
                allow_partial=not strict_submit,
            )

            if previous_project_id != project.id or not had_attachments:
                ResearchService.apply_project_to_batch(batch_id, project.id, user)

            ResearchService.sync_batch_section_files(
                batch_id,
                request.files.get('initiation_note_file'),
                request.files.get('phase_result_file'),
                request.files.get('supplementary_note_file'),
                user,
            )

            batch = ResearchService.get_batch(batch_id, user)
            if strict_submit:
                ResearchService.submit_batch_for_review(batch_id, reviewer_id, user)
                flash('操作成功', 'success')
            else:
                ResearchService.add_batch_history(batch, '编辑研究批次', '已更新研究批次基础信息和材料', user)
                db.session.flush()
                flash('操作成功', 'success')

            return redirect(url_for('qc.research_batch_detail', batch_id=batch_id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/research_batch_form.html',
        batch=batch,
        is_edit=True,
        projects=projects,
        reviewers=reviewers,
        category_options=RESEARCH_PROJECT_CATEGORY_OPTIONS,
    )


@qc_bp.route('/research/batches/<int:batch_id>/delete', methods=['POST'])
@login_required
def research_batch_delete(batch_id: int):
    """Delete a research batch."""
    user = g.current_user
    blocked = _block_research_batch_access(user)
    if blocked:
        return blocked

    try:
        ResearchService.delete_batch(batch_id, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.research_batch_list'))


@qc_bp.route('/research/reviews/<int:batch_id>', methods=['GET', 'POST'])
@login_required
def research_review_detail(batch_id: int):
    """Research review detail."""
    user = g.current_user
    blocked = _block_research_review_access(user)
    if blocked:
        return blocked

    batch = ResearchService.get_batch(batch_id, user)
    if not batch:
        flash('研究批次不存在或没有权限查看', 'error')
        return redirect(url_for('qc.research_review_list'))

    if request.method == 'POST':
        if not ResearchService.can_review_batch(user, batch):
            flash('没有权限提交指导审批结果', 'error')
            return redirect(url_for('qc.research_review_detail', batch_id=batch_id))

        action = request.form.get('submit_action', 'submit').strip()
        final_submit = action != 'draft'
        try:
            updated_batch = ResearchService.submit_review(
                batch_id=batch_id,
                results=_build_research_review_results(batch, request.form, request.files),
                user=user,
                final_submit=final_submit,
            )
            if not final_submit:
                flash('操作成功', 'success')
                return redirect(url_for('qc.research_review_detail', batch_id=batch_id))

            if updated_batch.status == 'review_completed':
                flash('操作成功', 'success')
                return redirect(url_for('qc.research_acceptance_detail', batch_id=batch_id))

            flash('当前无权限或条件未满足', 'warning')
            if ResearchService.can_access_batch_launch(user):
                return redirect(url_for('qc.research_batch_detail', batch_id=batch_id))
            return redirect(url_for('qc.research_review_list'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/research_review_detail.html',
        batch=batch,
        review_records_by_attachment=ResearchService.review_record_map(batch),
        can_review_batch=ResearchService.can_review_batch(user, batch),
    )


@qc_bp.route('/research/acceptance/<int:batch_id>')
@login_required
def research_acceptance_detail(batch_id: int):
    """Research acceptance detail."""
    user = g.current_user
    blocked = _block_research_acceptance_access(user)
    if blocked:
        return blocked

    batch = ResearchService.get_batch(batch_id, user)
    if not batch:
        flash('研究批次不存在或没有权限查看', 'error')
        return redirect(url_for('qc.research_acceptance_list'))

    signatures = batch.signatures_by_role
    can_accept_batch = ResearchService.can_accept_batch(user, batch)
    can_rollback_batch = ResearchService.can_rollback_batch(user, batch)
    can_sign_as_researcher = _can_sign_research_acceptance_as(user, batch, 'researcher')
    can_sign_as_reviewer = _can_sign_research_acceptance_as(user, batch, 'reviewer')
    can_cancel_signatures = {
        signer_role: bool(signatures.get(signer_role)) and ResearchService.can_cancel_acceptance_signature(
            user,
            batch,
            signer_role,
        )
        for signer_role in ['researcher', 'reviewer']
    }

    return render_template(
        'qc/research_acceptance_detail.html',
        batch=batch,
        signatures=signatures,
        can_cancel_signatures=can_cancel_signatures,
        review_records_by_attachment=ResearchService.review_record_map(batch),
        can_accept_batch=can_accept_batch,
        can_rollback_batch=can_rollback_batch,
        can_sign_as_researcher=can_sign_as_researcher,
        can_sign_as_reviewer=can_sign_as_reviewer,
    )


@qc_bp.route('/research/acceptance/<int:batch_id>/sign', methods=['POST'])
@login_required
def research_acceptance_sign(batch_id: int):
    """Submit a research acceptance signature."""
    user = g.current_user
    blocked = _block_research_acceptance_access(user)
    if blocked:
        return blocked

    signer_role = request.form.get('signer_role', '').strip() or None
    try:
        result = ResearchService.sign_acceptance(batch_id, user, signer_role=signer_role)
        flash(result['message'], 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.research_acceptance_detail', batch_id=batch_id))


@qc_bp.route('/research/acceptance/<int:batch_id>/cancel-signature/<signer_role>', methods=['POST'])
@login_required
def research_acceptance_cancel_signature(batch_id: int, signer_role: str):
    """Cancel one research acceptance signature."""
    user = g.current_user
    blocked = _block_research_acceptance_access(user)
    if blocked:
        return blocked

    try:
        ResearchService.cancel_acceptance_signature(batch_id, signer_role, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.research_acceptance_detail', batch_id=batch_id))


@qc_bp.route('/research/acceptance/<int:batch_id>/rollback', methods=['POST'])
@login_required
def research_acceptance_rollback(batch_id: int):
    """Roll a research batch back from acceptance."""
    user = g.current_user
    blocked = _block_research_acceptance_access(user)
    if blocked:
        return blocked

    target = request.form.get('target', '').strip()
    reason = request.form.get('reason', '').strip()

    try:
        ResearchService.rollback_batch(batch_id, target, reason, user)
        flash('研究批次已退回', 'success')
        if target == 'research':
            return redirect(url_for('qc.research_batch_detail', batch_id=batch_id))
        return redirect(url_for('qc.research_review_detail', batch_id=batch_id))
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.research_acceptance_detail', batch_id=batch_id))


# ==================== QC 绯荤粺绠＄悊 ====================

QC_ADMIN_MANAGED_ROLE_CODES = ('superadmin',) + QC_ADMIN_ROLE_CODES


@qc_bp.route('/admin/users')
@login_required
def qc_admin_users():
    """QC admin: user list."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    role_code = request.args.get('role', '').strip()
    status = request.args.get('status', '').strip()
    keyword = request.args.get('keyword', '').strip()

    identity_user_ids = AICatsUserIdentity.query.with_entities(
        AICatsUserIdentity.user_id
    )
    profile_user_ids = AICatsAccountProfile.query.with_entities(
        AICatsAccountProfile.user_id
    )
    query = User.query.join(Role).filter(
        or_(
            Role.code.in_(QC_ADMIN_MANAGED_ROLE_CODES),
            User.id.in_(identity_user_ids),
            User.id.in_(profile_user_ids),
        )
    )

    if role_code:
        if role_code in AI_CATS_IDENTITY_DEFINITIONS:
            matching_user_ids = AICatsUserIdentity.query.filter_by(
                identity_code=role_code,
            ).with_entities(AICatsUserIdentity.user_id)
            query = query.filter(User.id.in_(matching_user_ids))
        else:
            query = query.filter(Role.code == role_code)
    if status == 'active':
        disabled_profile_ids = AICatsAccountProfile.query.filter_by(
            is_enabled=False,
        ).with_entities(AICatsAccountProfile.user_id)
        query = query.filter(
            User.is_active.is_(True),
            ~User.id.in_(disabled_profile_ids),
        )
    elif status == 'inactive':
        disabled_profile_ids = AICatsAccountProfile.query.filter_by(
            is_enabled=False,
        ).with_entities(AICatsAccountProfile.user_id)
        query = query.filter(
            or_(User.is_active.is_(False), User.id.in_(disabled_profile_ids))
        )
    if keyword:
        like_keyword = f'%{keyword}%'
        query = query.filter(
            or_(
                User.username.ilike(like_keyword),
                User.real_name.ilike(like_keyword),
                User.email.ilike(like_keyword),
            )
        )

    pagination = query.order_by(User.created_at.desc()).distinct().paginate(
        page=page,
        per_page=20,
        error_out=False,
    )
    users = pagination.items
    user_ids = [user.id for user in users]
    identities = (
        AICatsUserIdentity.query.filter(AICatsUserIdentity.user_id.in_(user_ids))
        .order_by(AICatsUserIdentity.user_id.asc(), AICatsUserIdentity.id.asc())
        .all()
        if user_ids else []
    )
    identity_map: dict[int, list[AICatsUserIdentity]] = {}
    for identity in identities:
        identity_map.setdefault(identity.user_id, []).append(identity)
    profile_map = {
        profile.user_id: profile
        for profile in AICatsAccountProfile.query.filter(
            AICatsAccountProfile.user_id.in_(user_ids)
        ).all()
    } if user_ids else {}
    roles = Role.query.filter(Role.code.in_(QC_MANAGER_ROLE_CODES)).order_by(Role.level.desc()).all()
    return render_template(
        'qc/admin_users.html',
        users=users,
        pagination=pagination,
        roles=roles,
        identity_definitions=AI_CATS_IDENTITY_DEFINITIONS,
        identity_map=identity_map,
        profile_map=profile_map,
        role=role_code,
        status=status,
        keyword=keyword,
    )


@qc_bp.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@login_required
def qc_admin_toggle_user(user_id: int):
    """QC admin: toggle AI CATS access without affecting shared ERP access."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    user = UserService.get_user_by_id(user_id, include_qc=True)
    if not user:
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.qc_admin_users'))
    if user.is_superadmin or user.id == g.current_user.id:
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.qc_admin_users'))

    profile = AICatsAccessService.get_profile(user)
    currently_enabled = profile.is_enabled if profile else AICatsAccessService.can_enter(user)
    try:
        AICatsAccessService.set_account_enabled(
            user,
            not currently_enabled,
            g.current_user,
        )
        db.session.commit()
        flash(f'用户 {user.username} 的 AI CATS 状态已更新', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('qc.qc_admin_users'))


@qc_bp.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
def qc_admin_reset_password(user_id: int):
    """QC admin: reset user password."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    user = UserService.get_user_by_id(user_id, include_qc=True)
    if not user:
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.qc_admin_users'))

    AuthService.reset_password(user)
    flash(f'已重置 {user.username} 的密码', 'success')
    return redirect(url_for('qc.qc_admin_users'))


@qc_bp.route('/admin/pending')
@login_required
def qc_admin_pending():
    """QC admin: pending approvals."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    pending_qc_users = User.query.join(Role).filter(
        Role.code.in_(['qc_controller', 'qc_inspector']),
        User.is_active.is_(False),
        User.approved_at.is_(None),
    ).order_by(User.created_at.asc()).all()

    pending_qc_bindings = QCUserBinding.query.filter_by(is_active=False).order_by(
        QCUserBinding.created_at.asc()
    ).all()
    pending_identities = AICatsUserIdentity.query.filter_by(status='pending').order_by(
        AICatsUserIdentity.requested_at.asc(),
        AICatsUserIdentity.id.asc(),
    ).all()
    pending_user_ids = {identity.user_id for identity in pending_identities}
    pending_profiles = {
        profile.user_id: profile
        for profile in AICatsAccountProfile.query.filter(
            AICatsAccountProfile.user_id.in_(pending_user_ids)
        ).all()
    } if pending_user_ids else {}

    return render_template(
        'qc/admin_pending.html',
        pending_qc_users=pending_qc_users,
        pending_qc_bindings=pending_qc_bindings,
        pending_identities=pending_identities,
        pending_profiles=pending_profiles,
    )


@qc_bp.route('/admin/identities/<int:identity_id>/<action>', methods=['POST'])
@login_required
def qc_admin_identity_action(identity_id: int, action: str):
    """Approve, reject, revoke, or restore one AI CATS identity."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    identity = AICatsUserIdentity.query.get_or_404(identity_id)
    status_by_action = {
        'approve': 'active',
        'reject': 'rejected',
        'revoke': 'revoked',
        'restore': 'active',
    }
    target_status = status_by_action.get(action)
    if not target_status:
        flash('无效的身份管理操作', 'error')
        return redirect(url_for('qc.qc_admin_users'))

    allowed_source_statuses = {
        'approve': {'pending'},
        'reject': {'pending'},
        'revoke': {'active'},
        'restore': {'rejected', 'revoked'},
    }
    if identity.status not in allowed_source_statuses[action]:
        flash('当前身份状态不允许执行此操作', 'error')
        return redirect(url_for('qc.qc_admin_user_detail', user_id=identity.user_id))

    try:
        if action == 'revoke':
            AICatsAccessService.assert_identity_change_safe(identity)
        AICatsAccessService.set_identity_status(
            identity,
            target_status,
            g.current_user,
            reason=request.form.get('reason'),
        )
        db.session.commit()
        flash(f'{identity.user.username} 的“{identity.display_name}”身份已更新', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')

    next_url = request.form.get('next', '').strip()
    if not next_url.startswith('/') or next_url.startswith('//'):
        next_url = url_for('qc.qc_admin_pending')
    return redirect(next_url)


@qc_bp.route('/admin/users/<int:user_id>')
@login_required
def qc_admin_user_detail(user_id: int):
    """Display one user's AI CATS identities, scopes, and audit trail."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked
    user = User.query.get_or_404(user_id)
    identities = AICatsUserIdentity.query.filter_by(user_id=user.id).order_by(
        AICatsUserIdentity.id.asc()
    ).all()
    audits = AICatsIdentityAuditLog.query.filter_by(target_user_id=user.id).order_by(
        AICatsIdentityAuditLog.created_at.desc(),
        AICatsIdentityAuditLog.id.desc(),
    ).limit(100).all()
    return render_template(
        'qc/admin_user_detail.html',
        user=user,
        profile=AICatsAccessService.get_profile(user),
        identities=identities,
        audits=audits,
        identity_definitions=AI_CATS_IDENTITY_DEFINITIONS,
    )


@qc_bp.route('/admin/users/<int:user_id>/identity/add', methods=['POST'])
@login_required
def qc_admin_add_identity(user_id: int):
    """Assign one additional AI CATS identity immediately."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked
    user = User.query.get_or_404(user_id)
    identity_code = request.form.get('identity_code', '').strip()
    try:
        identity = AICatsAccessService.request_identities(
            user,
            [identity_code],
            source='admin',
            status='pending',
        )[0]
        AICatsAccessService.set_identity_status(identity, 'active', g.current_user)
        db.session.commit()
        flash(f'已为 {user.username} 添加“{identity.display_name}”身份', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('qc.qc_admin_user_detail', user_id=user.id))


@qc_bp.route('/admin/identities/<int:identity_id>/scope/<module_code>', methods=['POST'])
@login_required
def qc_admin_toggle_identity_scope(identity_id: int, module_code: str):
    """Toggle one valid module scope for an AI CATS identity."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked
    identity = AICatsUserIdentity.query.get_or_404(identity_id)
    is_enabled = request.form.get('is_enabled') == '1'
    try:
        if not is_enabled:
            AICatsAccessService.assert_identity_change_safe(identity, module_code)
        AICatsAccessService.set_scope_enabled(
            identity,
            module_code,
            is_enabled,
            g.current_user,
        )
        db.session.commit()
        flash('模块权限范围已更新', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('qc.qc_admin_user_detail', user_id=identity.user_id))


@qc_bp.route('/admin/pending/user/<int:user_id>/approve', methods=['POST'])
@login_required
def qc_admin_approve_user(user_id: int):
    """QC admin: approve QC user."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    user = UserService.get_user_by_id(user_id, include_qc=True)
    if not user:
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.qc_admin_pending'))

    AuthService.approve_user(user, g.current_user)
    flash(f'用户 {user.username} 审核通过', 'success')
    return redirect(url_for('qc.qc_admin_pending'))


@qc_bp.route('/admin/pending/user/<int:user_id>/reject', methods=['POST'])
@login_required
def qc_admin_reject_user(user_id: int):
    """QC admin: reject QC user."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    user = UserService.get_user_by_id(user_id, include_qc=True)
    if not user:
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.qc_admin_pending'))

    AuthService.reject_user(user)
    flash(f'已拒绝用户 {user.username} 的注册申请', 'success')
    return redirect(url_for('qc.qc_admin_pending'))


@qc_bp.route('/admin/pending/binding/<int:binding_id>/approve', methods=['POST'])
@login_required
def qc_admin_approve_binding(binding_id: int):
    """QC admin: approve ERP user QC binding."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    binding = QCUserBinding.query.get_or_404(binding_id)
    now = datetime.now()
    binding.is_active = True
    binding.approved_by = g.current_user.id
    binding.approved_at = now

    if not binding.user.is_active:
        binding.user.is_active = True
        binding.user.approved_by = g.current_user.id
        binding.user.approved_at = now

    AICatsAccessService.ensure_profile(binding.user, 'shared', is_enabled=True)
    for identity_code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP.get(binding.role.code, ()):
        identity = AICatsUserIdentity.query.filter_by(
            user_id=binding.user_id,
            identity_code=identity_code,
        ).first()
        if not identity:
            identity = AICatsAccessService.request_identities(
                binding.user,
                [identity_code],
                source='legacy_binding',
                status='pending',
            )[0]
        AICatsAccessService.set_identity_status(identity, 'active', g.current_user)

    db.session.commit()
    flash(f'已通过 {binding.user.username} 的 AI CATS 绑定申请', 'success')
    return redirect(url_for('qc.qc_admin_pending'))


@qc_bp.route('/admin/pending/binding/<int:binding_id>/reject', methods=['POST'])
@login_required
def qc_admin_reject_binding(binding_id: int):
    """QC admin: reject ERP user QC binding."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    binding = QCUserBinding.query.get_or_404(binding_id)
    username = binding.user.username
    user = binding.user
    if not user.is_active and user.role.code in QC_ROLE_CODES:
        AuthService.reject_user(user)
        flash(f'已拒绝 {username} 的 AI CATS 账号申请', 'success')
        return redirect(url_for('qc.qc_admin_pending'))

    for identity_code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP.get(binding.role.code, ()):
        identity = AICatsUserIdentity.query.filter_by(
            user_id=binding.user_id,
            identity_code=identity_code,
            status='pending',
        ).first()
        if identity:
            AICatsAccessService.set_identity_status(
                identity,
                'rejected',
                g.current_user,
                reason='旧版绑定申请被拒绝',
            )
    db.session.delete(binding)
    db.session.commit()
    flash(f'已拒绝 {username} 的 AI CATS 绑定申请', 'success')
    return redirect(url_for('qc.qc_admin_pending'))


@qc_bp.route('/admin/roles')
@login_required
def qc_admin_roles():
    """QC admin: role permissions overview."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    roles = Role.query.filter(Role.code.in_(QC_ADMIN_MANAGED_ROLE_CODES)).order_by(Role.level.desc()).all()
    import json

    permission_counts = {}
    for role in roles:
        if role.code == 'superadmin':
            permission_counts[role.id] = -1
            continue
        try:
            permission_counts[role.id] = len(json.loads(role.permissions or '[]'))
        except Exception:
            permission_counts[role.id] = 0
    return render_template('qc/admin_roles.html', roles=roles, permission_counts=permission_counts)


@qc_bp.route('/admin/roles/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
def qc_admin_edit_role(role_id: int):
    """QC admin: edit role permissions."""
    blocked = _require_qc_admin()
    if blocked:
        return blocked

    role = Role.query.get_or_404(role_id)
    if role.code not in QC_ADMIN_MANAGED_ROLE_CODES:
        flash('该角色不属于 AI CATS 历史兼容管理范围', 'error')
        return redirect(url_for('qc.qc_admin_roles'))
    if role.code == 'superadmin':
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.qc_admin_roles'))

    if request.method == 'POST':
        selected_permissions = request.form.getlist('permissions')
        success, message = UserService.update_role_permissions(role_id, selected_permissions, scope='qc')
        flash(message, 'success' if success else 'error')
        if success:
            return redirect(url_for('qc.qc_admin_roles'))

    import json

    try:
        current_permissions = json.loads(role.permissions or '[]')
    except Exception:
        current_permissions = []
    return render_template(
        'qc/admin_role_edit.html',
        role=role,
        permissions=QC_ROLE_EDITABLE_PERMISSIONS.get(role.code, {}),
        current_permissions=current_permissions,
    )


# ==================== 工件库模块 ====================

@qc_bp.route('/workpieces/')
@login_required
def workpiece_list():
    """Workpiece-library list."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '').strip()
    pagination = QCService.get_workpiece_list(user=user, keyword=keyword or None, page=page)
    return render_template(
        'qc/workpiece_list.html',
        workpieces=pagination.items,
        pagination=pagination,
        keyword=keyword,
    )


@qc_bp.route('/workpieces/new', methods=['GET', 'POST'])
@login_required
def workpiece_new():
    """Create a new workpiece."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    if not QCService.can_create_workpiece(user):
        flash('没有权限新增工件', 'error')
        return redirect(url_for('qc.workpiece_list'))

    if request.method == 'POST':
        guide_items = _build_guide_items(request.form, request.files)
        drawing_items = _build_drawing_items(request.form, request.files)
        material_items = _build_material_items(request.form, request.files)
        remark_items = _build_remark_items(request.form, request.files)
        drawing_file = request.files.get('drawing')
        coa_template_file = request.files.get('coa_template_file')

        try:
            workpiece = QCService.create_workpiece(
                data={
                    'workpiece_code': request.form.get('workpiece_code', '').strip(),
                    'workpiece_name': request.form.get('workpiece_name', '').strip(),
                    'workpiece_type': request.form.get('workpiece_type', '').strip(),
                },
                creator_id=user.id,
                auto_commit=False,
            )
            QCService.sync_workpiece_attachments(
                workpiece_id=workpiece.id,
                guide_items=guide_items,
                remark_items=remark_items,
                drawing_file=drawing_file,
                user=user,
                material_items=material_items,
                drawing_items=drawing_items,
                coa_template_file=coa_template_file,
            )
            flash('操作成功', 'success')
            return redirect(url_for('qc.workpiece_detail', workpiece_id=workpiece.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template('qc/workpiece_form.html', workpiece_types=QC_WORKPIECE_TYPE_DISPLAY)


@qc_bp.route('/workpieces/<int:workpiece_id>')
@login_required
def workpiece_detail(workpiece_id: int):
    """Workpiece detail."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    workpiece = QCService.get_workpiece(workpiece_id, user)
    if not workpiece:
        flash('工件不存在或没有权限查看', 'error')
        return redirect(url_for('qc.workpiece_list'))

    return render_template('qc/workpiece_detail.html', workpiece=workpiece)


@qc_bp.route('/workpieces/<int:workpiece_id>/edit', methods=['GET', 'POST'])
@login_required
def workpiece_edit(workpiece_id: int):
    """Edit a workpiece."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    workpiece = QCService.get_workpiece(workpiece_id, user)
    if not workpiece:
        flash('工件不存在或没有权限查看', 'error')
        return redirect(url_for('qc.workpiece_list'))
    if not QCService.can_edit_workpiece(user, workpiece):
        flash('操作失败，请检查后重试', 'error')
        return redirect(url_for('qc.workpiece_detail', workpiece_id=workpiece_id))

    if request.method == 'POST':
        guide_items = _build_guide_items(request.form, request.files)
        drawing_items = _build_drawing_items(request.form, request.files)
        material_items = _build_material_items(request.form, request.files)
        remark_items = _build_remark_items(request.form, request.files)
        drawing_file = request.files.get('drawing')
        coa_template_file = request.files.get('coa_template_file')
        try:
            QCService.update_workpiece(
                workpiece_id=workpiece_id,
                data={
                    'workpiece_code': request.form.get('workpiece_code', '').strip(),
                    'workpiece_name': request.form.get('workpiece_name', '').strip(),
                    'workpiece_type': request.form.get('workpiece_type', '').strip(),
                },
                user=user,
            )
            QCService.sync_workpiece_attachments(
                workpiece_id=workpiece_id,
                guide_items=guide_items,
                remark_items=remark_items,
                drawing_file=drawing_file,
                user=user,
                material_items=material_items,
                drawing_items=drawing_items,
                coa_template_file=coa_template_file,
            )
            flash('工件更新成功', 'success')
            return redirect(url_for('qc.workpiece_detail', workpiece_id=workpiece_id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/workpiece_form.html',
        workpiece=workpiece,
        is_edit=True,
        workpiece_types=QC_WORKPIECE_TYPE_DISPLAY,
    )


@qc_bp.route('/workpieces/<int:workpiece_id>/delete', methods=['POST'])
@login_required
def workpiece_delete(workpiece_id: int):
    """Delete a workpiece."""
    user = g.current_user
    blocked = _block_workpiece_access(user)
    if blocked:
        return blocked

    try:
        QCService.delete_workpiece(workpiece_id, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.workpiece_list'))


@qc_bp.route('/workpieces/<int:workpiece_id>/snapshot')
@login_required
def workpiece_snapshot(workpiece_id: int):
    """Return workpiece preview data for the order form."""
    user = g.current_user
    workpiece = QCService.get_workpiece(workpiece_id, user)
    if not workpiece:
        return jsonify({'success': False, 'message': '工件不存在或没有权限查看'}), 404
    return jsonify({'success': True, 'workpiece': QCService.serialize_workpiece_preview(workpiece)})


# ==================== 璐ㄩ噺鎺у埗妯″潡 ====================

@qc_bp.route('/quality-control/')
@login_required
def quality_control_list():
    """Quality control work order list."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    keyword = request.args.get('keyword', '')

    pagination = QCService.get_work_order_list(
        user=user,
        status=status or None,
        keyword=keyword or None,
        page=page,
    )

    return render_template(
        'qc/work_order_list.html',
        orders=pagination.items,
        pagination=pagination,
        status=status,
        keyword=keyword,
    )


@qc_bp.route('/quality-control/new', methods=['GET', 'POST'])
@login_required
def quality_control_new():
    """Create a new work order."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    if not QCService.can_create_work_order(user):
        flash('没有权限创建工件订单', 'error')
        return redirect(url_for('qc.index'))

    suppliers = _active_suppliers()
    workpieces = QCService.get_workpiece_choices(user)

    if request.method == 'POST':
        action = request.form.get('submit_action', '').strip()
        if action not in ['draft', 'complete']:
            flash('操作失败，请检查后重试', 'error')
            return render_template(
                'qc/work_order_form.html',
                workpieces=workpieces,
                suppliers=suppliers,
                workpiece_types=QC_WORKPIECE_TYPE_DISPLAY,
            )

        strict_complete = action == 'complete'
        inspector_id = request.form.get('inspector_id', type=int) if strict_complete else None
        workpiece_id = request.form.get('workpiece_id', type=int)

        try:
            if strict_complete and not inspector_id:
                raise ValueError('提交数据无效，请检查后重试')

            work_order = QCService.create_work_order(
                data={
                    'batch_no': request.form.get('batch_no', '').strip(),
                    'workpiece_id': workpiece_id,
                    'workpiece_name': request.form.get('workpiece_name', '').strip(),
                    'workpiece_type': request.form.get('workpiece_type', '').strip(),
                    'quantity': request.form.get('quantity', '').strip(),
                },
                controller_id=user.id,
                status='draft' if action == 'draft' else 'qc_pending',
                allow_partial=(action == 'draft'),
                auto_commit=False,
            )

            if workpiece_id:
                QCService.apply_workpiece_to_order(work_order.id, workpiece_id, user)
            else:
                legacy_points = _build_legacy_point_items(request.form, request.files)
                legacy_remarks = _build_remark_items(request.form, request.files)
                drawing_file = request.files.get('drawing')
                instruction_file = request.files.get('instruction')
                has_legacy_payload = any([
                    drawing_file and drawing_file.filename,
                    instruction_file and instruction_file.filename,
                    legacy_points,
                    legacy_remarks,
                ])

                if has_legacy_payload:
                    QCService.sync_work_order_attachments(
                        order_id=work_order.id,
                        point_items=legacy_points,
                        remark_items=legacy_remarks,
                        drawing_file=drawing_file,
                        instruction_file=instruction_file,
                        user=user,
                        allow_partial=(action == 'draft'),
                    )
                elif strict_complete:
                    raise ValueError('请选择有效工件或上传质检材料')
                else:
                    db.session.flush()

            QCService.sync_order_section_files(
                order_id=work_order.id,
                drawing_note_file=request.files.get('drawing_note_file'),
                guide_certificate_file=request.files.get('guide_certificate_file'),
                remark_note_file=request.files.get('remark_note_file'),
                user=user,
            )

            if action == 'complete':
                QCService.complete_quality_control(work_order.id, inspector_id, user)
                flash('操作成功', 'success')
                return redirect(url_for('qc.quality_inspection_detail', order_id=work_order.id))

            flash('工件订单已保存为草稿，完成后可进入质量检测', 'success')
            return redirect(url_for('qc.quality_control_detail', order_id=work_order.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/work_order_form.html',
        workpieces=workpieces,
        suppliers=suppliers,
        workpiece_types=QC_WORKPIECE_TYPE_DISPLAY,
    )


@qc_bp.route('/quality-control/<int:order_id>')
@login_required
def quality_control_detail(order_id: int):
    """Quality control work order detail."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.quality_control_list'))

    suppliers = _active_suppliers()
    return render_template(
        'qc/work_order_detail_qc.html',
        order=work_order,
        suppliers=suppliers,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
    )


@qc_bp.route('/quality-control/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def quality_control_edit(order_id: int):
    """Edit a work order."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.quality_control_list'))

    if not QCService.can_edit_work_order(user, work_order):
        flash('当前工件订单状态不允许编辑', 'error')
        return redirect(url_for('qc.quality_control_detail', order_id=order_id))

    suppliers = _active_suppliers()
    workpieces = QCService.get_workpiece_choices(user)

    if request.method == 'POST':
        try:
            allow_partial = work_order.status == 'draft'
            workpiece_id = request.form.get('workpiece_id', type=int)
            previous_workpiece_id = work_order.workpiece_id
            had_attachments = bool(work_order.attachments)

            QCService.update_work_order(
                order_id=order_id,
                data={
                    'batch_no': request.form.get('batch_no', '').strip(),
                    'workpiece_id': workpiece_id,
                    'workpiece_name': request.form.get('workpiece_name', '').strip(),
                    'workpiece_type': request.form.get('workpiece_type', '').strip(),
                    'quantity': request.form.get('quantity', '').strip(),
                },
                user=user,
                allow_partial=allow_partial,
            )

            if workpiece_id:
                if previous_workpiece_id != workpiece_id or not had_attachments:
                    QCService.apply_workpiece_to_order(order_id, workpiece_id, user)
            else:
                QCService.sync_work_order_attachments(
                    order_id=order_id,
                    point_items=_build_legacy_point_items(request.form, request.files),
                    remark_items=_build_remark_items(request.form, request.files),
                    drawing_file=request.files.get('drawing'),
                    instruction_file=request.files.get('instruction'),
                    user=user,
                    allow_partial=allow_partial,
                )

            QCService.sync_order_section_files(
                order_id=order_id,
                drawing_note_file=request.files.get('drawing_note_file'),
                guide_certificate_file=request.files.get('guide_certificate_file'),
                remark_note_file=request.files.get('remark_note_file'),
                user=user,
            )

            flash('工件订单更新成功', 'success')
            return redirect(url_for('qc.quality_control_detail', order_id=order_id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/work_order_form.html',
        order=work_order,
        suppliers=suppliers,
        workpieces=workpieces,
        workpiece_types=QC_WORKPIECE_TYPE_DISPLAY,
        is_edit=True,
    )


@qc_bp.route('/quality-control/<int:order_id>/delete', methods=['POST'])
@login_required
def quality_control_delete(order_id: int):
    """Delete a work order."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    try:
        QCService.delete_work_order(order_id, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.quality_control_list'))


@qc_bp.route('/quality-control/<int:order_id>/complete', methods=['POST'])
@login_required
def quality_control_complete(order_id: int):
    """Complete quality control and assign a supplier."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    inspector_id = request.form.get('inspector_id', type=int)

    try:
        QCService.complete_quality_control(order_id, inspector_id, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')

    return redirect(url_for('qc.quality_control_detail', order_id=order_id))


@qc_bp.route('/quality-control/attachments/<int:attachment_id>/delete', methods=['POST'])
@login_required
def quality_control_delete_attachment(attachment_id: int):
    """Delete a legacy work-order attachment."""
    user = g.current_user
    blocked = _block_quality_control_for_inspector(user)
    if blocked:
        return blocked

    try:
        QCService.delete_attachment(attachment_id, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(request.referrer or url_for('qc.index'))


# ==================== 质量检测模块 ====================

@qc_bp.route('/quality-inspection/')
@login_required
def quality_inspection_list():
    """Quality inspection list."""
    user = g.current_user
    blocked = _require_qc_inspection_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '')

    pagination = QCService.get_inspection_list(
        user=user,
        keyword=keyword or None,
        page=page,
    )

    return render_template(
        'qc/inspection_list.html',
        orders=pagination.items,
        pagination=pagination,
        keyword=keyword,
    )


@qc_bp.route('/quality-inspection/<int:order_id>', methods=['GET', 'POST'])
@login_required
def quality_inspection_detail(order_id: int):
    """Quality inspection detail."""
    user = g.current_user
    blocked = _require_qc_inspection_access(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.quality_inspection_list'))

    if request.method == 'POST':
        if not QCService.can_inspect_work_order(user, work_order):
            flash('没有权限提交质检结果', 'error')
            return redirect(url_for('qc.quality_inspection_detail', order_id=order_id))

        action = request.form.get('submit_action', 'submit').strip()
        final_submit = action != 'draft'
        try:
            results = []
            for attachment in work_order.attachments:
                result = request.form.get(f'result_{attachment.id}', '').strip()
                remark = request.form.get(f'remark_{attachment.id}', '').strip()
                report_file = request.files.get(f'report_file_{attachment.id}')
                has_payload = bool(result or remark or (report_file and report_file.filename))
                if final_submit or has_payload:
                    results.append(
                        {
                            'attachment_id': attachment.id,
                            'result': result,
                            'remark': remark or None,
                            'report_file': report_file,
                        }
                    )

            updated_order = QCService.submit_inspection(
                order_id=order_id,
                results=results,
                user=user,
                final_submit=final_submit,
            )

            if not final_submit:
                flash('操作成功', 'success')
                return redirect(url_for('qc.quality_inspection_detail', order_id=order_id))

            if updated_order.status == 'inspection_completed':
                flash('质检合格，已进入验收模块', 'success')
                return redirect(url_for('qc.acceptance_detail', order_id=order_id))

            flash('当前无权限或条件未满足', 'warning')
            if QCService.can_access_quality_control(user):
                return redirect(url_for('qc.quality_control_detail', order_id=order_id))
            return redirect(url_for('qc.quality_inspection_list'))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')

    return render_template(
        'qc/work_order_detail_inspector.html',
        order=work_order,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
    )


# ==================== 楠屾敹妯″潡 ====================

@qc_bp.route('/acceptance/')
@login_required
def acceptance_list():
    """Acceptance list."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    page = request.args.get('page', 1, type=int)
    keyword = request.args.get('keyword', '')

    pagination = QCService.get_acceptance_list(
        user=user,
        keyword=keyword or None,
        page=page,
    )

    return render_template(
        'qc/acceptance_list.html',
        orders=pagination.items,
        pagination=pagination,
        keyword=keyword,
    )


@qc_bp.route('/acceptance/<int:order_id>')
@login_required
def acceptance_detail(order_id: int):
    """Acceptance detail."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.acceptance_list'))

    active_acceptance_batch = QCService.current_acceptance_batch(work_order)
    signatures = (
        active_acceptance_batch.signatures_by_role
        if active_acceptance_batch
        else {}
    )
    can_cancel_signatures = {
        role: QCService.can_cancel_acceptance_signature(user, work_order, role)
        for role in ['qc_controller', 'qc_inspector']
    }
    eligible_signer_roles = QCService.eligible_acceptance_signer_roles(user, work_order)
    return render_template(
        'qc/acceptance_detail.html',
        order=work_order,
        signatures=signatures,
        active_acceptance_batch=active_acceptance_batch,
        acceptance_batches=work_order.acceptance_batches,
        can_cancel_signatures=can_cancel_signatures,
        eligible_signer_roles=eligible_signer_roles,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
    )


@qc_bp.route('/acceptance/<int:order_id>/sign', methods=['POST'])
@login_required
def acceptance_sign(order_id: int):
    """Acceptance sign action."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    try:
        result = QCService.sign_acceptance(
            order_id,
            user,
            signer_role=request.form.get('signer_role'),
            production_quantity=request.form.get('production_quantity'),
            accepted_quantity=request.form.get('accepted_quantity'),
        )
        flash(result['message'], 'success' if result['completed'] else 'info')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.acceptance_detail', order_id=order_id))


@qc_bp.route('/acceptance/<int:order_id>/batch/new', methods=['POST'])
@login_required
def acceptance_start_batch(order_id: int):
    """Start a new partial acceptance batch."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    try:
        QCService.start_acceptance_batch(order_id, user)
        flash('已发起新的验收批次，请填写本次数量并完成双方确认', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.acceptance_detail', order_id=order_id))


@qc_bp.route('/acceptance/<int:order_id>/signature/<signer_role>/cancel', methods=['POST'])
@login_required
def acceptance_cancel_signature(order_id: int, signer_role: str):
    """Cancel one acceptance signature."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    try:
        QCService.cancel_acceptance_signature(order_id, signer_role, user)
        flash('操作成功', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('qc.acceptance_detail', order_id=order_id))


@qc_bp.route('/acceptance/<int:order_id>/rollback', methods=['POST'])
@login_required
def acceptance_rollback(order_id: int):
    """Rollback acceptance and return the workflow."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    target = request.form.get('target', '').strip()
    reason = request.form.get('reason', '').strip()

    try:
        QCService.rollback_acceptance(order_id, target, reason, user)
        flash('已退回上一流程', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')

    return redirect(url_for('qc.acceptance_detail', order_id=order_id))


@qc_bp.route('/acceptance/<int:order_id>/print')
@login_required
def acceptance_print(order_id: int):
    """Printable acceptance sheet."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.acceptance_list'))

    signatures = {signature.signer_role: signature for signature in work_order.signatures}
    return render_template(
        'qc/acceptance_print.html',
        order=work_order,
        signatures=signatures,
        inspection_records_by_attachment=_build_inspection_record_map(work_order),
        download_url=url_for('qc.acceptance_print_download', order_id=work_order.id),
        current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )


@qc_bp.route('/acceptance/<int:order_id>/print/download')
@login_required
def acceptance_print_download(order_id: int):
    """Download the workpiece acceptance sheet as a Word document."""
    user = g.current_user
    blocked = _require_qc_acceptance_access(user)
    if blocked:
        return blocked

    work_order = QCService.get_work_order(order_id, user)
    if not work_order:
        flash('工件订单不存在或没有权限查看', 'error')
        return redirect(url_for('qc.acceptance_list'))
    records = _build_inspection_record_map(work_order)
    lines = [
        '工件验收确认单',
        f'批次编号：{work_order.batch_no}',
        f'工件名称：{work_order.workpiece_name}',
        f'计划生产数量：{float(work_order.quantity or 0):g}',
        f'实际交付数量：{float(work_order.actual_delivered_quantity or 0):g}',
        f"验收日期：{work_order.accepted_at.strftime('%Y-%m-%d') if work_order.accepted_at else '-'}",
        f'质控人：{work_order.controller.real_name or work_order.controller.username if work_order.controller else "-"}',
        f'供应商：{work_order.inspector.real_name or work_order.inspector.username if work_order.inspector else "-"}',
        '',
        '质检记录明细',
    ]
    for attachment in work_order.ordered_attachments:
        record = records.get(attachment.id)
        result_text = {'pass': '通过', 'fail': '不通过', 'draft': '草稿'}.get(record.result if record else '', '-')
        lines.append(
            f'{attachment.display_title}：{result_text}；'
            f'报告：{record.report_filename if record and record.report_file_path else "-"}；'
            f'备注：{record.remark or "" if record else ""}'
        )
    lines.extend(['', '签字确认区', '质控人签字：', '供应商签字：'])
    return _send_docx_text_report(lines, f'工件验收确认单_{work_order.batch_no}.docx')
