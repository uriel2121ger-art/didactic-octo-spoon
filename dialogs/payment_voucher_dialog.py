"""Dialog for voucher/gift-card payments."""
from __future__ import annotations

from typing import Dict

from PySide6 import QtWidgets


class PaymentVoucherDialog(QtWidgets.QDialog):
    def __init__(self, total: float, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.total = float(total)
        self.result_data: Dict[str, float] | None = None
        self.setWindowTitle("Pago con vales")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)
        self.amount_spin = QtWidgets.QDoubleSpinBox()
        self.amount_spin.setMaximum(1_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setValue(self.total)
        layout.addRow("Monto de vales", self.amount_spin)
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def _accept(self) -> None:
        amount = float(self.amount_spin.value())
        if amount <= 0:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El monto debe ser mayor a cero")
            return
        self.result_data = {"method": "vouchers", "amount": amount, "voucher_amount": amount}
        self.accept()


__all__ = ["PaymentVoucherDialog"]
