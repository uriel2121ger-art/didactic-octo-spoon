from __future__ import annotations

from typing import Dict, Optional

from PySide6 import QtCore, QtWidgets


class MixedPaymentDialog(QtWidgets.QDialog):
    """Capture multiple payment methods ensuring totals cover the sale."""

    def __init__(
        self,
        total: float,
        *,
        card_fee_percent: float = 0.0,
        default_exchange: float = 17.0,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.total = float(total)
        self.card_fee_percent = float(card_fee_percent)
        self.default_exchange = float(default_exchange)
        self.result_data: Dict[str, object] | None = None
        self.setWindowTitle("Pago mixto")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Desglose de pago mixto")
        font = title.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 2)
        title.setFont(font)
        layout.addWidget(title)

        grid = QtWidgets.QFormLayout()
        self.cash_spin = self._money_spin()
        self.card_spin = self._money_spin()
        self.card_ref = QtWidgets.QLineEdit()
        self.card_fee_spin = QtWidgets.QDoubleSpinBox()
        self.card_fee_spin.setDecimals(2)
        self.card_fee_spin.setMaximum(100)
        self.card_fee_spin.setSuffix(" %")
        self.card_fee_spin.setValue(self.card_fee_percent)
        self.transfer_spin = self._money_spin()
        self.transfer_ref = QtWidgets.QLineEdit()
        self.voucher_spin = self._money_spin()
        self.check_spin = self._money_spin()
        self.check_number = QtWidgets.QLineEdit()
        self.usd_amount = self._money_spin()
        self.usd_exchange = QtWidgets.QDoubleSpinBox()
        self.usd_exchange.setDecimals(4)
        self.usd_exchange.setMaximum(1_000)
        self.usd_exchange.setValue(self.default_exchange)

        grid.addRow("Efectivo", self.cash_spin)
        grid.addRow("Tarjeta", self.card_spin)
        grid.addRow("Ref. tarjeta", self.card_ref)
        grid.addRow("Comisión %", self.card_fee_spin)
        grid.addRow("Transferencia", self.transfer_spin)
        grid.addRow("Ref. transferencia", self.transfer_ref)
        grid.addRow("Vales", self.voucher_spin)
        grid.addRow("Cheque", self.check_spin)
        grid.addRow("No. cheque", self.check_number)
        grid.addRow("USD", self.usd_amount)
        grid.addRow("Tipo de cambio", self.usd_exchange)
        layout.addLayout(grid)

        self.summary_lbl = QtWidgets.QLabel()
        layout.addWidget(self.summary_lbl)

        for widget in [
            self.cash_spin,
            self.card_spin,
            self.transfer_spin,
            self.voucher_spin,
            self.check_spin,
            self.usd_amount,
        ]:
            widget.valueChanged.connect(self._update_summary)
        self.usd_exchange.valueChanged.connect(self._update_summary)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        self._update_summary()

    def _money_spin(self) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setDecimals(2)
        spin.setMaximum(1_000_000_000)
        return spin

    def _update_summary(self) -> None:
        total_paid = self._total_paid_mxn()
        delta = total_paid - self.total
        if delta >= 0:
            self.summary_lbl.setText(f"Cambio: ${delta:,.2f}")
        else:
            self.summary_lbl.setText(f"Faltante: ${abs(delta):,.2f}")

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
        change = total_paid - self.total
        if self.cash_spin.value():
            breakdown["cash"] = float(self.cash_spin.value())
        if self.card_spin.value():
            card_fee = float(self.card_spin.value()) * (self.card_fee_spin.value() / 100.0)
            breakdown["card"] = {
                "amount": float(self.card_spin.value()),
                "reference": self.card_ref.text().strip(),
                "fee": card_fee,
                "card_fee": card_fee,
            }
        if self.transfer_spin.value():
            breakdown["transfer"] = {
                "amount": float(self.transfer_spin.value()),
                "reference": self.transfer_ref.text().strip(),
            }
        if self.voucher_spin.value():
            breakdown["vouchers"] = float(self.voucher_spin.value())
        if self.check_spin.value():
            breakdown["check"] = {
                "amount": float(self.check_spin.value()),
                "check_number": self.check_number.text().strip(),
            }
        if self.usd_amount.value():
            breakdown["usd"] = {
                "usd_amount": float(self.usd_amount.value()),
                "usd_given": float(self.usd_amount.value()),
                "usd_exchange": float(self.usd_exchange.value()),
                "exchange_rate": float(self.usd_exchange.value()),
            }
        self.result_data = {"method": "mixed", "breakdown": breakdown, "change": change}
        self.accept()


__all__ = ["MixedPaymentDialog"]
