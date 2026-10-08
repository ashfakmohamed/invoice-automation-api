from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class InvoiceStatus(StrEnum):
    auto_approved = "auto_approved"
    manual_review = "manual_review"
    rejected = "rejected"
    duplicate = "duplicate"


class InvoiceCreate(BaseModel):
    vendor_name: str = Field(min_length=2, max_length=160)
    invoice_number: str = Field(min_length=2, max_length=80)
    po_number: str | None = Field(default=None, max_length=80)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    due_date: date

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        currency = value.upper()
        if currency not in {"USD", "EUR", "GBP", "INR"}:
            raise ValueError("currency must be USD, EUR, GBP, or INR")
        return currency

    @field_validator("vendor_name", "invoice_number", "po_number")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class AuditStep(BaseModel):
    stage: str
    outcome: str
    detail: str
    created_at: datetime


class InvoiceResponse(InvoiceCreate):
    id: str
    status: InvoiceStatus
    risk_score: int = Field(ge=0, le=100)
    fingerprint: str
    duplicate_of: str | None = None
    audit: list[AuditStep]
    created_at: datetime


class MetricsResponse(BaseModel):
    total: int
    by_status: dict[InvoiceStatus, int]
