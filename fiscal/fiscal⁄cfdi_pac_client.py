"""
Stub de cliente PAC para CFDI.

Este módulo existe solo para que el POS arranque sin errores.
Más adelante podrías implementar un cliente real a un PAC (ProFact, SoluciónFactible, etc.).
"""


class PACClient:
    """
    Cliente PAC falso (stub).
    Todas las funciones simulan éxito sin hacer ninguna llamada externa.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def timbrar_cfdi(self, xml_bytes: bytes) -> bytes:
        """
        Simula el timbrado de un CFDI.
        En una implementación real, aquí se haría la llamada HTTP al PAC.

        Por ahora solo regresa el mismo XML o le agrega un comentario.
        """
        # IMPORTANTE: esto es solo stub.
        # En producción, deberías integrar un PAC real.
        return xml_bytes

    def cancelar_cfdi(self, uuid: str) -> bool:
        """
        Simula la cancelación de un CFDI.
        Siempre devuelve True en este stub.
        """
        return True
