"""Service Ledger domain service.

Contains business logic for the operational service ledger including
listing, summaries, CSV/PDF export, and adjustments.

The ledger is an OPERATIONAL SERVICE LEDGER — not a statutory
accounting/general ledger replacement.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ledger.models import ServiceLedgerEntry
from app.domain.ledger.repository import LedgerRepository
from app.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.logging import get_logger

logger = get_logger(__name__)


class LedgerService:
    """Operational service ledger management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.ledger_repo = LedgerRepository(session)

    # --- Retrieval ---

    async def get_entry(self, entry_id: uuid.UUID) -> ServiceLedgerEntry:
        """Get a ledger entry by ID."""
        entry = await self.ledger_repo.get_by_id(entry_id)
        if entry is None:
            raise NotFoundError("Ledger entry not found")
        return entry

    async def get_business_entry(
        self, entry_id: uuid.UUID, business_id: uuid.UUID
    ) -> ServiceLedgerEntry:
        """Get a ledger entry, verifying it belongs to the business."""
        entry = await self.get_entry(entry_id)
        if entry.business_id != business_id:
            raise AuthorizationError("Ledger entry does not belong to this business")
        return entry

    async def list_entries(
        self,
        business_id: uuid.UUID,
        *,
        payment_status: str | None = None,
        service_offer_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ServiceLedgerEntry]:
        """List ledger entries for a business with filters."""
        return await self.ledger_repo.get_by_business(
            business_id,
            payment_status=payment_status,
            service_offer_id=service_offer_id,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

    async def get_summary(
        self,
        business_id: uuid.UUID,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict:
        """Get ledger summary/totals for a business."""
        return await self.ledger_repo.get_summary(
            business_id, date_from=date_from, date_to=date_to
        )

    # --- Export ---

    async def export_csv(
        self,
        business_id: uuid.UUID,
        *,
        payment_status: str | None = None,
        service_offer_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> str:
        """Export ledger entries as CSV.

        Uses actual persisted data.  Respects filters and tenant
        authorization.  Includes totals and export metadata.
        """
        entries = await self.ledger_repo.get_by_business(
            business_id,
            payment_status=payment_status,
            service_offer_id=service_offer_id,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            limit=10000,  # Large limit for export
            offset=0,
        )

        output = io.StringIO()
        writer = csv.writer(output)

        # Header with metadata
        writer.writerow(["FIELDed — Operational Service Ledger"])
        writer.writerow([f"Business ID: {business_id}"])
        if date_from:
            writer.writerow([f"From: {date_from.isoformat()}"])
        if date_to:
            writer.writerow([f"To: {date_to.isoformat()}"])
        if payment_status:
            writer.writerow([f"Payment Status: {payment_status}"])
        writer.writerow([f"Export Date: {datetime.now().isoformat()}"])
        writer.writerow([])

        # Column headers
        writer.writerow([
            "Date",
            "Service",
            "Customer ID",
            "Booking ID",
            "Invoice ID",
            "Gross Amount",
            "Discount",
            "Tax",
            "Net Amount",
            "Currency",
            "Payment Status",
            "Transaction Reference",
        ])

        # Data rows
        total_gross = Decimal("0")
        total_discount = Decimal("0")
        total_tax = Decimal("0")
        total_net = Decimal("0")

        for entry in entries:
            writer.writerow([
                entry.completion_date.strftime("%Y-%m-%d %H:%M") if entry.completion_date else "",
                str(entry.service_offer_id),
                str(entry.customer_id),
                str(entry.booking_id),
                str(entry.invoice_id) if entry.invoice_id else "",
                str(entry.gross_amount),
                str(entry.discount),
                str(entry.tax),
                str(entry.net_amount),
                entry.currency,
                entry.payment_status,
                entry.transaction_reference or "",
            ])
            total_gross += Decimal(str(entry.gross_amount))
            total_discount += Decimal(str(entry.discount))
            total_tax += Decimal(str(entry.tax))
            total_net += Decimal(str(entry.net_amount))

        # Totals row
        writer.writerow([])
        writer.writerow([
            "TOTALS",
            "",
            "",
            "",
            "",
            str(total_gross),
            str(total_discount),
            str(total_tax),
            str(total_net),
            "",
            "",
            "",
        ])
        writer.writerow([f"Total Entries: {len(entries)}"])

        return output.getvalue()

    async def export_pdf(
        self,
        business_id: uuid.UUID,
        *,
        payment_status: str | None = None,
        service_offer_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> bytes:
        """Export ledger as PDF report.

        Uses actual persisted data.  Server-side generation.
        """
        entries = await self.ledger_repo.get_by_business(
            business_id,
            payment_status=payment_status,
            service_offer_id=service_offer_id,
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
            limit=10000,
            offset=0,
        )

        summary = await self.ledger_repo.get_summary(
            business_id, date_from=date_from, date_to=date_to
        )

        return _build_ledger_pdf(business_id, entries, summary, date_from, date_to)

    # --- Adjustments ---

    async def create_adjustment(
        self,
        *,
        business_id: uuid.UUID,
        original_entry_id: uuid.UUID,
        adjustment_gross: str,
        adjustment_discount: str,
        adjustment_tax: str,
        adjustment_net: str,
        currency: str,
        notes: str,
        actor_id: uuid.UUID,
    ) -> ServiceLedgerEntry:
        """Create an adjustment/reversal ledger entry.

        Uses append-oriented mechanism — the original entry is not
        modified.  A new entry is created that references the original.
        """
        original = await self.get_business_entry(original_entry_id, business_id)

        if not original.is_primary:
            raise ValidationError("Can only adjust primary ledger entries")

        tx_ref = f"ADJ-{uuid.uuid4().hex[:12].upper()}"

        adjustment = ServiceLedgerEntry(
            business_id=business_id,
            customer_id=original.customer_id,
            service_execution_id=original.service_execution_id,
            booking_id=original.booking_id,
            quote_id=original.quote_id,
            invoice_id=original.invoice_id,
            service_offer_id=original.service_offer_id,
            completion_date=datetime.now(),
            gross_amount=adjustment_gross,
            discount=adjustment_discount,
            tax=adjustment_tax,
            net_amount=adjustment_net,
            currency=currency,
            payment_status=original.payment_status,
            is_primary=False,
            adjusts_entry_id=original.id,
            transaction_reference=tx_ref,
            notes=notes,
        )
        adjustment = await self.ledger_repo.create(adjustment)

        logger.info(
            "ledger_adjustment_created",
            adjustment_id=str(adjustment.id),
            original_entry_id=str(original_entry_id),
            actor=str(actor_id),
            transaction_reference=tx_ref,
        )

        return adjustment


def _build_ledger_pdf(
    business_id: uuid.UUID,
    entries: list[ServiceLedgerEntry],
    summary: dict,
    date_from: datetime | None,
    date_to: datetime | None,
) -> bytes:
    """Build a PDF ledger report.

    Attempts to use reportlab; falls back to a minimal PDF.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )

        styles = getSampleStyleSheet()
        elements = []

        # Title
        elements.append(Paragraph("Operational Service Ledger", styles["Title"]))
        elements.append(Spacer(1, 3 * mm))
        elements.append(Paragraph(f"Business: {business_id}", styles["Normal"]))
        if date_from or date_to:
            period = f"Period: {date_from or '...'} to {date_to or '...'}"
            elements.append(Paragraph(period, styles["Normal"]))
        elements.append(Spacer(1, 5 * mm))

        # Summary
        summary_data = [
            ["Total Services:", summary["total_entries"]],
            ["Total Gross:", summary["total_gross"]],
            ["Total Discount:", summary["total_discount"]],
            ["Total Tax:", summary["total_tax"]],
            ["Total Net:", summary["total_net"]],
            ["Paid:", summary["paid_amount"]],
            ["Outstanding:", summary["outstanding_amount"]],
        ]
        summary_table = Table(summary_data, colWidths=[35 * mm, 50 * mm])
        summary_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 5 * mm))

        # Entries table
        table_data = [
            ["Date", "Service", "Customer", "Invoice", "Gross", "Discount", "Tax", "Net", "Currency", "Status"],
        ]
        for entry in entries:
            table_data.append([
                entry.completion_date.strftime("%Y-%m-%d") if entry.completion_date else "",
                str(entry.service_offer_id)[:8],
                str(entry.customer_id)[:8],
                str(entry.invoice_id)[:8] if entry.invoice_id else "",
                str(entry.gross_amount),
                str(entry.discount),
                str(entry.tax),
                str(entry.net_amount),
                entry.currency,
                entry.payment_status,
            ])

        col_widths = [22 * mm, 25 * mm, 25 * mm, 25 * mm, 20 * mm, 18 * mm, 18 * mm, 20 * mm, 18 * mm, 22 * mm]
        entry_table = Table(table_data, colWidths=col_widths)
        entry_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ]))
        elements.append(entry_table)

        doc.build(elements)
        return buffer.getvalue()

    except ImportError:
        # Fallback: minimal PDF
        content = f"FIELDed Operational Service Ledger\nBusiness: {business_id}\nEntries: {len(entries)}\n"
        pdf = f"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length {len(content) + 44}>>
stream
BT /F1 10 Tf 50 750 Td ({content}) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Courier>>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
trailer<</Size 6/Root 1 0 R>>
startxref 0
%%EOF"""
        return pdf.encode("utf-8")
