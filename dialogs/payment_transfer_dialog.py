"""Dialog for transfer payments."""
from __future__ import annotations

from typing import Dict

from PySide6 import QtWidgets


class PaymentTransferDialog(QtWidgets.QDialog):
    def __init__(self, total: float, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.total = float(total)
        self.result_data: Dict[str, float | str] | None = None
        self.setWindowTitle("Pago por transferencia")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)
        self.amount_spin = QtWidgets.QDoubleSpinBox()
        self.amount_spin.setMaximum(1_000_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setValue(self.total)
        self.reference_input = QtWidgets.QLineEdit()
        self.reference_input.setPlaceholderText("Referencia obligatoria")
        layout.addRow("Monto", self.amount_spin)
        layout.addRow("Referencia", self.reference_input)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _accept(self) -> None:
        reference = self.reference_input.text().strip()
        if not reference:
            QtWidgets.QMessageBox.warning(self, "Referencia requerida", "Captura la referencia de la transferencia")
            return
        amount = float(self.amount_spin.value())
        if amount <= 0:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El monto debe ser mayor a cero")
            return
        self.result_data = {"method": "transfer", "amount": amount, "reference": reference}
        self.accept()


__all__ = ["PaymentTransferDialog"]
