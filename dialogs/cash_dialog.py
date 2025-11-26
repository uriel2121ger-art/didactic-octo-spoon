from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class CashMovementDialog(QtWidgets.QDialog):
    def __init__(self, movement_type: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Movimiento de efectivo")
        self.movement_type = movement_type
        self.result_data: dict | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("ENTRADA DE EFECTIVO" if self.movement_type == "in" else "SALIDA DE EFECTIVO")
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

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

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


class CashHistoryDialog(QtWidgets.QDialog):
    def __init__(self, movements: list[dict], parent: QtWidgets.QWidget | None = None, can_cancel: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Historial de caja")
        self.movements = movements
        self.can_cancel = can_cancel
        self.to_delete: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Hora", "Tipo", "Cantidad", "Motivo"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self._refresh()

        if self.can_cancel:
            self.cancel_btn = QtWidgets.QPushButton("Cancelar movimiento")
            self.cancel_btn.clicked.connect(self._handle_cancel)
            layout.addWidget(self.cancel_btn)

        close_btn = QtWidgets.QPushButton("Cerrar")
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)

    def _refresh(self) -> None:
        self.table.setRowCount(0)
        for mov in self.movements:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(mov.get("created_at"))))
            typ = "Entrada" if mov.get("movement_type") == "in" else "Salida"
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(typ))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"$ {mov.get('amount',0):.2f}"))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(mov.get("reason") or ""))

    def _handle_cancel(self) -> None:
        current = self.table.currentRow()
        if current < 0:
            QtWidgets.QMessageBox.warning(self, "Seleccione", "Seleccione un movimiento")
            return
        mov = self.movements[current]
        self.to_delete = mov.get("id")
        self.accept()
