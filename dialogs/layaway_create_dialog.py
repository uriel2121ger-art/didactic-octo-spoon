"""Dialog to capture layaway header information with cart preview."""
from __future__ import annotations

from typing import Iterable

from PySide6 import QtCore, QtWidgets

from utils.animations import fade_in


class LayawayCreateDialog(QtWidgets.QDialog):
    def __init__(self, items: Iterable[dict], total: float, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo apartado")
        self.setModal(True)
        self.setMinimumSize(520, 420)
        self.result_data: dict | None = None
        self.total = float(total)
        self._build_ui(list(items))
        fade_in(self)

    def _build_ui(self, items: list[dict]) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("CREAR APARTADO")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        summary_frame = QtWidgets.QFrame()
        summary_frame.setStyleSheet(
            "QFrame {border: 1px solid #d0d7e2; border-radius: 8px; background: #f7f9fc;}"
        )
        vbox = QtWidgets.QVBoxLayout(summary_frame)
        vbox.addWidget(QtWidgets.QLabel("Productos en el apartado:"))

        self.items_table = QtWidgets.QTableWidget(0, 4)
        self.items_table.setHorizontalHeaderLabels(["SKU", "Nombre", "Cant", "Precio"])
        self.items_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        vbox.addWidget(self.items_table)
        layout.addWidget(summary_frame)

        self._populate_items(items)

        form = QtWidgets.QFormLayout()
        self.customer_id: int | None = None
        self.customer_label = QtWidgets.QLabel("Sin cliente")

        self.due_date = QtWidgets.QDateEdit()
        self.due_date.setCalendarPopup(True)
        self.due_date.setDate(QtCore.QDate.currentDate().addDays(7))
        self.due_date.setDisplayFormat("yyyy-MM-dd")

        self.deposit_sb = QtWidgets.QDoubleSpinBox()
        self.deposit_sb.setPrefix("$")
        self.deposit_sb.setMaximum(self.total)
        self.deposit_sb.setDecimals(2)
        self.deposit_sb.setSingleStep(50)
        self.deposit_sb.valueChanged.connect(self._update_balance_preview)

        self.notes_edit = QtWidgets.QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Notas u observaciones (opcional)")

        self.balance_preview = QtWidgets.QLabel(f"Saldo restante: ${self.total:,.2f}")
        self.balance_preview.setStyleSheet("font-weight: 700; color: #2c3e50;")

        form.addRow("Cliente", self.customer_label)
        form.addRow("Fecha límite", self.due_date)
        form.addRow("Depósito inicial", self.deposit_sb)
        form.addRow("Notas", self.notes_edit)
        form.addRow("", self.balance_preview)

        layout.addLayout(form)

        btn_box = QtWidgets.QDialogButtonBox()
        self.accept_btn = btn_box.addButton("Crear apartado", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_btn = btn_box.addButton("Cancelar", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def set_customer(self, customer_id: int | None, customer_name: str | None) -> None:
        self.customer_id = customer_id
        self.customer_label.setText(customer_name or "Sin cliente")

    def _populate_items(self, items: list[dict]) -> None:
        self.items_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [
                item.get("sku", ""),
                item.get("name", ""),
                str(item.get("qty", 0)),
                f"${float(item.get('price', 0.0)):.2f}",
            ]
            for col, val in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(val))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row, col, cell)

    def _update_balance_preview(self) -> None:
        balance = max(self.total - float(self.deposit_sb.value()), 0)
        self.balance_preview.setText(f"Saldo restante: ${balance:,.2f}")

    def _on_accept(self) -> None:
        deposit = float(self.deposit_sb.value())
        if deposit < 0:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El depósito debe ser cero o mayor")
            return
        if deposit > self.total:
            QtWidgets.QMessageBox.warning(self, "Monto inválido", "El depósito no puede exceder el total")
            return
        due_date_str = self.due_date.date().toString("yyyy-MM-dd") if self.due_date.date().isValid() else None
        self.result_data = {
            "deposit": deposit,
            "due_date": due_date_str,
            "notes": self.notes_edit.toPlainText().strip(),
            "customer_id": self.customer_id,
        }
        self.accept()


__all__ = ["LayawayCreateDialog"]
