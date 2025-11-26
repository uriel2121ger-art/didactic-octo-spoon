"""Dialog to register layaway payments (abonos)."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from utils.animations import fade_in


class LayawayPaymentDialog(QtWidgets.QDialog):
    def __init__(self, customer_name: str, total: float, paid: float, balance: float, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Abono de apartado")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.result_data: dict | None = None
        self.balance = float(balance)
        self.customer_name = customer_name or "Cliente"
        self.total = float(total)
        self.paid = float(paid)
        self._build_ui()
        fade_in(self)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("ABONO DE APARTADO")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        info_layout = QtWidgets.QFormLayout()
        info_layout.addRow("Cliente", QtWidgets.QLabel(self.customer_name))
        info_layout.addRow("Total", QtWidgets.QLabel(f"${self.total:,.2f}"))
        info_layout.addRow("Pagado", QtWidgets.QLabel(f"${self.paid:,.2f}"))
        info_layout.addRow("Saldo", QtWidgets.QLabel(f"${self.balance:,.2f}"))

        self.amount_sb = QtWidgets.QDoubleSpinBox()
        self.amount_sb.setPrefix("$")
        self.amount_sb.setMaximum(self.balance)
        self.amount_sb.setDecimals(2)
        self.amount_sb.setSingleStep(10)
        self.amount_sb.valueChanged.connect(self._update_future_balance)

        self.notes_edit = QtWidgets.QLineEdit()
        self.notes_edit.setPlaceholderText("Notas opcionales del abono")

        self.new_balance_lbl = QtWidgets.QLabel("Saldo actualizado: --")
        self.new_balance_lbl.setStyleSheet("font-weight: 600;")

        info_layout.addRow("Monto del abono", self.amount_sb)
        info_layout.addRow("Notas", self.notes_edit)
        info_layout.addRow("", self.new_balance_lbl)
        layout.addLayout(info_layout)

        btn_box = QtWidgets.QDialogButtonBox()
        self.register_btn = btn_box.addButton("Registrar abono", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_btn = btn_box.addButton("Cancelar", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        self._update_future_balance()

    def _update_future_balance(self) -> None:
        new_balance = max(self.balance - self.amount_sb.value(), 0)
        self.new_balance_lbl.setText(f"Saldo actualizado: ${new_balance:,.2f}")

    def _on_accept(self) -> None:
        amount = float(self.amount_sb.value())
        if amount <= 0:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El abono debe ser mayor a cero")
            return
        if amount > self.balance:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El abono no puede ser mayor al saldo")
            return
        self.result_data = {
            "amount": amount,
            "notes": self.notes_edit.text().strip(),
        }
        self.accept()


__all__ = ["LayawayPaymentDialog"]
