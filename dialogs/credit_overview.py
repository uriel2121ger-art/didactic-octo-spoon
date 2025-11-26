from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from pos_core import POSCore, STATE
from dialogs.credit_payment_dialog import CreditPaymentDialog
from utils import ticket_engine


class CreditOverviewDialog(QtWidgets.QDialog):
    """Show a credit statement with history and abono shortcut."""

    def __init__(self, core: POSCore, customer_id: int, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self.customer_id = customer_id
        self.customer_row = self.core.get_customer(customer_id)
        self.setWindowTitle("Estado de cuenta")
        self.setMinimumSize(700, 480)
        self.result_data: dict | None = None
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QtWidgets.QHBoxLayout()
        self.name_label = QtWidgets.QLabel()
        self.name_label.setStyleSheet("font-size:18px; font-weight:700;")
        self.balance_label = QtWidgets.QLabel()
        self.balance_label.setStyleSheet("font-size:16px; color:#c0392b; font-weight:700;")
        header.addWidget(self.name_label)
        header.addStretch(1)
        header.addWidget(self.balance_label)
        layout.addLayout(header)

        summary_frame = QtWidgets.QFrame()
        summary_frame.setStyleSheet("QFrame { background:#f6f8fb; border-radius:10px; padding:10px; }")
        grid = QtWidgets.QGridLayout(summary_frame)
        self.limit_label = QtWidgets.QLabel("Límite: --")
        self.payments_total_label = QtWidgets.QLabel("Abonos: --")
        grid.addWidget(self.limit_label, 0, 0)
        grid.addWidget(self.payments_total_label, 0, 1)
        layout.addWidget(summary_frame)

        tabs = QtWidgets.QTabWidget()
        # ventas a crédito
        self.sales_table = QtWidgets.QTableWidget(0, 4)
        self.sales_table.setHorizontalHeaderLabels(["ID", "Fecha", "Total", "Método"])
        self.sales_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        # abonos
        self.payments_table = QtWidgets.QTableWidget(0, 3)
        self.payments_table.setHorizontalHeaderLabels(["Fecha", "Monto", "Notas"])
        self.payments_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)

        sales_tab = QtWidgets.QWidget()
        v1 = QtWidgets.QVBoxLayout(sales_tab)
        v1.addWidget(self.sales_table)
        payments_tab = QtWidgets.QWidget()
        v2 = QtWidgets.QVBoxLayout(payments_tab)
        v2.addWidget(self.payments_table)

        tabs.addTab(sales_tab, "Ventas a crédito")
        tabs.addTab(payments_tab, "Abonos")
        layout.addWidget(tabs)

        btns = QtWidgets.QHBoxLayout()
        self.pay_btn = QtWidgets.QPushButton("Abonar")
        self.pay_btn.clicked.connect(self._register_payment)
        self.print_btn = QtWidgets.QPushButton("Imprimir estado de cuenta")
        self.print_btn.clicked.connect(self._print_statement)
        close_btn = QtWidgets.QPushButton("Cerrar")
        close_btn.clicked.connect(self.reject)
        btns.addWidget(self.pay_btn)
        btns.addWidget(self.print_btn)
        btns.addStretch(1)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _load_data(self) -> None:
        if not self.customer_row:
            return
        name = (self.customer_row.get("full_name") or "").strip() or self.customer_row.get("first_name") or "Cliente"
        self.name_label.setText(name)
        summary = self.core.get_credit_summary(self.customer_id)
        balance = float(summary.get("credit_balance", 0.0) or 0.0)
        credit_limit = float(summary.get("credit_limit", 0.0) or 0.0)
        self.balance_label.setText(f"Saldo: ${balance:,.2f}")
        self.limit_label.setText(f"Límite: ${credit_limit:,.2f}")
        self.payments_total_label.setText(f"Abonos: ${float(summary.get('total_payments', 0.0)) :,.2f}")

        payments = summary.get("payments", []) or []
        self.payments_table.setRowCount(len(payments))
        for row_idx, p in enumerate(payments):
            values = [p.get("timestamp", ""), f"${float(p.get('amount', 0.0)):.2f}", p.get("notes") or ""]
            for col, val in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.payments_table.setItem(row_idx, col, item)

        sales = summary.get("sales", []) or []
        self.sales_table.setRowCount(len(sales))
        for row_idx, s in enumerate(sales):
            values = [s.get("id"), s.get("ts"), f"${float(s.get('total', 0.0)):.2f}", s.get("payment_method")]
            for col, val in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.sales_table.setItem(row_idx, col, item)

    def _register_payment(self) -> None:
        summary = self.core.get_credit_summary(self.customer_id)
        balance = float(summary.get("credit_balance", 0.0) or 0.0)
        credit_limit = float(summary.get("credit_limit", 0.0) or 0.0)
        if balance <= 0:
            QtWidgets.QMessageBox.information(self, "Sin saldo", "Este cliente no tiene adeudo")
            return
        dlg = CreditPaymentDialog(
            customer_name=self.name_label.text(),
            credit_limit=credit_limit,
            credit_balance=balance,
            parent=self,
        )
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            self.core.register_credit_payment(
                self.customer_id,
                dlg.result_data["amount"],
                dlg.result_data.get("notes") or None,
                STATE.user_id,
            )
            QtWidgets.QMessageBox.information(self, "Abono", "Abono registrado correctamente")
            self._load_data()

    def _print_statement(self) -> None:
        summary = self.core.get_credit_summary(self.customer_id)
        ticket_engine.print_credit_payment(
            customer_name=self.name_label.text(),
            amount=0.0,
            new_balance=float(summary.get("credit_balance", 0.0) or 0.0),
            notes="Estado de cuenta",
        )
        QtWidgets.QMessageBox.information(self, "Impresión", "Estado de cuenta enviado a impresión")


__all__ = ["CreditOverviewDialog"]
