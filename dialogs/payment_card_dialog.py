"""Dialog for card payments with reference and fee capture."""
from __future__ import annotations

from typing import Dict

from PySide6 import QtCore, QtWidgets


class PaymentCardDialog(QtWidgets.QDialog):
    def __init__(self, total: float, fee_percent: float = 0.0, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.total = float(total)
        self.fee_percent = float(fee_percent)
        self.result_data: Dict[str, float | str] | None = None
        self.setWindowTitle("Pago con tarjeta")
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)
        self.amount_spin = QtWidgets.QDoubleSpinBox()
        self.amount_spin.setMaximum(1_000_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setValue(self.total)
        self.ref_input = QtWidgets.QLineEdit()
        self.ref_input.setPlaceholderText("Referencia")
        self.fee_spin = QtWidgets.QDoubleSpinBox()
        self.fee_spin.setMaximum(100.0)
        self.fee_spin.setDecimals(2)
        self.fee_spin.setSuffix(" %")
        self.fee_spin.setValue(self.fee_percent)
        layout.addRow("Monto", self.amount_spin)
        layout.addRow("Referencia", self.ref_input)
        layout.addRow("Comisión %", self.fee_spin)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _accept(self) -> None:
        reference = self.ref_input.text().strip()
        if not reference:
            QtWidgets.QMessageBox.warning(self, "Referencia requerida", "Captura la referencia de la tarjeta")
            return
        amount = float(self.amount_spin.value())
        if amount <= 0:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El monto debe ser mayor a cero")
            return
        if amount < self.total:
            QtWidgets.QMessageBox.warning(
                self, "Monto insuficiente", "El monto con tarjeta no cubre el total a cobrar"
            )
            return
        fee = amount * (self.fee_spin.value() / 100.0)
        self.result_data = {
            "method": "card",
            "amount": amount,
            "reference": reference,
            "fee": fee,
            "card_fee": fee,
        }
        self.accept()


__all__ = ["PaymentCardDialog"]
