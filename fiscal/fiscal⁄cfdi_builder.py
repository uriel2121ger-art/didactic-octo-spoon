"""Helpers to build CFDI 4.0 XML payloads (simplified).

These builders intentionally keep the structure lean while exposing the
required nodes to integrate with a PAC. They can be refined later with full
CFDI validations and catalogs.
"""
from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from typing import Any, Sequence


def _make_attrib(base: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in base.items() if v is not None}


def build_cfdi_ingreso_xml(
    sale: dict[str, Any],
    items: Sequence[dict[str, Any]],
    config: dict[str, Any],
    *,
    uso_cfdi: str = "G03",
    forma_pago: str = "01",
    metodo_pago: str = "PUE",
    currency: str = "MXN",
) -> str:
    """Build a minimal CFDI 4.0 XML for an ingreso (factura) document."""

    root = ET.Element(
        "Comprobante",
        _make_attrib(
            {
                "Version": "4.0",
                "Serie": config.get("serie_factura", "F"),
                "Folio": sale.get("folio", ""),
                "Fecha": datetime.datetime.utcnow().isoformat(),
                "Moneda": currency,
                "SubTotal": f"{sale.get('subtotal', 0):.2f}",
                "Total": f"{sale.get('total', 0):.2f}",
                "TipoDeComprobante": "I",
                "FormaPago": forma_pago,
                "MetodoPago": metodo_pago,
                "LugarExpedicion": config.get("lugar_expedicion", "00000"),
                "NoCertificado": "00001000000400000123",  # placeholder
            }
        ),
    )

    emisor = ET.SubElement(
        root,
        "Emisor",
        _make_attrib(
            {
                "Rfc": config.get("rfc_emisor", ""),
                "Nombre": config.get("razon_social_emisor", ""),
                "RegimenFiscal": config.get("regimen_fiscal", "601"),
            }
        ),
    )
    receptor = ET.SubElement(
        root,
        "Receptor",
        _make_attrib(
            {
                "Rfc": sale.get("customer_rfc", "XAXX010101000"),
                "Nombre": sale.get("customer_name", "Publico en general"),
                "UsoCFDI": uso_cfdi,
                "DomicilioFiscalReceptor": sale.get("customer_zip", config.get("lugar_expedicion", "00000")),
                "RegimenFiscalReceptor": sale.get("customer_regimen", "601"),
            }
        ),
    )
    conceptos = ET.SubElement(root, "Conceptos")
    tax_total = 0.0
    for idx, item in enumerate(items, start=1):
        qty = float(item.get("qty", 1))
        price = float(item.get("price", 0.0))
        discount = float(item.get("discount", 0.0))
        subtotal = max(price * qty - discount, 0)
        importe = subtotal
        impuesto = importe * 0.16
        tax_total += impuesto
        concepto = ET.SubElement(
            conceptos,
            "Concepto",
            _make_attrib(
                {
                    "ClaveProdServ": item.get("sku", "01010101"),
                    "NoIdentificacion": item.get("sku", str(idx)),
                    "Cantidad": f"{qty:.2f}",
                    "ClaveUnidad": "H87",
                    "Descripcion": item.get("name", "Producto"),
                    "ValorUnitario": f"{price:.2f}",
                    "Importe": f"{importe:.2f}",
                    "Descuento": f"{discount:.2f}" if discount else None,
                    "ObjetoImp": "02",
                }
            ),
        )
        impuestos = ET.SubElement(concepto, "Impuestos")
        traslados = ET.SubElement(impuestos, "Traslados")
        ET.SubElement(
            traslados,
            "Traslado",
            _make_attrib(
                {
                    "Base": f"{importe:.2f}",
                    "Impuesto": "002",
                    "TipoFactor": "Tasa",
                    "TasaOCuota": "0.160000",
                    "Importe": f"{impuesto:.2f}",
                }
            ),
        )

    totales = ET.SubElement(root, "Impuestos", _make_attrib({"TotalImpuestosTrasladados": f"{tax_total:.2f}"}))
    tras_tot = ET.SubElement(totales, "Traslados")
    ET.SubElement(
        tras_tot,
        "Traslado",
        _make_attrib(
            {
                "Impuesto": "002",
                "TipoFactor": "Tasa",
                "TasaOCuota": "0.160000",
                "Importe": f"{tax_total:.2f}",
                "Base": f"{sale.get('subtotal', 0):.2f}",
            }
        ),
    )
    return ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")


