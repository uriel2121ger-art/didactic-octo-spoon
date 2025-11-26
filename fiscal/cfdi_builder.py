"""
Stubs de construcción CFDI para que el POS arranque sin errores.
Más adelante puedes implementar facturación (CFDI 4.0 real).
"""

def build_cfdi_ingreso_xml(data, *args, **kwargs):
    """
    Genera un CFDI de ingreso en modo stub.
    """
    return b"<cfdi:Comprobante Tipo='Ingreso' Stub='true'/>"


def build_cfdi_pago_xml(data, *args, **kwargs):
    """
    Genera un CFDI de pago en modo stub.
    """
    return b"<cfdi:Comprobante Tipo='Pago' Stub='true'/>"
