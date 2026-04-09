"""Export and backup route tests."""

from __future__ import annotations

from pathlib import Path

from app.services.contract_service import ContractService


def test_contract_export_delivery_note_redirects_when_no_transactions(app, client, login, base_data):
    """Export delivery note should redirect when contract has no transactions."""
    with app.app_context():
        contract = ContractService.create_contract(
            {
                "contract_no": "EXPORT-NO-TX",
                "company_name": "Export Corp",
                "owner": "Sales - Owner",
                "department": "Sales",
                "manager": "Sales Owner",
                "created_by_id": base_data["owner_user_id"],
            },
            [
                {
                    "product_code": "EX-001",
                    "product_name": "Export Product",
                    "product_model": "E1",
                    "product_type": "TypeE",
                    "quantity": 5,
                    "unit": "pcs",
                    "price": 10,
                    "remark": "",
                }
            ],
        )
        contract_id = contract.id

    login(base_data["superadmin_id"])
    resp = client.get(f"/contract/{contract_id}/export-delivery-note", follow_redirects=False)
    assert resp.status_code == 302
    assert f"/contract/{contract_id}" in resp.headers.get("Location", "")


def test_backup_download_returns_zip(app, client, login, base_data, tmp_path, monkeypatch):
    """Backup download should produce a zip payload for authorized users."""
    import app.routes.backup as backup_routes

    data_dir = tmp_path / "data"
    uploads_dir = tmp_path / "uploads"
    exports_dir = tmp_path / "exports"
    backup_dir = tmp_path / "backups"
    for d in (data_dir, uploads_dir, exports_dir, backup_dir):
        d.mkdir(parents=True, exist_ok=True)

    (data_dir / "erp.db").write_text("fake-db", encoding="utf-8")
    (uploads_dir / "sample.txt").write_text("upload", encoding="utf-8")
    (exports_dir / "report.xlsx").write_text("export", encoding="utf-8")

    monkeypatch.setattr(backup_routes, "get_data_directory", lambda: str(data_dir))
    monkeypatch.setattr(backup_routes, "get_uploads_directory", lambda: str(uploads_dir))
    monkeypatch.setattr(backup_routes, "get_exports_directory", lambda: str(exports_dir))
    monkeypatch.setattr(backup_routes, "get_backup_directory", lambda: str(backup_dir))

    login(base_data["superadmin_id"])
    resp = client.get("/backup/download", follow_redirects=False)

    assert resp.status_code == 200
    assert "application/zip" in resp.headers.get("Content-Type", "")
    assert resp.data[:2] == b"PK"

    backup_files = list(Path(backup_dir).glob("erp_backup_*.zip"))
    assert backup_files
