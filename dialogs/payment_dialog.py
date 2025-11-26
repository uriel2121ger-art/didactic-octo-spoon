"""Payment dialog supporting multiple methods."""
from __future__ import annotations

from typing import Dict

from PySide6 import QtCore, QtGui, QtWidgets

from utils.animations import fade_in

from .payment_card_dialog import PaymentCardDialog
from .payment_check_dialog import PaymentCheckDialog
from .payment_credit_dialog import PaymentCreditDialog
from .mixed_payment_dialog import MixedPaymentDialog
from .payment_transfer_dialog import PaymentTransferDialog
from .payment_usd_dialog import PaymentUSDDialog
from .payment_voucher_dialog import PaymentVoucherDialog


class CashMethodDialog(QtWidgets.QDialog):
    """Minimal cash dialog with change calculation."""

    def __init__(self, total: float, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.total = float(total)
        self.result_data: Dict[str, float] | None = None
        self.setWindowTitle("Cobro en efectivo")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(f"Total a cobrar: ${self.total:,.2f}"))
        self.amount_input = QtWidgets.QLineEdit()
        self.amount_input.setValidator(QtGui.QDoubleValidator(0.0, 1_000_000_000.0, 2))
        self.amount_input.textChanged.connect(self._recalc)
        self.amount_input.setPlaceholderText("Monto recibido")
        layout.addWidget(self.amount_input)
        self.change_lbl = QtWidgets.QLabel("Cambio: $0.00")
        layout.addWidget(self.change_lbl)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.amount_input.setFocus()

    def _recalc(self) -> None:
        paid = self._current_amount()
        change = max(paid - self.total, 0.0)
        self.change_lbl.setText(f"Cambio: ${change:,.2f}")

    def _current_amount(self) -> float:
        text = self.amount_input.text().replace(",", "").strip()
        try:
            return float(text) if text else 0.0
        except ValueError:
            return 0.0

    def _accept(self) -> None:
        paid = self._current_amount()
        if paid < self.total:
            QtWidgets.QMessageBox.warning(self, "Monto insuficiente", "El monto recibido es menor al total")
            return
        change = max(paid - self.total, 0.0)
        self.result_data = {
            "method": "cash",
            "amount": self.total,
            "paid_amount": paid,
            "change": change,
            "cash": self.total,
        }
        self.accept()


class PaymentDialog(QtWidgets.QDialog):
    def __init__(
        self,
        total_a_cobrar: float,
        parent: QtWidgets.QWidget | None = None,
        *,
        allow_credit: bool = False,
        customer_name: str | None = None,
        customer_id: int | None = None,
        credit_available: float = 0.0,
        card_fee_percent: float = 0.0,
        default_exchange: float = 17.0,
    ):
        super().__init__(parent)
        self.total_a_cobrar = float(total_a_cobrar)
        self.allow_credit = allow_credit
        self.customer_name = customer_name or "Cliente"
        self.customer_id = customer_id
        self.credit_available = float(credit_available)
        self.card_fee_percent = float(card_fee_percent)
        self.default_exchange = float(default_exchange)
        self.result_data: Dict[str, object] | None = None
        self.setWindowTitle("Formas de pago")
        self._build_ui()
        fade_in(self)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Selecciona forma de pago")
        font = title.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        layout.addWidget(QtWidgets.QLabel(f"Total: ${self.total_a_cobrar:,.2f}"))

        grid = QtWidgets.QGridLayout()
        buttons = [
            ("Efectivo", self._pay_cash),
            ("Tarjeta", self._pay_card),
            ("Transferencia", self._pay_transfer),
            ("Dólares", self._pay_usd),
            ("Vales", self._pay_voucher),
            ("Cheque", self._pay_check),
            ("Crédito", self._pay_credit),
            ("Pago mixto", self._pay_mixed),
        ]
        for idx, (text, handler) in enumerate(buttons):
            btn = QtWidgets.QPushButton(text)
            btn.setMinimumHeight(36)
            btn.clicked.connect(handler)
            if text == "Crédito":
                if not self.allow_credit:
                    btn.setEnabled(False)
                    btn.setToolTip("Asigna un cliente para habilitar crédito")
                elif self.credit_available <= 0:
                    btn.setEnabled(False)
                    btn.setToolTip("Crédito no disponible para este cliente")
            grid.addWidget(btn, idx // 2, idx % 2)
        layout.addLayout(grid)
        cancel_btn = QtWidgets.QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.setStyleSheet(
            """
            QPushButton { padding: 10px 14px; border-radius: 8px; background:#2b8be6; color:white; }
            QPushButton:hover { background:#1f6fbb; }
            QPushButton:disabled { background: #9bb9e3; }
            QDialog { background:#f6f8fb; }
            """
        )

    # -- method handlers -------------------------------------------------
    def _pay_cash(self) -> None:
        dlg = CashMethodDialog(self.total_a_cobrar, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            self.result_data = dlg.result_data
            self.accept()

    def _pay_card(self) -> None:
        dlg = PaymentCardDialog(self.total_a_cobrar, fee_percent=self.card_fee_percent, parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            self.result_data = dlg.result_data
            self.accept()

    def _pay_transfer(self) -> None:
        dlg = PaymentTransferDialog(self.total_a_cobrar, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            self.result_data = dlg.result_data
            self.accept()

    def _pay_usd(self) -> None:
        dlg = PaymentUSDDialog(self.total_a_cobrar, default_exchange=self.default_exchange, parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            self.result_data = dlg.result_data
            self.accept()

    def _pay_voucher(self) -> None:
        dlg = PaymentVoucherDialog(self.total_a_cobrar, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            self.result_data = dlg.result_data
            self.accept()

    def _pay_check(self) -> None:
        dlg = PaymentCheckDialog(self.total_a_cobrar, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            self.result_data = dlg.result_data
            self.accept()

    def _pay_credit(self) -> None:
        if not self.allow_credit:
            QtWidgets.QMessageBox.warning(self, "Crédito no disponible", "Asigna un cliente antes de vender a crédito")
            return
        dlg = PaymentCreditDialog(
            self.total_a_cobrar,
            self.customer_name,
            self.credit_available,
            self.customer_id,
            self,
        )
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            self.result_data = dlg.result_data
            self.accept()

    def _pay_mixed(self) -> None:
        dlg = MixedPaymentDialog(
            self.total_a_cobrar,
            card_fee_percent=self.card_fee_percent,
            default_exchange=self.default_exchange,
            parent=self,
        )
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            self.result_data = dlg.result_data
            self.accept()


__all__ = ["PaymentDialog"]
