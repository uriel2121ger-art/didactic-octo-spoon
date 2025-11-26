"""Estado de cuenta de crédito estilo Eleventa."""
from __future__ import annotations

import csv
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from dialogs.credit_payment_dialog import CreditPaymentDialog
from dialogs.previous_credit_dialog import PreviousCreditDialog
from utils import pdf_helper
from utils.animations import fade_in


class CreditStatementDialog(QtWidgets.QDialog):
    def __init__(
        self,
        core,
        customer_id: int,
        customer_name: str,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.core = core
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.setWindowTitle(f"Estado de Cuenta – {customer_name}")
        self.resize(900, 620)
        self._build_ui()
        self._load_data()
        fade_in(self)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(f"ESTADO DE CUENTA – {self.customer_name}")
        title.setStyleSheet("font-size:20px; font-weight:800; letter-spacing:1px;")
        header.addWidget(title)
        header.addStretch(1)
        self.previous_btn = QtWidgets.QPushButton("Consultar crédito anterior…")
        self.previous_btn.clicked.connect(self._open_previous_credit)
        header.addWidget(self.previous_btn)
        layout.addLayout(header)

        filter_layout = QtWidgets.QHBoxLayout()
        self.date_from = QtWidgets.QDateEdit(QtCore.QDate.currentDate().addMonths(-1))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_to = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.include_prev = QtWidgets.QCheckBox("Incluir crédito anterior consolidado")
        self.include_prev.setChecked(True)
        refresh_btn = QtWidgets.QPushButton("Actualizar")
        refresh_btn.clicked.connect(self._load_data)
        today_btn = QtWidgets.QPushButton("Hoy")
        today_btn.clicked.connect(self._set_today)
        month_btn = QtWidgets.QPushButton("Este mes")
        month_btn.clicked.connect(self._set_month)
        all_btn = QtWidgets.QPushButton("Todo")
        all_btn.clicked.connect(self._set_all)
        for btn in (today_btn, month_btn, all_btn):
            btn.setStyleSheet("QPushButton { padding:6px 10px; }")
        filter_layout.addWidget(QtWidgets.QLabel("Desde"))
        filter_layout.addWidget(self.date_from)
        filter_layout.addWidget(QtWidgets.QLabel("Hasta"))
        filter_layout.addWidget(self.date_to)
        filter_layout.addWidget(self.include_prev)
        filter_layout.addStretch(1)
        filter_layout.addWidget(today_btn)
        filter_layout.addWidget(month_btn)
        filter_layout.addWidget(all_btn)
        filter_layout.addWidget(refresh_btn)
        layout.addLayout(filter_layout)

        body = QtWidgets.QHBoxLayout()
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Fecha", "Tipo", "Folio", "Descripción", "Cargo", "Abono", "Saldo"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        body.addWidget(self.table, 3)

        right = QtWidgets.QVBoxLayout()
        self.summary_card = QtWidgets.QFrame()
        self.summary_card.setStyleSheet("QFrame { background:#f6f8ff; border-radius:12px; padding:12px; }")
        summary_layout = QtWidgets.QFormLayout(self.summary_card)
        self.previous_lbl = QtWidgets.QLabel("$0.00")
        self.sales_lbl = QtWidgets.QLabel("$0.00")
        self.payments_lbl = QtWidgets.QLabel("$0.00")
        self.adjust_lbl = QtWidgets.QLabel("$0.00")
        self.current_lbl = QtWidgets.QLabel("$0.00")
        for lbl in (self.previous_lbl, self.sales_lbl, self.payments_lbl, self.adjust_lbl, self.current_lbl):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet("font-weight:700; font-size:14px;")
        summary_layout.addRow("Saldo anterior", self.previous_lbl)
        summary_layout.addRow("Ventas en periodo", self.sales_lbl)
        summary_layout.addRow("Abonos", self.payments_lbl)
        summary_layout.addRow("Ajustes", self.adjust_lbl)
        summary_layout.addRow("Saldo actual", self.current_lbl)
        right.addWidget(self.summary_card)

        self.abono_btn = QtWidgets.QPushButton("F2 – Abonar a deuda")
        self.abono_btn.clicked.connect(self._open_payment)
        self.print_btn = QtWidgets.QPushButton("Imprimir Estado de Cuenta")
        self.print_btn.clicked.connect(self._export_pdf)
        self.export_btn = QtWidgets.QPushButton("Exportar CSV")
        self.export_btn.clicked.connect(self._export_csv)
        right.addWidget(self.abono_btn)
        right.addWidget(self.print_btn)
        right.addWidget(self.export_btn)
        right.addStretch(1)
        body.addLayout(right, 1)
        layout.addLayout(body)

        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self, self.reject)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F2), self, self._open_payment)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+P"), self, self._export_pdf)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+S"), self, self._export_csv)

    def _set_today(self) -> None:
        today = QtCore.QDate.currentDate()
        self.date_from.setDate(today)
        self.date_to.setDate(today)
        self._load_data()

    def _set_month(self) -> None:
        today = QtCore.QDate.currentDate()
        self.date_from.setDate(QtCore.QDate(today.year(), today.month(), 1))
        self.date_to.setDate(today)
        self._load_data()

    def _set_all(self) -> None:
        self.date_from.setDate(QtCore.QDate(2000, 1, 1))
        self.date_to.setDate(QtCore.QDate.currentDate())
        self._load_data()

    def _load_data(self) -> None:
        date_from = self.date_from.date().toString("yyyy-MM-dd") if self.date_from.date() else None
        date_to = self.date_to.date().toString("yyyy-MM-dd") if self.date_to.date() else None
        statement = self.core.get_credit_statement(
            self.customer_id,
            date_from=date_from,
            date_to=date_to,
            include_previous=self.include_prev.isChecked(),
        )
        self._render_statement(statement)

    def _render_statement(self, statement: dict[str, Any]) -> None:
        movements = statement.get("movements", [])
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(movements))
        for row_idx, mv in enumerate(movements):
            values = [
                mv.get("date", ""),
                mv.get("type", ""),
                mv.get("sale_id") or mv.get("payment_id") or "",
                mv.get("description", ""),
                f"{float(mv.get('debit', 0.0) or 0.0):.2f}",
                f"{float(mv.get('credit', 0.0) or 0.0):.2f}",
                f"{float(mv.get('balance_after', 0.0) or 0.0):.2f}",
            ]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if col >= 4:
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, col, item)
        self.table.setUpdatesEnabled(True)

        self.previous_lbl.setText(f"${float(statement.get('previous_balance', 0.0) or 0.0):,.2f}")
        self.sales_lbl.setText(f"${float(statement.get('total_sales', 0.0) or 0.0):,.2f}")
        self.payments_lbl.setText(f"${float(statement.get('total_payments', 0.0) or 0.0):,.2f}")
        self.adjust_lbl.setText("$0.00")
        self.current_lbl.setText(f"${float(statement.get('current_balance', 0.0) or 0.0):,.2f}")

    def _open_payment(self) -> None:
        dlg = CreditPaymentDialog(
            customer_name=self.customer_name,
            credit_limit=0.0,
            credit_balance=float(self.core.get_credit_balance(self.customer_id)),
            parent=self,
        )
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            data = dlg.result_data
            try:
                self.core.register_credit_payment(self.customer_id, data["amount"], data.get("notes"))
                QtWidgets.QMessageBox.information(self, "Abono registrado", "Se registró el abono correctamente")
                self._load_data()
            except Exception as exc:  # pragma: no cover - UI path
                QtWidgets.QMessageBox.critical(self, "Error", str(exc))

    def _export_csv(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar CSV", "estado_cuenta.csv", "CSV (*.csv)")
        if not path:
            return
        statement = self.core.get_credit_statement(
            self.customer_id,
            date_from=self.date_from.date().toString("yyyy-MM-dd"),
            date_to=self.date_to.date().toString("yyyy-MM-dd"),
            include_previous=self.include_prev.isChecked(),
        )
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Fecha", "Tipo", "Folio", "Descripción", "Cargo", "Abono", "Saldo"])
            for mv in statement.get("movements", []):
                writer.writerow(
                    [
                        mv.get("date"),
                        mv.get("type"),
                        mv.get("sale_id") or mv.get("payment_id") or "",
                        mv.get("description"),
                        f"{float(mv.get('debit', 0.0) or 0.0):.2f}",
                        f"{float(mv.get('credit', 0.0) or 0.0):.2f}",
                        f"{float(mv.get('balance_after', 0.0) or 0.0):.2f}",
                    ]
                )
        QtWidgets.QMessageBox.information(self, "Exportado", "CSV generado correctamente")

    def _export_pdf(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Exportar PDF", "estado_cuenta.pdf", "PDF (*.pdf)")
        if not path:
            return
        statement = self.core.get_credit_statement(
            self.customer_id,
            date_from=self.date_from.date().toString("yyyy-MM-dd"),
            date_to=self.date_to.date().toString("yyyy-MM-dd"),
            include_previous=self.include_prev.isChecked(),
        )
        pdf_helper.export_credit_statement_pdf(statement, path)
        QtWidgets.QMessageBox.information(self, "Exportado", "PDF generado correctamente")

    def _open_previous_credit(self) -> None:
        balance_info = self.core.get_previous_credit_balance(self.customer_id)
        dlg = PreviousCreditDialog(self.customer_name, balance_info, self)
        dlg.exec()