def build_cfdi_pago_xml(
    cfdi_original: dict[str, Any],
    payments: Sequence[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    """Build a simplified CFDI payment complement XML.

    This is intentionally minimal and can be expanded with full schemas later.
    """

    root = ET.Element(
        "Comprobante",
        _make_attrib(
            {
                "Version": "4.0",
                "TipoDeComprobante": "P",
                "Serie": cfdi_original.get("serie", config.get("serie_factura", "P")),
                "Folio": cfdi_original.get("folio", ""),
                "LugarExpedicion": config.get("lugar_expedicion", "00000"),
            }
        ),
    )
    ET.SubElement(
        root,
        "Emisor",
        _make_attrib(
            {
                "Rfc": config.get("rfc_emisor", ""),
                "Nombre": config.get("razon_social_emisor", ""),
                "RegimenFiscal": config.get("regimen_fiscal", "601"),
            }
        ),
    )
    ET.SubElement(
        root,
        "Receptor",
        _make_attrib(
            {
                "Rfc": cfdi_original.get("customer_rfc", "XAXX010101000"),
                "Nombre": cfdi_original.get("customer_name", "Publico en general"),
                "UsoCFDI": cfdi_original.get("uso_cfdi", "CP01"),
                "DomicilioFiscalReceptor": cfdi_original.get("customer_zip", config.get("lugar_expedicion", "00000")),
                "RegimenFiscalReceptor": cfdi_original.get("customer_regimen", "601"),
            }
        ),
    )
    pagos = ET.SubElement(root, "Pagos", _make_attrib({"Version": "2.0"}))
    totales = ET.SubElement(pagos, "Totales")
    total_pagado = 0.0
    for pay in payments:
        monto = float(pay.get("amount", 0.0))
        total_pagado += monto
        pago = ET.SubElement(
            pagos,
            "Pago",
            _make_attrib(
                {
                    "FechaPago": pay.get("timestamp") or datetime.datetime.utcnow().isoformat(),
                    "FormaDePagoP": pay.get("forma_pago", "03"),
                    "MonedaP": pay.get("moneda", "MXN"),
                    "Monto": f"{monto:.2f}",
                }
            ),
        )
        docto = ET.SubElement(
            pago,
            "DoctoRelacionado",
            _make_attrib(
                {
                    "IdDocumento": cfdi_original.get("uuid", ""),
                    "Serie": cfdi_original.get("serie", ""),
                    "Folio": cfdi_original.get("folio", ""),
                    "MonedaDR": "MXN",
                    "EquivalenciaDR": "1",
                    "NumParcialidad": str(pay.get("parcialidad", 1)),
                    "ImpSaldoAnt": f"{pay.get('saldo_anterior', 0):.2f}",
                    "ImpPagado": f"{monto:.2f}",
                    "ImpSaldoInsoluto": f"{max(pay.get('saldo_anterior', 0) - monto, 0):.2f}",
                    "ObjetoImpDR": "02",
                }
            ),
        )
        imp = ET.SubElement(docto, "ImpuestosDR")
        tras = ET.SubElement(imp, "TrasladosDR")
        ET.SubElement(
            tras,
            "TrasladoDR",
            _make_attrib(
                {
                    "BaseDR": f"{monto:.2f}",
                    "ImpuestoDR": "002",
                    "TipoFactorDR": "Tasa",
                    "TasaOCuotaDR": "0.160000",
                    "ImporteDR": f"{monto * 0.16:.2f}",
                }
            ),
        )
    totales.attrib["MontoTotalPagos"] = f"{total_pagado:.2f}"
    return ET.tostring(root, encoding="utf-8", method="xml").decode("utf-8")

__all__ = ["build_cfdi_ingreso_xml", "build_cfdi_pago_xml"]
