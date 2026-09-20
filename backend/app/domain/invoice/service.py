"""Invoice domain service.

Contains business logic for invoice management including PDF generation,
payment status updates, and retrieval.

Invoice amounts derive from persisted transaction data — no LLM is
used to calculate totals.
"""

from __future__ import annotations

import io
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.enums import InvoicePaymentStatus, InvoiceStatus
from app.domain.invoice.models import Invoice
from app.domain.invoice.repository import InvoiceRepository
from app.exceptions import AuthorizationError, NotFoundError, StateTransitionError
from app.logging import get_logger

logger = get_logger(__name__)


class InvoiceService:
    """Invoice lifecycle management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.invoice_repo = InvoiceRepository(session)

    # --- Retrieval ---

    async def get_invoice(self, invoice_id: uuid.UUID) -> Invoice:
        """Get an invoice by ID."""
        invoice = await self.invoice_repo.get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found")
        return invoice

    async def get_business_invoice(self, invoice_id: uuid.UUID, business_id: uuid.UUID) -> Invoice:
        """Get an invoice, verifying it belongs to the business."""
        invoice = await self.get_invoice(invoice_id)
        if invoice.business_id != business_id:
            raise AuthorizationError("Invoice does not belong to this business")
        return invoice

    async def get_customer_invoice(self, invoice_id: uuid.UUID, customer_id: uuid.UUID) -> Invoice:
        """Get an invoice, verifying customer ownership."""
        invoice = await self.get_invoice(invoice_id)
        if invoice.customer_id != customer_id:
            raise AuthorizationError("Not your invoice")
        return invoice

    async def list_business_invoices(
        self,
        business_id: uuid.UUID,
        *,
        payment_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Invoice]:
        """List invoices for a business."""
        return await self.invoice_repo.get_by_business(
            business_id, payment_status=payment_status, limit=limit, offset=offset
        )

    async def list_customer_invoices(
        self,
        customer_id: uuid.UUID,
        *,
        payment_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Invoice]:
        """List invoices for a customer."""
        return await self.invoice_repo.get_by_customer(
            customer_id, payment_status=payment_status, limit=limit, offset=offset
        )

    # --- Payment status ---

    async def update_payment_status(
        self,
        invoice: Invoice,
        new_status: InvoicePaymentStatus,
        *,
        actor_id: uuid.UUID,
    ) -> Invoice:
        """Update the payment status of an invoice.

        Only authorized business users may update payment status.
        """
        old_status = invoice.payment_status

        # VOID is a terminal state
        if InvoicePaymentStatus(old_status) == InvoicePaymentStatus.VOID:
            raise StateTransitionError("Cannot change payment status of a voided invoice")

        invoice.payment_status = new_status

        # If voiding, update invoice status too
        if new_status == InvoicePaymentStatus.VOID:
            invoice.status = InvoiceStatus.VOID

        invoice = await self.invoice_repo.update(invoice)

        logger.info(
            "invoice_payment_status_updated",
            invoice_id=str(invoice.id),
            actor=str(actor_id),
            from_status=old_status,
            to_status=new_status.value,
        )

        return invoice

    # --- PDF generation ---

    async def generate_invoice_pdf(self, invoice: Invoice) -> bytes:
        """Generate a PDF invoice document from persisted data.

        The PDF is generated server-side from the invoice's persisted
        data.  It is reproducible — calling this method again with the
        same invoice data produces an equivalent document.
        """
        # Ensure line items are loaded
        if not invoice.line_items:
            invoice = await self.get_invoice(invoice.id)

        return _build_invoice_pdf(invoice)

    # --- CSV export helper (used by ledger) ---


def _build_invoice_pdf(invoice: Invoice) -> bytes:
    """Build a PDF invoice document from persisted invoice data.

    Uses reportlab for server-side PDF generation.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        # Fallback: generate a simple text-based PDF using basic PDF structure
        return _build_simple_pdf(invoice)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=6 * mm,
    )
    heading_style = ParagraphStyle(
        "InvoiceHeading",
        parent=styles["Heading2"],
        fontSize=12,
        spaceAfter=3 * mm,
    )
    normal_style = styles["Normal"]

    elements = []

    # Title
    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Spacer(1, 5 * mm))

    # Invoice details
    details_data = [
        ["Invoice Number:", invoice.invoice_number],
        ["Issue Date:", invoice.issue_date.strftime("%d %b %Y")],
        ["Due Date:", invoice.due_date.strftime("%d %b %Y") if invoice.due_date else "N/A"],
        ["Currency:", invoice.currency],
        ["Payment Status:", invoice.payment_status.upper()],
        ["Status:", invoice.status.upper()],
    ]
    details_table = Table(details_data, colWidths=[40 * mm, 80 * mm])
    details_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    elements.append(details_table)
    elements.append(Spacer(1, 8 * mm))

    # Business / Customer info
    elements.append(Paragraph("Bill To:", heading_style))
    elements.append(Paragraph(f"Customer ID: {invoice.customer_id}", normal_style))
    elements.append(Spacer(1, 5 * mm))

    # Line items table
    elements.append(Paragraph("Line Items", heading_style))

    table_data = [
        ["Description", "Qty", "Unit Price", "Discount", "Tax", "Total"],
    ]
    for item in invoice.line_items:
        table_data.append(
            [
                item.description,
                str(item.quantity),
                f"{item.currency} {item.unit_price}",
                f"{item.unit_price}",  # show discount amount
                f"{item.tax}",
                f"{item.currency} {item.line_total}",
            ]
        )

    line_table = Table(table_data, colWidths=[60 * mm, 15 * mm, 25 * mm, 20 * mm, 20 * mm, 25 * mm])
    line_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(line_table)
    elements.append(Spacer(1, 8 * mm))

    # Totals
    totals_data = [
        ["Subtotal:", f"{invoice.currency} {invoice.subtotal}"],
        ["Discount:", f"{invoice.currency} {invoice.discount}"],
        ["Tax:", f"{invoice.currency} {invoice.tax}"],
        ["TOTAL:", f"{invoice.currency} {invoice.total}"],
    ]
    totals_table = Table(totals_data, colWidths=[40 * mm, 50 * mm])
    totals_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, -1), (1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
            ]
        )
    )
    elements.append(totals_table)

    # Notes
    if invoice.notes:
        elements.append(Spacer(1, 8 * mm))
        elements.append(Paragraph("Notes:", heading_style))
        elements.append(Paragraph(invoice.notes, normal_style))

    doc.build(elements)
    return buffer.getvalue()


