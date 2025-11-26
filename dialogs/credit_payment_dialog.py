from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class CreditPaymentDialog(QtWidgets.QDialog):
    """Dialog to capture a credit payment (abono) without side effects."""

    def __init__(
        self,
        *,
        customer_name: str,
        credit_limit: float,
        credit_balance: float,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.customer_name = customer_name
        self.credit_limit = float(credit_limit)
        self.credit_balance = float(credit_balance)
        self.setWindowTitle("Abono a crédito")
        self.setModal(True)
        self.result_data: dict | None = None
        self._build_ui()
        self._update_future_balance()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        self.setMinimumWidth(460)

        title = QtWidgets.QLabel("ABONO A CRÉDITO")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        info_frame = QtWidgets.QFrame()
        info_frame.setStyleSheet(
            "QFrame { background: #f6f8fb; border-radius: 12px; padding: 12px; }"
        )
        form = QtWidgets.QFormLayout(info_frame)
        name_lbl = QtWidgets.QLabel(self.customer_name)
        name_lbl.setStyleSheet("font-weight: 600;")
        form.addRow("Cliente", name_lbl)
        self.limit_lbl = QtWidgets.QLabel(f"${self.credit_limit:,.2f}")
        self.balance_lbl = QtWidgets.QLabel(f"${self.credit_balance:,.2f}")
        for lbl in (self.limit_lbl, self.balance_lbl):
            lbl.setStyleSheet("font-weight: 600; color: #2c3e50;")
        form.addRow("Límite de crédito", self.limit_lbl)
        form.addRow("Saldo actual", self.balance_lbl)
        layout.addWidget(info_frame)

        self.amount_input = QtWidgets.QDoubleSpinBox()
        self.amount_input.setMaximum(max(self.credit_balance, 1_000_000))
        self.amount_input.setDecimals(2)
        self.amount_input.setPrefix("$")
        self.amount_input.setSingleStep(50.0)
        self.amount_input.valueChanged.connect(self._update_future_balance)

        self.notes_input = QtWidgets.QLineEdit()
        self.notes_input.setPlaceholderText("Notas del abono (opcional)")

        layout.addWidget(QtWidgets.QLabel("Monto del abono"))
        layout.addWidget(self.amount_input)
        layout.addWidget(QtWidgets.QLabel("Notas"))
        layout.addWidget(self.notes_input)

        self.future_label = QtWidgets.QLabel()
        self.future_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.future_label.setStyleSheet("font-size: 14px; color: #27ae60; font-weight: 600;")
        layout.addWidget(self.future_label)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        accept_btn = QtWidgets.QPushButton("✔ Registrar abono")
        accept_btn.setStyleSheet("background:#27ae60; color:white; padding:8px 16px; font-weight:600; border-radius:8px;")
        accept_btn.clicked.connect(self._on_accept)
        cancel_btn = QtWidgets.QPushButton("✖ Cancelar")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(accept_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _update_future_balance(self) -> None:
        amount = float(self.amount_input.value())
        updated = max(self.credit_balance - amount, 0)
        self.future_label.setText(f"Saldo actualizado: ${updated:,.2f}")

    def _on_accept(self) -> None:
        amount = float(self.amount_input.value())
        if amount <= 0:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El abono debe ser mayor a cero")
            return
        if amount - self.credit_balance > 1e-6:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El abono no puede exceder el adeudo")
            return
        self.result_data = {"amount": amount, "notes": self.notes_input.text().strip()}
        self.accept()


__all__ = ["CreditPaymentDialog"]
