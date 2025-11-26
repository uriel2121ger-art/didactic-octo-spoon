"""PDF export helpers for POS reports using ReportLab."""
from __future__ import annotations

import datetime as dt
from typing import Iterable, List, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _build_table(headers: Sequence[str], rows: Iterable[Sequence]) -> Table:
    data: List[List[str]] = [list(headers)] + [list(map(str, r)) for r in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ]
        )
    )
    return table


def _export_table_doc(title: str, headers: Sequence[str], rows: Iterable[Sequence], filepath: str) -> None:
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Heading1"]), Spacer(1, 12)]
    story.append(Paragraph(dt.datetime.now().strftime("%Y-%m-%d %H:%M"), styles["Normal"]))
    story.append(Spacer(1, 12))
    story.append(_build_table(headers, rows))
    doc = SimpleDocTemplate(filepath, pagesize=letter, leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    doc.build(story)


def export_sales_summary_pdf(data: dict, filepath: str) -> None:
    headers = ["Fecha", "Subtotal", "IVA", "Total", "Cliente", "Pago"]
    rows = data.get("rows", [])
    _export_table_doc("Resumen de ventas", headers, rows, filepath)


def export_top_products_pdf(data: dict, filepath: str) -> None:
    headers = ["Producto", "Cantidad", "Total", "% del Total"]
    rows = data.get("rows", [])
    _export_table_doc("Productos más vendidos", headers, rows, filepath)


def export_daily_sales_pdf(data: dict, filepath: str) -> None:
    headers = ["Día", "Total"]
    rows = data.get("rows", [])
    _export_table_doc("Ventas por día", headers, rows, filepath)


def export_credit_report_pdf(data: dict, filepath: str) -> None:
    headers = ["Cliente", "Saldo", "Límite"]
    rows = data.get("rows", [])
    _export_table_doc("Créditos y cuentas por cobrar", headers, rows, filepath)


def export_layaway_report_pdf(data: dict, filepath: str) -> None:
    headers = ["ID", "Cliente", "Fecha", "Total", "Pagado", "Saldo", "Estado"]
    rows = data.get("rows", [])
    _export_table_doc("Apartados", headers, rows, filepath)


def export_turn_report_pdf(data: dict, filepath: str) -> None:
    headers = ["Concepto", "Monto"]
    rows = data.get("rows", [])
    _export_table_doc("Caja / turno", headers, rows, filepath)


def export_credit_statement_pdf(statement_data: dict, filepath: str) -> None:
    customer = statement_data.get("customer") or {}
    title = f"Estado de cuenta de {customer.get('full_name') or customer.get('first_name','Cliente')}"
    headers = ["Fecha", "Descripción", "Cargo", "Abono", "Saldo"]
    rows = []
    for mv in statement_data.get("movements", []):
        rows.append(
            [
                mv.get("date"),
                mv.get("description"),
                f"{float(mv.get('debit', 0.0) or 0.0):.2f}",
                f"{float(mv.get('credit', 0.0) or 0.0):.2f}",
                f"{float(mv.get('balance_after', 0.0) or 0.0):.2f}",
            ]
        )
    _export_table_doc(title, headers, rows, filepath)
