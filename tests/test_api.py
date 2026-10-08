from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def invoice(**overrides) -> dict:
    payload = {
        "vendor_name": "Example Supplies",
        "invoice_number": "INV-1001",
        "po_number": "PO-9001",
        "amount": "7500.00",
        "currency": "USD",
        "due_date": str(datetime.now(UTC).date() + timedelta(days=30)),
    }
    payload.update(overrides)
    return payload


def test_low_risk_invoice_is_auto_approved():
    response = client.post("/invoices", json=invoice(invoice_number="INV-AUTO"))
    assert response.status_code == 201
    assert response.json()["status"] == "auto_approved"
    assert response.json()["risk_score"] == 0


def test_missing_purchase_order_requires_manual_review():
    response = client.post(
        "/invoices", json=invoice(invoice_number="INV-REVIEW", po_number=None)
    )
    assert response.json()["status"] == "manual_review"
    assert response.json()["risk_score"] == 30


def test_extreme_amount_is_rejected():
    response = client.post(
        "/invoices", json=invoice(invoice_number="INV-REJECT", amount="300000.00")
    )
    assert response.json()["status"] == "rejected"


def test_duplicate_invoice_links_to_original():
    payload = invoice(invoice_number="INV-DUPLICATE")
    original = client.post("/invoices", json=payload).json()
    duplicate = client.post("/invoices", json=payload).json()
    assert duplicate["status"] == "duplicate"
    assert duplicate["duplicate_of"] == original["id"]


def test_invalid_currency_is_rejected_by_schema():
    response = client.post(
        "/invoices", json=invoice(invoice_number="INV-CURRENCY", currency="XYZ")
    )
    assert response.status_code == 422


def test_metrics_include_processed_statuses():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.json()["total"] >= 4
