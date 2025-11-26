"""Ticket rendering helpers for POS payments and hardware hooks."""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable

logger = logging.getLogger(__name__)


def _format_currency(amount: float) -> str:
    return f"${float(amount):,.2f}"


def render_payment_lines(payment_breakdown: Dict[str, Any]) -> list[str]:
    """Return text lines describing the payment used in the sale."""

    lines: list[str] = []
    method = payment_breakdown.get("method")
    if method == "mixed":
        lines.append("*PAGO MIXTO*")
        breakdown = payment_breakdown.get("breakdown", {}) or {}
        for key, value in breakdown.items():
            if key == "card" and isinstance(value, dict):
                lines.append(f"Tarjeta: {_format_currency(value.get('amount', 0))}")
                if value.get("reference"):
                    lines.append(f"Ref: {value['reference']}")
                if value.get("card_fee"):
                    lines.append(f"Comisión: {_format_currency(value['card_fee'])}")
            elif key == "transfer" and isinstance(value, dict):
                lines.append(f"Transferencia: {_format_currency(value.get('amount', 0))}")
                if value.get("reference"):
                    lines.append(f"Ref: {value['reference']}")
            elif key == "usd" and isinstance(value, dict):
                usd_amount = float(value.get("usd_amount") or 0)
                usd_exchange = float(value.get("usd_exchange") or 0)
                lines.append(f"USD: {usd_amount:.2f} TC {usd_exchange:.4f}")
            elif key == "check" and isinstance(value, dict):
                lines.append(f"Cheque: {_format_currency(value.get('amount', 0))}")
                if value.get("check_number"):
                    lines.append(f"No: {value['check_number']}")
            elif key in ("voucher", "vouchers"):
                amount = value.get("amount") if isinstance(value, dict) else value
                lines.append(f"Vales: {_format_currency(amount or 0)}")
            elif key == "cash":
                amount = value.get("amount") if isinstance(value, dict) else value
                lines.append(f"Efectivo: {_format_currency(amount or 0)}")
    else:
        header_map = {
            "cash": "PAGO EN EFECTIVO",
            "card": "PAGO CON TARJETA",
            "transfer": "PAGO CON TRANSFERENCIA",
            "usd": "PAGO EN DÓLARES",
            "voucher": "PAGO CON VALES",
            "vouchers": "PAGO CON VALES",
            "check": "PAGO CON CHEQUE",
            "credit": "VENTA A CRÉDITO",
        }
        if method in header_map:
            lines.append(f"*{header_map[method]}*")
        amount = payment_breakdown.get("amount") or payment_breakdown.get("paid_amount") or payment_breakdown.get("cash")
        if method == "card":
            if payment_breakdown.get("reference"):
                lines.append(f"Ref: {payment_breakdown['reference']}")
            if payment_breakdown.get("card_fee"):
                lines.append(f"Comisión: {_format_currency(payment_breakdown['card_fee'])}")
        if method == "transfer" and payment_breakdown.get("reference"):
            lines.append(f"Ref: {payment_breakdown['reference']}")
        if method == "usd":
            usd_amount = float(payment_breakdown.get("usd_amount") or 0)
            usd_exchange = float(payment_breakdown.get("usd_exchange") or 0)
            lines.append(f"USD: {usd_amount:.2f} TC {usd_exchange:.4f}")
        if method == "check" and payment_breakdown.get("check_number"):
            lines.append(f"No. cheque: {payment_breakdown['check_number']}")
        if method == "voucher" and payment_breakdown.get("voucher_amount"):
            amount = payment_breakdown.get("voucher_amount")
        if amount:
            lines.append(f"Monto: {_format_currency(float(amount))}")
        if method == "credit":
            lines.append("Saldo abonado al crédito del cliente")
    return lines


def print_credit_sale(customer_name: str, total: float, new_balance: float) -> list[str]:
    """Return printable lines for a credit sale ticket."""

    lines = ["VENTA A CRÉDITO", f"Cliente: {customer_name}", f"Monto: {_format_currency(total)}"]
    lines.append(f"Nuevo saldo: {_format_currency(new_balance)}")
    return lines


def print_credit_payment(customer_name: str, amount: float, new_balance: float, notes: str | None = None) -> list[str]:
    """Return printable lines for a credit payment receipt."""

    lines = ["ABONO A CRÉDITO", f"Cliente: {customer_name}", f"Monto: {_format_currency(amount)}"]
    lines.append(f"Saldo actualizado: {_format_currency(new_balance)}")
    if notes:
        lines.append(f"Notas: {notes}")
    return lines


