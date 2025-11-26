"""Dialog for check payments."""
from __future__ import annotations

from typing import Dict

from PySide6 import QtWidgets


class PaymentCheckDialog(QtWidgets.QDialog):
    def __init__(self, total: float, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.total = float(total)
        self.result_data: Dict[str, float | str] | None = None
        self.setWindowTitle("Pago con cheque")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)
        self.amount_spin = QtWidgets.QDoubleSpinBox()
        self.amount_spin.setMaximum(1_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setValue(self.total)
        self.check_number_input = QtWidgets.QLineEdit()
        self.check_number_input.setPlaceholderText("Número de cheque")
        layout.addRow("Monto", self.amount_spin)
        layout.addRow("No. cheque", self.check_number_input)
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _accept(self) -> None:
        amount = float(self.amount_spin.value())
        check_number = self.check_number_input.text().strip()
        if amount <= 0:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El monto debe ser mayor a cero")
            return
        if not check_number:
            QtWidgets.QMessageBox.warning(self, "Dato requerido", "Ingresa el número de cheque")
            return
        self.result_data = {"method": "check", "amount": amount, "check_number": check_number}
        self.accept()


__all__ = ["PaymentCheckDialog"]