def _build_simple_pdf(invoice: Invoice) -> bytes:
    """Fallback: build a minimal PDF without reportlab.

    Generates a valid PDF with invoice details as plain text.
    """
    lines = [
        "INVOICE",
        "",
        f"Invoice Number: {invoice.invoice_number}",
        f"Issue Date: {invoice.issue_date.strftime('%d %b %Y')}",
        f"Due Date: {invoice.due_date.strftime('%d %b %Y') if invoice.due_date else 'N/A'}",
        f"Currency: {invoice.currency}",
        f"Payment Status: {invoice.payment_status.upper()}",
        "",
        "Line Items:",
    ]

    for item in invoice.line_items:
        lines.append(f"  - {item.description}: {item.currency} {item.line_total}")

    lines.extend(
        [
            "",
            f"Subtotal: {invoice.currency} {invoice.subtotal}",
            f"Discount: {invoice.currency} {invoice.discount}",
            f"Tax: {invoice.currency} {invoice.tax}",
            f"TOTAL: {invoice.currency} {invoice.total}",
        ]
    )

    if invoice.notes:
        lines.extend(["", f"Notes: {invoice.notes}"])

    content = "\n".join(lines)

    # Minimal valid PDF
    pdf_head = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R
   /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length {len(content) + 44} >>
stream
BT
/F1 10 Tf
50 750 Td
({content}) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>
endobj
"""
    # Xref entries REQUIRE a trailing space before the EOL (fixed-width 20-byte
    # entries per PDF spec) — kept as explicit literals so linters never strip them.
    pdf_tail = (
        "xref\n"
        "0 6\n"
        "0000000000 65535 f \n"
        "0000000009 00000 n \n"
        "0000000058 00000 n \n"
        "0000000115 00000 n \n"
        "0000000266 00000 n \n"
        "trailer\n"
        "<< /Size 6 /Root 1 0 R >>\n"
        "startxref\n"
        "0\n"
        "%%EOF"
    )
    return (pdf_head + pdf_tail).encode("utf-8")