def print_layaway_create(layaway: Dict[str, Any], items: Iterable[Dict[str, Any]]) -> list[str]:
    """Return printable lines for a layaway creation ticket."""

    lines = [
        "APARTADO GENERADO",
        f"Cliente: {layaway.get('customer_name') or 'Sin cliente'}",
        f"Fecha: {layaway.get('created_at', '')}",
    ]
    lines.append(f"Total: {_format_currency(layaway.get('total', 0))}")
    lines.append(f"Depósito: {_format_currency(layaway.get('deposit', 0))}")
    lines.append(f"Saldo: {_format_currency(layaway.get('balance', layaway.get('balance_calc', 0)))}")
    lines.append("--- Productos ---")
    for item in items:
        qty = float(item.get("qty", 0))
        price = float(item.get("price", 0))
        lines.append(f"{qty:.2f} x {_format_currency(price)}  {item.get('name','')}")
    return lines


def print_layaway_payment(layaway: Dict[str, Any], payment: Dict[str, Any]) -> list[str]:
    """Return printable lines for a layaway payment receipt."""

    lines = [
        "ABONO DE APARTADO",
        f"Cliente: {layaway.get('customer_name') or 'Sin cliente'}",
        f"Monto: {_format_currency(payment.get('amount', 0))}",
    ]
    if payment.get("notes"):
        lines.append(f"Notas: {payment['notes']}")
    new_balance = max(float(layaway.get("balance_calc", layaway.get("balance", 0))) - float(payment.get("amount", 0)), 0)
    lines.append(f"Saldo actualizado: {_format_currency(new_balance)}")
    return lines


def print_layaway_liquidation(layaway: Dict[str, Any]) -> list[str]:
    """Return printable lines for a layaway liquidation ticket."""

    lines = [
        "LIQUIDACIÓN DE APARTADO",
        f"Cliente: {layaway.get('customer_name') or 'Sin cliente'}",
        f"Total: {_format_currency(layaway.get('total', 0))}",
        "Estado: Liquidado",
    ]
    return lines


def print_backup_report(details: Dict[str, Any]) -> list[str]:
    """Return printable lines summarizing a backup event."""

    lines = ["RESPALDO GENERADO", f"Fecha: {details.get('created_at','')}"]
    if details.get("filename"):
        lines.append(f"Archivo: {details['filename']}")
    if details.get("sha256"):
        lines.append(f"SHA256: {details['sha256'][:16]}…")
    lines.append(f"Tamaño: {int(details.get('size_bytes',0))} bytes")
    locs = []
    for key, label in (("storage_local", "Local"), ("storage_nas", "NAS"), ("storage_cloud", "Nube")):
        if details.get(key):
            locs.append(label)
    lines.append(f"Ubicación: {', '.join(locs) if locs else 'Local'}")
    return lines


# ---------------------------------------------------------------------------
# Hardware helpers


def print_ticket(text: str, printer_name: str | None = None) -> None:
    """Send plain-text ticket to CUPS via ``lp`` without blocking the UI."""

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write(text)
            tmp_path = Path(tmp.name)
        cmd = ["lp"]
        if printer_name:
            cmd.extend(["-d", printer_name])
        if tmp_path:
            cmd.append(str(tmp_path))
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo enviar el ticket a imprimir")
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:  # noqa: BLE001
                logger.debug("No se pudo eliminar el ticket temporal %s", tmp_path)


def open_cash_drawer(printer_name: str | None, pulse_bytes: bytes) -> None:
    """Trigger cash drawer pulse via the configured printer using CUPS."""

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", delete=False) as tmp:
            tmp.write(pulse_bytes)
            tmp_path = Path(tmp.name)
        cmd = ["lp", "-o", "raw"]
        if printer_name:
            cmd.extend(["-d", printer_name])
        if tmp_path:
            cmd.append(str(tmp_path))
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        logger.exception("No se pudo abrir el cajón de dinero")
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:  # noqa: BLE001
                logger.debug("No se pudo eliminar el archivo temporal del cajón %s", tmp_path)


