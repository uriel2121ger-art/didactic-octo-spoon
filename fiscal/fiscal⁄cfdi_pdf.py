"""Generate printable CFDI PDF representations using ReportLab."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Sequence

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet


def export_cfdi_pdf(cfdi: dict[str, Any], items: Sequence[dict[str, Any]], xml_data: str, filepath: str | Path) -> str:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(filepath), pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    elems = []

    title = f"CFDI {cfdi.get('serie', '')}{cfdi.get('folio', '')}"
    elems.append(Paragraph(title, styles["Title"]))
    elems.append(Paragraph(f"UUID: {cfdi.get('uuid', 'pendiente')}", styles["Normal"]))
    elems.append(Paragraph(f"Fecha timbrado: {cfdi.get('fecha', datetime.datetime.utcnow().isoformat())}", styles["Normal"]))
    elems.append(Spacer(1, 12))

    emitter = cfdi.get("emitter", {})
    receiver = cfdi.get("receiver", {})
    elems.append(Paragraph(f"Emisor: {emitter.get('razon_social', '')} ({emitter.get('rfc', '')})", styles["Heading4"]))
    elems.append(Paragraph(f"Receptor: {receiver.get('name', '')} ({receiver.get('rfc', '')})", styles["Normal"]))
    elems.append(Spacer(1, 8))

    data = [["Cant", "Clave", "Descripción", "Unitario", "Importe"]]
    for it in items:
        data.append(
            [
                f"{float(it.get('qty', 0)):.2f}",
                it.get("sku", ""),
                it.get("name", ""),
                f"{float(it.get('price', 0)):.2f}",
                f"{float(it.get('total', 0)):.2f}",
            ]
        )
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    elems.append(table)
    elems.append(Spacer(1, 12))

    totals = cfdi.get("totals", {})
    elems.append(Paragraph(f"Subtotal: ${totals.get('subtotal', 0):.2f}", styles["Normal"]))
    elems.append(Paragraph(f"Impuestos: ${totals.get('tax', 0):.2f}", styles["Normal"]))
    elems.append(Paragraph(f"Total: ${totals.get('total', 0):.2f}", styles["Heading4"]))
    elems.append(Spacer(1, 12))

    elems.append(Paragraph("Sellos", styles["Heading4"]))
    elems.append(Paragraph(f"Sello SAT: {cfdi.get('sello_sat', 'N/A')}", styles["Normal"]))
    elems.append(Paragraph(f"Certificado SAT: {cfdi.get('cert_sat', 'N/A')}", styles["Normal"]))
    elems.append(Spacer(1, 6))
    elems.append(Paragraph("XML adjunto para validación.", styles["Italic"]))

    doc.build(elems)
    return str(filepath)

__all__ = ["export_cfdi_pdf"]
