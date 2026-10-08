from fastapi import FastAPI, HTTPException

from app.models import InvoiceCreate, InvoiceResponse, MetricsResponse
from app.pipeline import InvoicePipeline

pipeline = InvoicePipeline()
app = FastAPI(
    title="Invoice Automation API",
    description="Auditable invoice validation, risk scoring, and routing.",
    version="1.0.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/invoices", response_model=InvoiceResponse, status_code=201)
async def process_invoice(payload: InvoiceCreate) -> InvoiceResponse:
    return pipeline.process(payload)


@app.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(invoice_id: str) -> InvoiceResponse:
    invoice = pipeline.get(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.get("/metrics", response_model=MetricsResponse)
async def metrics() -> MetricsResponse:
    return pipeline.metrics()