def build_escpos_bytes(ticket_data: Dict[str, Any]) -> bytes:
    """Return ESC/POS bytes skeleton for future raw printing.

    The implementation keeps it minimal: initialize, render lines, feed, and
    perform a partial cut. Extend this as needed for specific printer models.
    """

    lines = ticket_data.get("lines", []) if isinstance(ticket_data, dict) else []
    buffer = bytearray()
    buffer.extend(b"\x1b@")  # Initialize
    for line in lines:
        buffer.extend(str(line).encode("latin1", errors="ignore"))
        buffer.extend(b"\n")
    buffer.extend(b"\n\n")
    buffer.extend(b"\x1dV\x42\x00")  # Partial cut
    return bytes(buffer)


def print_sale_card(reference: str, fee: float = 0.0, amount: float | None = None) -> list[str]:
    return render_payment_lines({"method": "card", "reference": reference, "card_fee": fee, "amount": amount})


def print_sale_transfer(reference: str, amount: float | None = None) -> list[str]:
    return render_payment_lines({"method": "transfer", "reference": reference, "amount": amount})


def print_sale_usd(usd_given: float, exchange_rate: float) -> list[str]:
    return render_payment_lines({"method": "usd", "usd_amount": usd_given, "usd_exchange": exchange_rate})


def print_sale_check(check_number: str, amount: float | None = None) -> list[str]:
    return render_payment_lines({"method": "check", "check_number": check_number, "amount": amount})


def print_sale_vouchers(amount: float) -> list[str]:
    return render_payment_lines({"method": "vouchers", "voucher_amount": amount, "amount": amount})


def print_sale_mixed(breakdown: Dict[str, Any]) -> list[str]:
    return render_payment_lines({"method": "mixed", "breakdown": breakdown})


def print_turn_open(turn: Dict[str, Any]) -> list[str]:
    lines = [
        "APERTURA DE TURNO",
        f"Turno: {turn.get('id','')}",
        f"Usuario: {turn.get('user','')}",
        f"Sucursal: {turn.get('branch','')}",
        f"Fondo inicial: {_format_currency(turn.get('opening_amount',0))}",
        f"Fecha: {turn.get('opened_at','')}",
    ]
    if turn.get("notes"):
        lines.append(f"Notas: {turn['notes']}")
    return lines


def print_turn_partial(summary: Dict[str, Any]) -> list[str]:
    lines = ["CORTE PARCIAL"]
    lines.append(f"Fondo: {_format_currency(summary.get('opening',0))}")
    lines.append(f"Ventas efectivo: {_format_currency(summary.get('cash_sales',0))}")
    lines.append(f"Ventas crédito: {_format_currency(summary.get('credit_sales',0))}")
    lines.append(f"Abonos crédito: {_format_currency(summary.get('credit_payments',0))}")
    lines.append(f"Abonos apartado: {_format_currency(summary.get('layaway_payments',0))}")
    lines.append(f"Entradas: {_format_currency(summary.get('ins',0))}")
    lines.append(f"Salidas: {_format_currency(summary.get('outs',0))}")
    lines.append(f"Efectivo esperado: {_format_currency(summary.get('expected_cash',0))}")
    return lines


def print_turn_close(summary: Dict[str, Any]) -> list[str]:
    lines = ["CIERRE DE TURNO"]
    lines.append(f"Fondo: {_format_currency(summary.get('opening',0))}")
    lines.append(f"Ventas efectivo: {_format_currency(summary.get('cash_sales',0))}")
    lines.append(f"Entradas: {_format_currency(summary.get('ins',0))}  Salidas: {_format_currency(summary.get('outs',0))}")
    lines.append(f"Abonos crédito: {_format_currency(summary.get('credit_payments',0))}")
    lines.append(f"Abonos apartado: {_format_currency(summary.get('layaway_payments',0))}")
    lines.append(f"Esperado: {_format_currency(summary.get('expected_cash',0))}")
    if "closing_amount" in summary:
        lines.append(f"Conteo: {_format_currency(summary.get('closing_amount',0))}")
        diff = float(summary.get("closing_amount",0)) - float(summary.get("expected_cash",0))
        lines.append(f"Diferencia: {_format_currency(diff)}")
    return lines


__all__ = [
    "render_payment_lines",
    "print_credit_payment",
    "print_credit_sale",
    "print_layaway_create",
    "print_layaway_payment",
    "print_layaway_liquidation",
    "print_turn_open",
    "print_turn_partial",
    "print_turn_close",
    "print_sale_card",
    "print_sale_transfer",
    "print_sale_usd",
    "print_sale_check",
    "print_sale_vouchers",
    "print_sale_mixed",
    "print_ticket",
    "open_cash_drawer",
    "build_escpos_bytes",
]
