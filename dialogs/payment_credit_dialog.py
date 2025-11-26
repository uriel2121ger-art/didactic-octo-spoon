"""Simple credit payment confirmation dialog."""
from __future__ import annotations

from typing import Dict

from PySide6 import QtWidgets


class PaymentCreditDialog(QtWidgets.QDialog):
    def __init__(
        self,
        total: float,
        customer_name: str,
        available_credit: float,
        customer_id: int | None = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.total = float(total)
        self.customer_name = customer_name
        self.available_credit = float(available_credit)
        self.customer_id = customer_id
        self.result_data: Dict[str, float | str | int] | None = None
        self.setWindowTitle("Venta a crédito")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        credit_txt = "Ilimitado" if self.available_credit < 0 else f"${self.available_credit:,.2f}"
        info = QtWidgets.QLabel(
            (
                "Registrar la venta a crédito para <b>" + self.customer_name + "</b><br>"
                + f"Total: ${self.total:,.2f}<br>"
                + f"Crédito disponible: {credit_txt}"
            )
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _accept(self) -> None:
        if self.available_credit >= 0 and (self.total - self.available_credit > 1e-6):
            QtWidgets.QMessageBox.warning(
                self,
                "Crédito insuficiente",
                "El monto excede el crédito disponible del cliente.",
            )
            return
        self.result_data = {"method": "credit", "amount": self.total, "credit_amount": self.total}
        if self.customer_id is not None:
            self.result_data["customer_id"] = self.customer_id
        self.result_data["change"] = 0.0
        self.accept()


__all__ = ["PaymentCreditDialog"]
