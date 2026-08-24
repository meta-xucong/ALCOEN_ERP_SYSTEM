"""Central AI CATS multi-identity access and administration service."""

from __future__ import annotations

import json
from datetime import datetime

from app import db
from app.models import (
    AI_CATS_IDENTITY_CODES,
    AI_CATS_IDENTITY_DEFINITIONS,
    AI_CATS_LEGACY_ROLE_IDENTITY_MAP,
    AI_CATS_MODULE_CODES,
    AI_CATS_TECHNICAL_ROLE_CODE,
    AICatsAccountProfile,
    AICatsIdentityAuditLog,
    AICatsUserIdentity,
    AICatsUserIdentityScope,
    QC_DEFAULT_PERMISSION_CODES,
    QC_MANAGER_ROLE_CODES,
    QC_PERMISSIONS,
    QCUserBinding,
    Role,
    User,
)


class AICatsAccessService:
    """Resolve AI CATS identities and perform audited identity changes."""

    IDENTITY_LEGACY_PERMISSION_MAP = {
        'controller': set(QC_DEFAULT_PERMISSION_CODES['qc_controller']),
        'supplier': set(QC_DEFAULT_PERMISSION_CODES['qc_inspector']),
        'researcher': set(QC_DEFAULT_PERMISSION_CODES['qc_controller']),
        'research_reviewer': set(QC_DEFAULT_PERMISSION_CODES['qc_inspector']),
    }

    @staticmethod
    def identity_definitions() -> dict[str, dict]:
        """Return a copy of the public identity catalog."""
        return {
            code: {
                **definition,
                'default_scopes': tuple(definition.get('default_scopes', ())),
            }
            for code, definition in AI_CATS_IDENTITY_DEFINITIONS.items()
        }

    @staticmethod
    def ensure_technical_role() -> Role:
        """Ensure the permissionless shell role for new AI CATS-only accounts."""
        role = Role.query.filter_by(code=AI_CATS_TECHNICAL_ROLE_CODE).first()
        if role:
            return role
        role = Role(
            name='AI CATS 用户',
            code=AI_CATS_TECHNICAL_ROLE_CODE,
            description='AI CATS 独立账号技术角色，业务权限由 AI CATS 身份分配',
            permissions='[]',
            level=1,
        )
        db.session.add(role)
        db.session.flush()
        return role

    @staticmethod
    def backfill_legacy_identities() -> int:
        """Idempotently copy legacy QC roles and bindings into multi-identities."""
        AICatsAccessService.ensure_technical_role()
        changed = 0
        users = User.query.all()
        for user in users:
            legacy_roles: dict[str, bool] = {}
            if user.role and user.role.code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP:
                legacy_roles[user.role.code] = bool(user.is_active)
                if not AICatsAccessService.get_profile(user):
                    AICatsAccessService.ensure_profile(
                        user,
                        'ai_cats_only',
                        is_enabled=bool(user.is_active),
                    )
                    changed += 1

            bindings = QCUserBinding.query.filter_by(user_id=user.id).all()
            for binding in bindings:
                if binding.role and binding.role.code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP:
                    legacy_roles[binding.role.code] = (
                        legacy_roles.get(binding.role.code, False)
                        or bool(binding.is_active)
                    )
            if bindings and not AICatsAccessService.get_profile(user):
                AICatsAccessService.ensure_profile(
                    user,
                    'shared',
                    is_enabled=True,
                )
                changed += 1

            existing = {
                row.identity_code: row
                for row in AICatsAccessService._identity_rows(user)
            }
            for legacy_role_code, is_active in legacy_roles.items():
                for identity_code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP[legacy_role_code]:
                    if identity_code in existing:
                        continue
                    identity = AICatsUserIdentity(
                        user_id=user.id,
                        identity_code=identity_code,
                        status='active' if is_active else 'pending',
                        source='legacy_migration',
                        requested_at=user.created_at or datetime.now(),
                        approved_at=user.approved_at if is_active else None,
                        approved_by=user.approved_by if is_active else None,
                    )
                    db.session.add(identity)
                    db.session.flush()
                    for module_code in AI_CATS_IDENTITY_DEFINITIONS[identity_code]['default_scopes']:
                        db.session.add(
                            AICatsUserIdentityScope(
                                user_identity_id=identity.id,
                                module_code=module_code,
                                is_enabled=True,
                            )
                        )
                    existing[identity_code] = identity
                    changed += 1
        if changed:
            db.session.commit()
        return changed

    @staticmethod
    def ensure_ready() -> int:
        """Ensure technical seed data and migrate legacy access idempotently."""
        changed = AICatsAccessService.backfill_legacy_identities()
        if db.session.new or db.session.dirty:
            db.session.commit()
        return changed

    @staticmethod
    def normalize_identity_codes(identity_codes) -> list[str]:
        """Validate and deduplicate submitted identity codes."""
        normalized: list[str] = []
        for identity_code in identity_codes or []:
            code = str(identity_code or '').strip()
            if code not in AI_CATS_IDENTITY_CODES:
                raise ValueError('包含无效的 AI CATS 身份')
            if code not in normalized:
                normalized.append(code)
        if not normalized:
            raise ValueError('请至少选择一个 AI CATS 身份')
        return normalized

    @staticmethod
    def get_profile(user: User | None) -> AICatsAccountProfile | None:
        """Return the user's AI CATS account profile when present."""
        if not user or not user.id:
            return None
        return db.session.get(AICatsAccountProfile, user.id)

    @staticmethod
    def ensure_profile(
        user: User,
        access_mode: str,
        *,
        is_enabled: bool = True,
    ) -> AICatsAccountProfile:
        """Create or update one AI CATS account profile."""
        if access_mode not in {'ai_cats_only', 'shared'}:
            raise ValueError('无效的 AI CATS 账号类型')
        profile = AICatsAccessService.get_profile(user)
        if not profile:
            profile = AICatsAccountProfile(
                user_id=user.id,
                access_mode=access_mode,
                is_enabled=is_enabled,
            )
            db.session.add(profile)
        else:
            profile.access_mode = access_mode
            profile.is_enabled = is_enabled
        return profile

    @staticmethod
    def _identity_rows(user: User | None) -> list[AICatsUserIdentity]:
        if not user or not user.id:
            return []
        return AICatsUserIdentity.query.filter_by(user_id=user.id).order_by(
            AICatsUserIdentity.id.asc()
        ).all()

    @staticmethod
    def _legacy_role_codes(user: User) -> set[str]:
        """Return active legacy AI CATS role codes for compatibility."""
        role_codes: set[str] = set()
        if user.role and user.role.code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP:
            role_codes.add(user.role.code)
        if user.id:
            bindings = QCUserBinding.query.filter_by(user_id=user.id, is_active=True).all()
            role_codes.update(
                binding.role.code
                for binding in bindings
                if binding.role and binding.role.code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP
            )
        return role_codes

    @staticmethod
    def _legacy_identity_codes(user: User) -> set[str]:
        identity_codes: set[str] = set()
        for role_code in AICatsAccessService._legacy_role_codes(user):
            identity_codes.update(AI_CATS_LEGACY_ROLE_IDENTITY_MAP.get(role_code, ()))
        return identity_codes

    @staticmethod
    def active_identity_rows(user: User | None) -> list[AICatsUserIdentity]:
        """Return active new-model identities, respecting account-level disable."""
        if not user or not user.is_active:
            return []
        profile = AICatsAccessService.get_profile(user)
        if profile and not profile.is_enabled:
            return []
        return [row for row in AICatsAccessService._identity_rows(user) if row.status == 'active']

    @staticmethod
    def active_identity_codes(user: User | None) -> set[str]:
        """Return active identity codes with a legacy fallback before migration."""
        if not user or not user.is_active:
            return set()
        profile = AICatsAccessService.get_profile(user)
        if profile and not profile.is_enabled:
            return set()
        rows = AICatsAccessService._identity_rows(user)
        if rows:
            return {row.identity_code for row in rows if row.status == 'active'}
        return AICatsAccessService._legacy_identity_codes(user)

    @staticmethod
    def is_manager(user: User | None) -> bool:
        """Return whether the user has full AI CATS business access."""
        if not user or not user.is_active:
            return False
        if user.is_superadmin:
            return True
        profile = AICatsAccessService.get_profile(user)
        if profile and not profile.is_enabled:
            return False
        if user.role and user.role.code in QC_MANAGER_ROLE_CODES:
            return True
        return bool(user.has_ai_cats_test_access)

    @staticmethod
    def is_qc_admin(user: User | None) -> bool:
        """Return whether the user may administer AI CATS identities."""
        return AICatsAccessService.is_manager(user)

    @staticmethod
    def has_identity(
        user: User | None,
        identity_code: str,
        module_code: str | None = None,
    ) -> bool:
        """Check one active identity and optional enabled module scope."""
        if identity_code not in AI_CATS_IDENTITY_CODES or not user or not user.is_active:
            return False
        if AICatsAccessService.is_manager(user):
            return True
        if identity_code not in AICatsAccessService.active_identity_codes(user):
            return False
        if module_code is None:
            return True
        if module_code not in AI_CATS_MODULE_CODES:
            return False
        if module_code not in AI_CATS_IDENTITY_DEFINITIONS[identity_code]['default_scopes']:
            return False

        rows = AICatsAccessService._identity_rows(user)
        if rows:
            identity = next(
                (
                    row
                    for row in rows
                    if row.identity_code == identity_code and row.status == 'active'
                ),
                None,
            )
            return bool(identity and module_code in identity.enabled_module_codes)

        return module_code in AI_CATS_IDENTITY_DEFINITIONS[identity_code]['default_scopes']

    @staticmethod
    def has_scope(user: User | None, module_code: str) -> bool:
        """Check whether any identity grants one AI CATS module scope."""
        if module_code not in AI_CATS_MODULE_CODES or not user or not user.is_active:
            return False
        if AICatsAccessService.is_manager(user):
            return True
        return any(
            AICatsAccessService.has_identity(user, identity_code, module_code)
            for identity_code in AI_CATS_IDENTITY_CODES
        )

    @staticmethod
    def can_enter(user: User | None) -> bool:
        """Check whether an active user can enter AI CATS."""
        if not user or not user.is_active:
            return False
        if AICatsAccessService.is_manager(user):
            return True
        profile = AICatsAccessService.get_profile(user)
        if profile and not profile.is_enabled:
            return False
        return bool(AICatsAccessService.active_identity_codes(user))

    @staticmethod
    def is_ai_cats_only(user: User | None) -> bool:
        """Check whether the account is prohibited from entering ERP."""
        if not user:
            return False
        profile = AICatsAccessService.get_profile(user)
        if profile:
            return profile.access_mode == 'ai_cats_only'
        return bool(user.role and user.role.code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP)

    @staticmethod
    def legacy_effective_role_code(user: User | None) -> str:
        """Return a stable single role code for remaining compatibility paths."""
        if not user:
            return ''
        if user.is_superadmin:
            return 'superadmin'
        if user.role and user.role.code in QC_MANAGER_ROLE_CODES:
            return user.role.code
        if user.has_ai_cats_test_access:
            return 'gm_assistant'
        identities = AICatsAccessService.active_identity_codes(user)
        if 'controller' in identities:
            return 'qc_controller'
        if 'supplier' in identities:
            return 'qc_inspector'
        if 'researcher' in identities:
            return 'qc_controller'
        if 'research_reviewer' in identities:
            return 'qc_inspector'
        return ''

    @staticmethod
    def has_legacy_permission(user: User | None, permission_code: str) -> bool:
        """Resolve existing ``qc_*`` permission calls through active identities."""
        if permission_code not in QC_PERMISSIONS or not user or not user.is_active:
            return False
        if AICatsAccessService.is_manager(user):
            return True

        rows = AICatsAccessService._identity_rows(user)
        if rows:
            return any(
                permission_code
                in AICatsAccessService.IDENTITY_LEGACY_PERMISSION_MAP.get(
                    identity_code,
                    set(),
                )
                for identity_code in AICatsAccessService.active_identity_codes(user)
            )

        # Preserve explicitly configured legacy role permissions until every
        # existing installation has completed the identity migration.
        roles: list[Role] = []
        if user.role and user.role.code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP:
            roles.append(user.role)
        if user.id:
            roles.extend(
                binding.role
                for binding in QCUserBinding.query.filter_by(
                    user_id=user.id,
                    is_active=True,
                ).all()
                if binding.role
            )
        return any(role.has_qc_permission(permission_code) for role in roles)

    @staticmethod
    def request_identities(
        user: User,
        identity_codes,
        *,
        source: str,
        status: str = 'pending',
        approver: User | None = None,
    ) -> list[AICatsUserIdentity]:
        """Create or reactivate one or more identity requests."""
        codes = AICatsAccessService.normalize_identity_codes(identity_codes)
        if status not in {'pending', 'active'}:
            raise ValueError('无效的身份申请状态')
        existing = {
            row.identity_code: row
            for row in AICatsAccessService._identity_rows(user)
        }
        results: list[AICatsUserIdentity] = []
        now = datetime.now()
        for code in codes:
            identity = existing.get(code)
            if identity and identity.status in {'active', 'pending'}:
                raise ValueError(f'{identity.display_name}已经生效或正在审核中')
            if not identity:
                identity = AICatsUserIdentity(
                    user_id=user.id,
                    identity_code=code,
                    source=source,
                    requested_at=now,
                )
                db.session.add(identity)
                db.session.flush()
            identity.status = status
            identity.source = source
            identity.requested_at = now
            identity.revoked_by = None
            identity.revoked_at = None
            if status == 'active':
                identity.approved_by = approver.id if approver else None
                identity.approved_at = now
            else:
                identity.approved_by = None
                identity.approved_at = None

            default_scopes = AI_CATS_IDENTITY_DEFINITIONS[code]['default_scopes']
            scopes_by_code = {scope.module_code: scope for scope in identity.scopes}
            for module_code in default_scopes:
                scope = scopes_by_code.get(module_code)
                if not scope:
                    scope = AICatsUserIdentityScope(
                        user_identity_id=identity.id,
                        module_code=module_code,
                        is_enabled=True,
                    )
                    db.session.add(scope)
                else:
                    scope.is_enabled = True
            results.append(identity)
        return results

    @staticmethod
    def _identity_snapshot(identity: AICatsUserIdentity | None) -> str | None:
        if not identity:
            return None
        return json.dumps(
            {
                'identity_code': identity.identity_code,
                'status': identity.status,
                'scopes': sorted(identity.enabled_module_codes),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def add_audit_log(
        target_user: User,
        action: str,
        operator: User,
        *,
        identity_code: str | None = None,
        before_state: str | None = None,
        after_state: str | None = None,
        reason: str | None = None,
    ) -> AICatsIdentityAuditLog:
        """Append one immutable identity administration audit record."""
        log = AICatsIdentityAuditLog(
            target_user_id=target_user.id,
            identity_code=identity_code,
            action=action,
            before_state=before_state,
            after_state=after_state,
            operator_id=operator.id,
            reason=(reason or '').strip() or None,
        )
        db.session.add(log)
        return log

    @staticmethod
    def set_identity_status(
        identity: AICatsUserIdentity,
        status: str,
        operator: User,
        *,
        reason: str | None = None,
    ) -> AICatsUserIdentity:
        """Approve, reject, revoke, or restore one identity with auditing."""
        if status not in {'active', 'rejected', 'revoked'}:
            raise ValueError('无效的身份状态')
        before = AICatsAccessService._identity_snapshot(identity)
        now = datetime.now()
        identity.status = status
        if status == 'active':
            identity.approved_by = operator.id
            identity.approved_at = now
            identity.revoked_by = None
            identity.revoked_at = None
            profile = AICatsAccessService.get_profile(identity.user)
            if not profile:
                access_mode = (
                    'ai_cats_only'
                    if identity.user.role
                    and identity.user.role.code == AI_CATS_TECHNICAL_ROLE_CODE
                    else 'shared'
                )
                profile = AICatsAccessService.ensure_profile(
                    identity.user,
                    access_mode,
                    is_enabled=True,
                )
            if profile.access_mode == 'ai_cats_only' and profile.is_enabled:
                identity.user.is_active = True
                identity.user.approved_by = operator.id
                identity.user.approved_at = now
        elif status == 'revoked':
            identity.revoked_by = operator.id
            identity.revoked_at = now
        else:
            identity.approved_by = None
            identity.approved_at = None
        db.session.flush()
        AICatsAccessService.add_audit_log(
            identity.user,
            f'identity_{status}',
            operator,
            identity_code=identity.identity_code,
            before_state=before,
            after_state=AICatsAccessService._identity_snapshot(identity),
            reason=reason,
        )
        return identity

    @staticmethod
    def unfinished_assignment_summary(
        identity: AICatsUserIdentity,
        module_code: str | None = None,
    ) -> list[str]:
        """Describe unfinished records still assigned to one identity."""
        from app.models import AssemblyOrder, AssemblyOutboundOrder, QCWorkOrder, ResearchBatch

        modules = {module_code} if module_code else set(identity.enabled_module_codes)
        user_id = identity.user_id
        findings: list[str] = []

        if identity.identity_code == 'controller' and 'production' in modules:
            count = QCWorkOrder.query.filter(
                QCWorkOrder.controller_id == user_id,
                QCWorkOrder.status != 'accepted',
            ).count()
            if count:
                findings.append(f'配件生产未完成订单 {count} 笔')
        if identity.identity_code == 'supplier' and 'production' in modules:
            count = QCWorkOrder.query.filter(
                QCWorkOrder.inspector_id == user_id,
                QCWorkOrder.status != 'accepted',
            ).count()
            if count:
                findings.append(f'配件生产待处理订单 {count} 笔')
        if identity.identity_code == 'controller' and 'assembly' in modules:
            count = AssemblyOrder.query.filter(
                AssemblyOrder.controller_id == user_id,
                AssemblyOrder.status != 'accepted',
            ).count()
            if count:
                findings.append(f'装配未完成订单 {count} 笔')
            outbound_count = AssemblyOutboundOrder.query.filter(
                AssemblyOutboundOrder.initiator_id == user_id,
                AssemblyOutboundOrder.status != 'completed',
            ).count()
            if outbound_count:
                findings.append(f'出厂未完成订单 {outbound_count} 笔')
        if identity.identity_code == 'supplier' and 'assembly' in modules:
            count = AssemblyOrder.query.filter(
                AssemblyOrder.inspector_id == user_id,
                AssemblyOrder.status != 'accepted',
            ).count()
            if count:
                findings.append(f'装配待处理订单 {count} 笔')
        if identity.identity_code == 'researcher' and 'research' in modules:
            count = ResearchBatch.query.filter(
                ResearchBatch.researcher_id == user_id,
                ResearchBatch.status != 'accepted',
            ).count()
            if count:
                findings.append(f'研究未完成批次 {count} 笔')
        if identity.identity_code == 'research_reviewer' and 'research' in modules:
            count = ResearchBatch.query.filter(
                ResearchBatch.reviewer_id == user_id,
                ResearchBatch.status != 'accepted',
            ).count()
            if count:
                findings.append(f'研究待指导批次 {count} 笔')
        return findings

    @staticmethod
    def assert_identity_change_safe(
        identity: AICatsUserIdentity,
        module_code: str | None = None,
    ) -> None:
        """Prevent revoking access while unfinished work remains assigned."""
        findings = AICatsAccessService.unfinished_assignment_summary(
            identity,
            module_code,
        )
        if findings:
            raise ValueError('请先转交未完成任务：' + '；'.join(findings))

    @staticmethod
    def set_scope_enabled(
        identity: AICatsUserIdentity,
        module_code: str,
        is_enabled: bool,
        operator: User,
    ) -> AICatsUserIdentityScope:
        """Enable or disable one valid module scope for an identity."""
        allowed_scopes = set(
            AI_CATS_IDENTITY_DEFINITIONS.get(identity.identity_code, {}).get(
                'default_scopes',
                (),
            )
        )
        if module_code not in allowed_scopes:
            raise ValueError('该身份不支持所选模块范围')
        before = AICatsAccessService._identity_snapshot(identity)
        scope = next(
            (item for item in identity.scopes if item.module_code == module_code),
            None,
        )
        if not scope:
            scope = AICatsUserIdentityScope(
                user_identity_id=identity.id,
                module_code=module_code,
            )
            db.session.add(scope)
        scope.is_enabled = bool(is_enabled)
        db.session.flush()
        AICatsAccessService.add_audit_log(
            identity.user,
            'scope_enabled' if is_enabled else 'scope_disabled',
            operator,
            identity_code=identity.identity_code,
            before_state=before,
            after_state=AICatsAccessService._identity_snapshot(identity),
        )
        return scope

    @staticmethod
    def set_account_enabled(
        user: User,
        is_enabled: bool,
        operator: User,
    ) -> AICatsAccountProfile:
        """Toggle AI CATS access without disabling a shared ERP account."""
        if not is_enabled:
            findings: list[str] = []
            for identity in AICatsAccessService.active_identity_rows(user):
                findings.extend(
                    AICatsAccessService.unfinished_assignment_summary(identity)
                )
            if findings:
                raise ValueError('请先转交未完成任务：' + '；'.join(dict.fromkeys(findings)))
        profile = AICatsAccessService.get_profile(user)
        if not profile:
            access_mode = (
                'ai_cats_only'
                if user.role and user.role.code in AI_CATS_LEGACY_ROLE_IDENTITY_MAP
                else 'shared'
            )
            profile = AICatsAccessService.ensure_profile(user, access_mode)
        before = json.dumps({'is_enabled': profile.is_enabled})
        profile.is_enabled = bool(is_enabled)
        if profile.access_mode == 'ai_cats_only':
            user.is_active = bool(is_enabled) and bool(
                AICatsUserIdentity.query.filter_by(
                    user_id=user.id,
                    status='active',
                ).first()
            )
        AICatsAccessService.add_audit_log(
            user,
            'account_enabled' if is_enabled else 'account_disabled',
            operator,
            before_state=before,
            after_state=json.dumps({'is_enabled': profile.is_enabled}),
        )
        return profile

    @staticmethod
    def eligible_users(identity_code: str, module_code: str) -> list[User]:
        """Return active users who can serve one identity in one module."""
        if identity_code not in AI_CATS_IDENTITY_CODES:
            return []
        return [
            user
            for user in User.query.filter_by(is_active=True).order_by(
                User.real_name.asc(),
                User.username.asc(),
            ).all()
            if AICatsAccessService.has_identity(user, identity_code, module_code)
            and not AICatsAccessService.is_manager(user)
        ]
