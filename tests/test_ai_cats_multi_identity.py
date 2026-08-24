"""AI CATS multi-identity access-control integration tests."""

from __future__ import annotations

import json

import pytest
from werkzeug.security import generate_password_hash

from app import db
from app.models import (
    AICatsAccountProfile,
    AICatsIdentityAuditLog,
    AICatsUserIdentity,
    Department,
    QCUserBinding,
    QCWorkOrder,
    Role,
    User,
)
from app.services.ai_cats_access_service import AICatsAccessService
from app.services.auth_service import AuthService
from app.services.qc_service import QCService
from config import ProductionConfig


def _create_role(code: str, name: str | None = None, permissions=None, level: int = 10) -> Role:
    role = Role(
        code=code,
        name=name or code,
        permissions=json.dumps(permissions or []),
        level=level,
    )
    db.session.add(role)
    db.session.flush()
    return role


def _create_user(username: str, role: Role, *, active: bool = True) -> User:
    user = User(
        username=username,
        password_hash=generate_password_hash('Pass123!'),
        real_name=username,
        role_id=role.id,
        email=f'{username}@example.com',
        is_active=active,
        require_password_change=False,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _assign(user: User, codes, *, access_mode: str = 'shared') -> list[AICatsUserIdentity]:
    AICatsAccessService.ensure_profile(user, access_mode, is_enabled=True)
    rows = AICatsAccessService.request_identities(
        user,
        codes,
        source='test',
        status='active',
    )
    db.session.commit()
    return rows


def test_production_config_forces_legacy_open_access_off():
    """Production cannot re-enable the retired all-user test override."""
    assert ProductionConfig.AI_CATS_TEST_OPEN_ACCESS is False


def test_multi_identity_registration_creates_pending_shell_account(app, client):
    """Public AI CATS registration stores each requested identity separately."""
    response = client.post(
        '/auth/register/qc',
        data={
            'username': 'multi_register',
            'real_name': 'Multi Register',
            'email': 'multi_register@example.com',
            'identity_codes': ['controller', 'research_reviewer'],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert '/auth/pending' in response.headers['Location']
    with app.app_context():
        user = User.query.filter_by(username='multi_register').one()
        profile = AICatsAccountProfile.query.get(user.id)
        identities = AICatsUserIdentity.query.filter_by(user_id=user.id).all()
        assert user.role.code == 'ai_cats_user'
        assert user.is_active is False
        assert profile.access_mode == 'ai_cats_only'
        assert {row.identity_code for row in identities} == {
            'controller',
            'research_reviewer',
        }
        assert all(row.status == 'pending' for row in identities)
        assert next(row for row in identities if row.identity_code == 'controller').enabled_module_codes == {
            'production',
            'assembly',
        }


def test_manager_can_partially_approve_multi_identity_account(app, client, login):
    """Approving one identity activates it without approving sibling requests."""
    with app.app_context():
        manager_role = _create_role('gm_assistant', '总经理助理', level=90)
        manager = _create_user('identity_manager', manager_role)
        pending_user, error = AuthService.register_qc_user(
            username='partial_identity_user',
            real_name='Partial Identity User',
            identity_codes=['controller', 'supplier'],
            email='partial_identity_user@example.com',
        )
        assert error is None
        controller = AICatsUserIdentity.query.filter_by(
            user_id=pending_user.id,
            identity_code='controller',
        ).one()
        manager_id = manager.id
        user_id = pending_user.id
        identity_id = controller.id

    login(manager_id)
    response = client.post(
        f'/qc/admin/identities/{identity_id}/approve',
        data={'next': f'/qc/admin/users/{user_id}'},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        user = User.query.get(user_id)
        statuses = {
            row.identity_code: row.status
            for row in AICatsUserIdentity.query.filter_by(user_id=user_id).all()
        }
        assert user.is_active is True
        assert statuses == {'controller': 'active', 'supplier': 'pending'}
        assert AICatsIdentityAuditLog.query.filter_by(
            target_user_id=user_id,
            identity_code='controller',
            action='identity_active',
        ).count() == 1


def test_disabling_shared_ai_cats_access_does_not_disable_erp_user(app):
    """AI CATS account switches must not mutate shared ERP activation."""
    with app.app_context():
        sales_role = _create_role('sales_identity_test', permissions=['contract_view'])
        manager_role = _create_role('general_manager', level=100)
        user = _create_user('shared_identity_user', sales_role)
        manager = _create_user('shared_identity_manager', manager_role)
        _assign(user, ['controller'])

        AICatsAccessService.set_account_enabled(user, False, manager)
        db.session.commit()

        assert user.is_active is True
        assert user.has_permission('contract_view') is True
        assert AICatsAccessService.can_enter(user) is False
        assert AICatsAccountProfile.query.get(user.id).is_enabled is False


def test_module_scope_is_enforced_in_navigation_and_direct_routes(app, client, login):
    """Disabling assembly scope must leave production active and block direct URLs."""
    with app.app_context():
        role = _create_role('scope_erp_role')
        manager_role = _create_role('general_manager', level=100)
        user = _create_user('scoped_controller', role)
        manager = _create_user('scope_manager', manager_role)
        identity = _assign(user, ['controller'])[0]
        AICatsAccessService.set_scope_enabled(identity, 'assembly', False, manager)
        db.session.commit()
        user_id = user.id

    login(user_id)
    assert client.get('/qc/production/', follow_redirects=False).status_code == 200
    assert client.get('/qc/assembly/', follow_redirects=False).status_code == 302
    assert client.get('/qc/assembly/products/', follow_redirects=False).status_code == 302
    assert client.get('/qc/research/', follow_redirects=False).status_code == 302


def test_supplier_candidates_are_shared_by_production_and_assembly_only(app):
    """Production and assembly reuse supplier identity while research stays isolated."""
    with app.app_context():
        role = _create_role('candidate_erp_role')
        supplier = _create_user('candidate_supplier', role)
        researcher = _create_user('candidate_researcher', role)
        manager_role = _create_role('general_manager', level=100)
        manager = _create_user('candidate_manager', manager_role)
        _assign(supplier, ['supplier'])
        _assign(researcher, ['research_reviewer'])

        production_ids = {
            user.id for user in AICatsAccessService.eligible_users('supplier', 'production')
        }
        assembly_ids = {
            user.id for user in AICatsAccessService.eligible_users('supplier', 'assembly')
        }
        research_ids = {
            user.id for user in AICatsAccessService.eligible_users(
                'research_reviewer',
                'research',
            )
        }
        assert production_ids == {supplier.id}
        assert assembly_ids == {supplier.id}
        assert research_ids == {researcher.id}
        assert manager.id not in production_ids | assembly_ids | research_ids


def test_legacy_backfill_is_idempotent_and_preserves_cross_module_access(app):
    """Legacy roles migrate once and retain their former research capability."""
    with app.app_context():
        controller_role = _create_role('qc_controller')
        inspector_role = _create_role('qc_inspector')
        erp_role = _create_role('legacy_erp_role')
        dedicated = _create_user('legacy_dedicated', controller_role)
        shared = _create_user('legacy_shared', erp_role)
        db.session.add(
            QCUserBinding(
                user_id=shared.id,
                role_id=inspector_role.id,
                is_active=True,
            )
        )
        business_order = QCWorkOrder(
            batch_no='LEGACY-MIGRATION-BUSINESS-001',
            workpiece_name='Migration Sentinel',
            quantity=7,
            controller_id=dedicated.id,
            inspector_id=shared.id,
            status='inspection_pending',
        )
        db.session.add(business_order)
        db.session.commit()
        business_snapshot = (
            business_order.id,
            business_order.batch_no,
            business_order.quantity,
            business_order.status,
            QCWorkOrder.query.count(),
        )

        first_change_count = AICatsAccessService.backfill_legacy_identities()
        second_change_count = AICatsAccessService.backfill_legacy_identities()

        assert first_change_count >= 6
        assert second_change_count == 0
        assert AICatsAccessService.active_identity_codes(dedicated) == {
            'controller',
            'researcher',
        }
        assert AICatsAccessService.active_identity_codes(shared) == {
            'supplier',
            'research_reviewer',
        }
        assert AICatsAccountProfile.query.get(dedicated.id).access_mode == 'ai_cats_only'
        assert AICatsAccountProfile.query.get(shared.id).access_mode == 'shared'
        unchanged_order = QCWorkOrder.query.get(business_order.id)
        assert (
            unchanged_order.id,
            unchanged_order.batch_no,
            unchanged_order.quantity,
            unchanged_order.status,
            QCWorkOrder.query.count(),
        ) == business_snapshot


def test_revocation_and_self_counterparty_are_blocked_for_unfinished_order(app):
    """A multi-role user cannot self-assign both sides or abandon unfinished work."""
    with app.app_context():
        role = _create_role('counterparty_erp_role')
        manager_role = _create_role('general_manager', level=100)
        user = _create_user('multi_counterparty', role)
        manager = _create_user('counterparty_manager', manager_role)
        identities = _assign(user, ['controller', 'supplier'])
        controller_identity = next(
            row for row in identities if row.identity_code == 'controller'
        )
        order = QCWorkOrder(
            batch_no='MULTI-COUNTERPARTY-001',
            workpiece_name='Test Workpiece',
            quantity=1,
            controller_id=user.id,
            status='draft',
        )
        db.session.add(order)
        db.session.commit()

        with pytest.raises(ValueError, match='不同用户'):
            QCService.complete_quality_control(order.id, user.id, user)
        with pytest.raises(ValueError, match='未完成任务'):
            AICatsAccessService.assert_identity_change_safe(controller_identity)
        with pytest.raises(ValueError, match='未完成任务'):
            AICatsAccessService.set_account_enabled(user, False, manager)

        order.status = 'accepted'
        db.session.commit()
        assert AICatsAccessService.unfinished_assignment_summary(controller_identity) == []


def test_general_manager_assistant_has_full_access_and_admin_page(app, client, login):
    """General manager assistants receive full module and identity administration access."""
    with app.app_context():
        role = _create_role('gm_assistant', '总经理助理', level=90)
        manager = _create_user('assistant_full_access', role)
        db.session.commit()
        manager_id = manager.id
        assert all(
            AICatsAccessService.has_scope(manager, module_code)
            for module_code in ('production', 'assembly', 'research')
        )

    login(manager_id)
    admin_response = client.get('/qc/admin/users', follow_redirects=False)
    assert admin_response.status_code == 200, admin_response.headers.get('Location')
    assert client.get('/qc/production/', follow_redirects=False).status_code == 200
    assert client.get('/qc/assembly/', follow_redirects=False).status_code == 200
    assert client.get('/qc/research/', follow_redirects=False).status_code == 200
