"""High-value route smoke tests."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/erp/",
        "/contract/list",
        "/contract/new",
        "/transaction/",
        "/transaction/new",
        "/product/",
        "/product/new",
        "/statement/generator",
        "/statement/list",
        "/theme/settings",
        "/backup/",
        "/department/",
        "/role/",
        "/user/",
        "/user/pending",
        "/auth/change-password",
    ],
)
def test_protected_pages_load_for_superadmin(client, login, base_data, path):
    """Superadmin should be able to open protected pages without server errors."""
    login(base_data["superadmin_id"])
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code in (200, 302)


@pytest.mark.parametrize(
    "path",
    [
        "/erp/",
        "/contract/list",
        "/transaction/",
        "/product/",
        "/statement/list",
        "/theme/settings",
        "/backup/",
        "/department/",
        "/role/",
        "/user/",
    ],
)
def test_protected_pages_redirect_without_login(client, path):
    """Anonymous users should be redirected to login for protected pages."""
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")
