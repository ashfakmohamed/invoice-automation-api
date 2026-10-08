import hashlib
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from app.models import (
    AuditStep,
    InvoiceCreate,
    InvoiceResponse,
    InvoiceStatus,
    MetricsResponse,
)


class InvoicePipeline:
    def __init__(
        self,
        auto_approve_limit: Decimal = Decimal(10000),
        reject_limit: Decimal = Decimal(250000),
    ) -> None:
        self._auto_approve_limit = auto_approve_limit
        self._reject_limit = reject_limit
        self._invoices: dict[str, InvoiceResponse] = {}
        self._fingerprints: dict[str, str] = {}
        self._lock = RLock()

    def process(self, payload: InvoiceCreate) -> InvoiceResponse:
        with self._lock:
            fingerprint = self._fingerprint(payload)
            if original_id := self._fingerprints.get(fingerprint):
                duplicate = self._build_result(
                    payload=payload,
                    fingerprint=fingerprint,
                    status=InvoiceStatus.duplicate,
                    risk_score=100,
                    duplicate_of=original_id,
                )
                duplicate.audit.append(
                    self._step(
                        "deduplicate",
                        "duplicate",
                        f"matches previously processed invoice {original_id}",
                    )
                )
                self._invoices[duplicate.id] = duplicate
                return duplicate

            risk_score, reasons = self._risk_score(payload)
            status = self._route(payload.amount, risk_score)
            result = self._build_result(
                payload=payload,
                fingerprint=fingerprint,
                status=status,
                risk_score=risk_score,
            )
            result.audit.extend(
                [
                    self._step("normalize", "success", "text and currency normalized"),
                    self._step("validate", "success", "schema and business fields valid"),
                    self._step(
                        "risk",
                        "scored",
                        "; ".join(reasons) if reasons else "no risk rules triggered",
                    ),
                    self._step("route", status.value, self._route_detail(status)),
                ]
            )
            self._invoices[result.id] = result
            self._fingerprints[fingerprint] = result.id
            return result

    def get(self, invoice_id: str) -> InvoiceResponse | None:
        with self._lock:
            return self._invoices.get(invoice_id)

    def metrics(self) -> MetricsResponse:
        with self._lock:
            counts = Counter(invoice.status for invoice in self._invoices.values())
            return MetricsResponse(
                total=len(self._invoices),
                by_status={status: counts.get(status, 0) for status in InvoiceStatus},
            )

    def _risk_score(self, payload: InvoiceCreate) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        if not payload.po_number:
            score += 30
            reasons.append("purchase order missing (+30)")
        if payload.amount > self._reject_limit:
            score += 70
            reasons.append("amount exceeds rejection limit (+70)")
        elif payload.amount > self._auto_approve_limit:
            score += 30
            reasons.append("amount exceeds auto-approval limit (+30)")
        if payload.due_date < datetime.now(UTC).date():
            score += 20
            reasons.append("invoice is overdue (+20)")
        return min(score, 100), reasons

    def _route(self, amount: Decimal, risk_score: int) -> InvoiceStatus:
        if amount > self._reject_limit or risk_score >= 70:
            return InvoiceStatus.rejected
        if risk_score >= 30:
            return InvoiceStatus.manual_review
        return InvoiceStatus.auto_approved

    @staticmethod
    def _fingerprint(payload: InvoiceCreate) -> str:
        normalized = "|".join(
            [
                payload.vendor_name.casefold(),
                payload.invoice_number.casefold(),
                f"{payload.amount:.2f}",
                payload.currency,
            ]
        )
        return hashlib.sha256(normalized.encode()).hexdigest()

    @staticmethod
    def _build_result(
        payload: InvoiceCreate,
        fingerprint: str,
        status: InvoiceStatus,
        risk_score: int,
        duplicate_of: str | None = None,
    ) -> InvoiceResponse:
        return InvoiceResponse(
            id=str(uuid4()),
            status=status,
            risk_score=risk_score,
            fingerprint=fingerprint,
            duplicate_of=duplicate_of,
            audit=[],
            created_at=datetime.now(UTC),
            **payload.model_dump(),
        )

    @staticmethod
    def _step(stage: str, outcome: str, detail: str) -> AuditStep:
        return AuditStep(
            stage=stage, outcome=outcome, detail=detail, created_at=datetime.now(UTC)
        )

    @staticmethod
    def _route_detail(status: InvoiceStatus) -> str:
        messages = {
            InvoiceStatus.auto_approved: "eligible for straight-through processing",
            InvoiceStatus.manual_review: "queued for finance review",
            InvoiceStatus.rejected: "blocked by configured risk policy",
            InvoiceStatus.duplicate: "matches an existing invoice",
        }
        return messages[status]
