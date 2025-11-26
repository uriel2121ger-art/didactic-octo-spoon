from __future__ import annotations

from PySide6 import QtWidgets


class CashMovementDialog(QtWidgets.QDialog):
    def __init__(self, movement_type: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.movement_type = movement_type
        self.result_data: dict | None = None
        self.setWindowTitle("Movimiento de efectivo")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Entrada de efectivo" if self.movement_type == "in" else "Salida de efectivo")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        form = QtWidgets.QFormLayout()
        self.amount = QtWidgets.QDoubleSpinBox()
        self.amount.setRange(0, 1_000_000)
        self.amount.setDecimals(2)
        self.amount.setPrefix("$ ")
        form.addRow("Cantidad:", self.amount)
        self.reason = QtWidgets.QLineEdit()
        form.addRow("Motivo:", self.reason)
        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:  # type: ignore[override]
        if self.amount.value() <= 0:
            QtWidgets.QMessageBox.warning(self, "Cantidad inválida", "Ingresa una cantidad mayor a cero")
            return
        self.result_data = {
            "type": self.movement_type,
            "amount": float(self.amount.value()),
            "reason": self.reason.text().strip(),
        }
        super().accept()
