"""Database schema integrity checks for key business tables."""

from __future__ import annotations

from sqlalchemy import text


def _columns(db_session, table_name: str):
    rows = db_session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def test_contract_related_tables_have_required_columns(db_session):
    """Core contract tables must expose required fields."""
    contract_cols = _columns(db_session, "contracts")
    tx_cols = _columns(db_session, "transactions")
    pay_cols = _columns(db_session, "payment_records")

    assert {"contract_no", "company_name", "delivery_status", "payment_status", "created_by_id"} <= contract_cols
    assert {"contract_id", "contract_product_id", "product_code", "handler", "delivery_date"} <= tx_cols
    assert {"contract_id", "contract_product_id", "payment_amount", "invoice_amount", "payment_date"} <= pay_cols
    assert "delivery_batch_no" in tx_cols


def test_formal_contract_tables_have_party_snapshot_columns(db_session):
    """Formal contracts must preserve the party-A data used at save time."""
    formal_cols = _columns(db_session, "formal_contracts")
    template_cols = _columns(db_session, "formal_contract_templates")
    assert {
        "party_id",
        "department_id",
        "party_a_billing_address",
        "party_a_phone",
        "party_a_tax_no",
        "party_a_bank_name",
        "party_a_bank_account",
    } <= formal_cols
    assert {"department_id"} <= template_cols


def test_transaction_table_has_no_legacy_payment_date_column(db_session):
    """v1.3 split should keep payment date in payment_records, not transactions."""
    tx_cols = _columns(db_session, "transactions")
    assert "payment_date" not in tx_cols


def test_payment_record_amount_and_date_fields_are_optional(db_session):
    """Invoice-only rows require nullable payment amount/date columns."""
    rows = db_session.execute(text("PRAGMA table_info(payment_records)")).fetchall()
    column_info = {row[1]: row for row in rows}

    assert column_info["payment_amount"][3] == 0
    assert column_info["payment_date"][3] == 0


def test_qc_production_tables_have_type_stock_and_history_columns(db_session):
    """AI CATS production tables must support workpiece types, inventory and immutable history."""
    workpiece_cols = _columns(db_session, "qc_workpieces")
    order_cols = _columns(db_session, "qc_work_orders")
    history_cols = _columns(db_session, "qc_work_order_histories")
    stock_history_cols = _columns(db_session, "qc_workpiece_stock_histories")

    assert {"workpiece_type", "stock_quantity"} <= workpiece_cols
    assert {"workpiece_type", "inventory_posted_at"} <= order_cols
    assert {
        "assembly_order_id",
        "assembly_acceptance_batch_id",
        "outbound_order_id",
        "outbound_batch_id",
    } <= stock_history_cols
    assert {"work_order_id", "operator_id", "action", "detail", "created_at"} <= history_cols


def test_research_module_tables_have_required_columns(db_session):
    """AI CATS research tables must expose the Phase 1 foundation columns."""
    project_cols = _columns(db_session, "research_projects")
    project_attachment_cols = _columns(db_session, "research_project_attachments")
    batch_cols = _columns(db_session, "research_batches")
    batch_attachment_cols = _columns(db_session, "research_batch_attachments")
    review_cols = _columns(db_session, "research_review_records")
    signature_cols = _columns(db_session, "research_acceptance_signatures")
    history_cols = _columns(db_session, "research_batch_histories")

    assert {"project_code", "project_name", "project_category", "creator_id"} <= project_cols
    assert {"project_id", "attach_type", "file_path", "sort_order"} <= project_attachment_cols
    assert {"batch_no", "project_id", "researcher_id", "reviewer_id", "status"} <= batch_cols
    assert {"batch_id", "attach_type", "source_type", "file_path"} <= batch_attachment_cols
    assert {"batch_id", "reviewer_id", "attachment_id", "result"} <= review_cols
    assert {"batch_id", "signer_id", "signer_role", "signed_at"} <= signature_cols
    assert {"batch_id", "operator_id", "action", "detail", "created_at"} <= history_cols


def test_assembly_module_tables_have_required_columns(db_session):
    """AI CATS assembly/shipping tables must expose the required foundation columns."""
    product_cols = _columns(db_session, "assembly_products")
    component_cols = _columns(db_session, "assembly_product_components")
    product_attachment_cols = _columns(db_session, "assembly_product_attachments")
    product_stock_history_cols = _columns(db_session, "assembly_product_stock_histories")
    order_cols = _columns(db_session, "assembly_orders")
    order_component_cols = _columns(db_session, "assembly_order_components")
    order_attachment_cols = _columns(db_session, "assembly_order_attachments")
    inspection_cols = _columns(db_session, "assembly_inspection_records")
    signature_cols = _columns(db_session, "assembly_acceptance_signatures")
    history_cols = _columns(db_session, "assembly_order_histories")

    assert {"product_code", "product_name", "creator_id"} <= product_cols
    assert {"product_id", "workpiece_id", "workpiece_code_snapshot", "quantity_per_unit"} <= component_cols
    assert {"product_id", "attach_type", "file_path", "sort_order"} <= product_attachment_cols
    assert {
        "product_id",
        "assembly_order_id",
        "assembly_acceptance_batch_id",
        "outbound_order_id",
        "outbound_batch_id",
        "change_type",
        "quantity_delta",
        "stock_before",
        "stock_after",
    } <= product_stock_history_cols
    assert {"batch_no", "product_id", "controller_id", "status", "inventory_posted_at"} <= order_cols
    assert {"order_id", "workpiece_id", "quantity_per_unit", "total_required_quantity"} <= order_component_cols
    assert {"order_id", "attach_type", "source_type", "file_path"} <= order_attachment_cols
    assert {"order_id", "inspector_id", "attachment_id", "result"} <= inspection_cols
    assert {"order_id", "signer_id", "signer_role", "signed_at"} <= signature_cols
    assert {"order_id", "operator_id", "action", "detail", "created_at"} <= history_cols
