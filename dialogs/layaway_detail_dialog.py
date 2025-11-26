"""Detail dialog for layaways: items, payments, and actions."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from utils.animations import fade_in

from dialogs.layaway_payment_dialog import LayawayPaymentDialog


class LayawayDetailDialog(QtWidgets.QDialog):
    def __init__(self, core, layaway_id: int, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self.layaway_id = layaway_id
        self.setWindowTitle(f"Apartado #{layaway_id}")
        self.setMinimumSize(680, 520)
        self.result_action: str | None = None
        self._build_ui()
        self._load_data()
        fade_in(self)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        self.header_lbl = QtWidgets.QLabel()
        self.header_lbl.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(self.header_lbl)

        grids = QtWidgets.QHBoxLayout()
        self.items_table = QtWidgets.QTableWidget(0, 4)
        self.items_table.setHorizontalHeaderLabels(["Producto", "Cantidad", "Precio", "Subtotal"])
        self.items_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        grids.addWidget(self.items_table, 3)

        self.payments_table = QtWidgets.QTableWidget(0, 3)
        self.payments_table.setHorizontalHeaderLabels(["Fecha", "Monto", "Notas"])
        self.payments_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        grids.addWidget(self.payments_table, 2)
        layout.addLayout(grids)

        btn_layout = QtWidgets.QHBoxLayout()
        self.pay_btn = QtWidgets.QPushButton("Abonar…")
        self.liquidate_btn = QtWidgets.QPushButton("Liquidar")
        self.cancel_btn = QtWidgets.QPushButton("Cancelar apartado")
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.pay_btn)
        btn_layout.addWidget(self.liquidate_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.pay_btn.clicked.connect(self._pay)
        self.liquidate_btn.clicked.connect(self._liquidate)
        self.cancel_btn.clicked.connect(self._cancel)

    def _load_data(self) -> None:
        layaway = self.core.get_layaway(self.layaway_id)
        if not layaway:
            QtWidgets.QMessageBox.critical(self, "Error", "Apartado no encontrado")
            self.reject()
            return
        status = layaway.get("display_status") or layaway.get("status")
        paid = float(layaway.get("paid_total", 0.0))
        balance = float(layaway.get("balance_calc", layaway.get("balance", 0.0)))
        header = (
            f"Cliente: {layaway.get('customer_name') or 'Sin cliente'} | "
            f"Creado: {layaway.get('created_at', '')} | Vence: {layaway.get('due_date') or '-'} | "
            f"Estado: {status}"
        )
        self.header_lbl.setText(header)
        self.pay_btn.setEnabled(status not in ("cancelado", "liquidado"))
        self.liquidate_btn.setEnabled(balance > 0 and status not in ("cancelado", "liquidado"))
        self.cancel_btn.setEnabled(status != "cancelado")

        items = self.core.get_layaway_items(self.layaway_id)
        self.items_table.setRowCount(len(items))
        for r, item in enumerate(items):
            values = [
                item.get("name", ""),
                f"{float(item['qty']):.2f}",
                f"${float(item['price']):.2f}",
                f"${float(item['total']):.2f}",
            ]
            for c, val in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(val))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(r, c, cell)

        payments = self.core.get_layaway_payments(self.layaway_id)
        self.payments_table.setRowCount(len(payments))
        for r, pay in enumerate(payments):
            values = [pay["timestamp"], f"${float(pay['amount']):.2f}", pay.get("notes", "") or ""]
            for c, val in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(val))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.payments_table.setItem(r, c, cell)

    def _pay(self) -> None:
        layaway = self.core.get_layaway(self.layaway_id)
        if not layaway:
            return
        dialog = LayawayPaymentDialog(
            layaway.get("customer_name") or "Cliente",
            layaway["total"],
            layaway.get("paid_total", 0.0),
            layaway.get("balance_calc", layaway.get("balance", 0.0)),
            self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted or not dialog.result_data:
            return
        try:
            self.core.add_layaway_payment(
                self.layaway_id,
                dialog.result_data["amount"],
                notes=dialog.result_data.get("notes"),
            )
            self.result_action = "paid"
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo registrar el abono: {exc}")
            return
        self._load_data()
        QtWidgets.QMessageBox.information(self, "Abono registrado", "El abono se registró correctamente")

    def _liquidate(self) -> None:
        if QtWidgets.QMessageBox.question(self, "Liquidar", "¿Liquidar este apartado?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.core.liquidate_layaway(self.layaway_id)
            self.result_action = "liquidated"
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo liquidar: {exc}")
            return
        self._load_data()

    def _cancel(self) -> None:
        if QtWidgets.QMessageBox.question(self, "Cancelar", "¿Cancelar este apartado y devolver stock?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.core.cancel_layaway(self.layaway_id)
            self.result_action = "cancelled"
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo cancelar: {exc}")
            return
        self._load_data()


__all__ = ["LayawayDetailDialog"]
