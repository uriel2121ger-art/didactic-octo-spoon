"""Dialog to capture mixed payments."""
from __future__ import annotations

from typing import Dict, Optional

from PySide6 import QtCore, QtWidgets


class PaymentMixedDialog(QtWidgets.QDialog):
    def __init__(
        self,
        total: float,
        card_fee_percent: float = 0.0,
        default_exchange: float = 17.0,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self.total = float(total)
        self.card_fee_percent = float(card_fee_percent)
        self.default_exchange = float(default_exchange)
        self.result_data: Dict[str, object] | None = None
        self.setWindowTitle("Pago mixto")
        self._build_ui()

    def _build_ui(self) -> None:
        form = QtWidgets.QFormLayout(self)
        self.cash_spin = QtWidgets.QDoubleSpinBox()
        self.cash_spin.setMaximum(1_000_000)
        self.cash_spin.setDecimals(2)
        self.card_spin = QtWidgets.QDoubleSpinBox()
        self.card_spin.setMaximum(1_000_000)
        self.card_spin.setDecimals(2)
        self.card_ref = QtWidgets.QLineEdit()
        self.card_fee_spin = QtWidgets.QDoubleSpinBox()
        self.card_fee_spin.setDecimals(2)
        self.card_fee_spin.setMaximum(100)
        self.card_fee_spin.setSuffix(" %")
        self.card_fee_spin.setValue(self.card_fee_percent)
        self.transfer_spin = QtWidgets.QDoubleSpinBox()
        self.transfer_spin.setMaximum(1_000_000)
        self.transfer_spin.setDecimals(2)
        self.transfer_ref = QtWidgets.QLineEdit()
        self.voucher_spin = QtWidgets.QDoubleSpinBox()
        self.voucher_spin.setMaximum(1_000_000)
        self.voucher_spin.setDecimals(2)
        self.check_spin = QtWidgets.QDoubleSpinBox()
        self.check_spin.setMaximum(1_000_000)
        self.check_spin.setDecimals(2)
        self.check_number = QtWidgets.QLineEdit()
        self.usd_amount = QtWidgets.QDoubleSpinBox()
        self.usd_amount.setMaximum(1_000_000)
        self.usd_amount.setDecimals(2)
        self.usd_exchange = QtWidgets.QDoubleSpinBox()
        self.usd_exchange.setMaximum(1_000)
        self.usd_exchange.setDecimals(4)
        self.usd_exchange.setValue(self.default_exchange)

        form.addRow("Efectivo", self.cash_spin)
        form.addRow("Tarjeta", self.card_spin)
        form.addRow("Ref. tarjeta", self.card_ref)
        form.addRow("Comisión %", self.card_fee_spin)
        form.addRow("Transferencia", self.transfer_spin)
        form.addRow("Ref. transferencia", self.transfer_ref)
        form.addRow("Vales", self.voucher_spin)
        form.addRow("Cheque", self.check_spin)
        form.addRow("No. cheque", self.check_number)
        form.addRow("USD", self.usd_amount)
        form.addRow("Tipo cambio", self.usd_exchange)

        self.summary_lbl = QtWidgets.QLabel("Faltante: $0.00")
        form.addRow(self.summary_lbl)
        for spin in [
            self.cash_spin,
            self.card_spin,
            self.transfer_spin,
            self.voucher_spin,
            self.check_spin,
            self.usd_amount,
        ]:
            spin.valueChanged.connect(self._update_summary)
        self.usd_exchange.valueChanged.connect(self._update_summary)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        form.addRow(btn_box)
        self._update_summary()

    def _update_summary(self) -> None:
        total_paid = self._total_paid_mxn()
        delta = total_paid - self.total
        if delta >= 0:
            text = f"Cambio: ${delta:,.2f}"
        else:
            text = f"Faltante: ${abs(delta):,.2f}"
        self.summary_lbl.setText(text)

    def _total_paid_mxn(self) -> float:
        usd_total = float(self.usd_amount.value()) * float(self.usd_exchange.value()) if self.usd_amount.value() else 0.0
        return (
            float(self.cash_spin.value())
            + float(self.card_spin.value())
            + float(self.transfer_spin.value())
            + float(self.voucher_spin.value())
            + float(self.check_spin.value())
            + usd_total
        )

    def _accept(self) -> None:
        total_paid = self._total_paid_mxn()
        if total_paid < self.total:
            QtWidgets.QMessageBox.warning(self, "Monto insuficiente", "Los montos no cubren el total")
            return
        breakdown: Dict[str, object] = {}
        if self.cash_spin.value():
            breakdown["cash"] = float(self.cash_spin.value())
        if self.card_spin.value():
            breakdown["card"] = {
                "amount": float(self.card_spin.value()),
                "reference": self.card_ref.text().strip(),
                "card_fee": float(self.card_spin.value()) * (self.card_fee_spin.value() / 100.0),
            }
        if self.transfer_spin.value():
            breakdown["transfer"] = {
                "amount": float(self.transfer_spin.value()),
                "reference": self.transfer_ref.text().strip(),
            }
        if self.voucher_spin.value():
            breakdown["voucher"] = {"amount": float(self.voucher_spin.value())}
        if self.check_spin.value():
            breakdown["check"] = {
                "amount": float(self.check_spin.value()),
                "check_number": self.check_number.text().strip(),
            }
        if self.usd_amount.value():
            breakdown["usd"] = {
                "usd_amount": float(self.usd_amount.value()),
                "usd_exchange": float(self.usd_exchange.value()),
            }
        self.result_data = {"method": "mixed", "breakdown": breakdown, "change": total_paid - self.total}
        self.accept()


__all__ = ["PaymentMixedDialog"]
