"""Dialog for USD payments with exchange rate."""
from __future__ import annotations

from typing import Dict

from PySide6 import QtWidgets


class PaymentUSDDialog(QtWidgets.QDialog):
    def __init__(self, total: float, default_exchange: float = 17.0, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.total = float(total)
        self.default_exchange = float(default_exchange)
        self.result_data: Dict[str, float] | None = None
        self.setWindowTitle("Pago en dólares")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)
        self.usd_amount = QtWidgets.QDoubleSpinBox()
        self.usd_amount.setMaximum(1_000_000)
        self.usd_amount.setDecimals(2)
        self.exchange_spin = QtWidgets.QDoubleSpinBox()
        self.exchange_spin.setMaximum(1_000)
        self.exchange_spin.setDecimals(4)
        self.exchange_spin.setValue(self.default_exchange)
        layout.addRow("USD entregados", self.usd_amount)
        layout.addRow("Tipo de cambio", self.exchange_spin)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _accept(self) -> None:
        usd_amount = float(self.usd_amount.value())
        usd_exchange = float(self.exchange_spin.value())
        if usd_amount <= 0 or usd_exchange <= 0:
            QtWidgets.QMessageBox.warning(self, "Datos inválidos", "Captura monto y tipo de cambio válidos")
            return
        amount_mxn = usd_amount * usd_exchange
        self.result_data = {
            "method": "usd",
            "usd_amount": usd_amount,
            "usd_given": usd_amount,
            "usd_exchange": usd_exchange,
            "exchange_rate": usd_exchange,
            "amount_mxn": amount_mxn,
        }
        self.accept()


__all__ = ["PaymentUSDDialog"]
