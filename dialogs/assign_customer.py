#!/usr/bin/env python3
"""Customer selector dialog with avatars and VIP filter."""
from __future__ import annotations

import hashlib
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from pos_core import POSCore


def _pastel(seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    r = (int(h[0:2], 16) + 255) // 2
    g = (int(h[2:4], 16) + 255) // 2
    b = (int(h[4:6], 16) + 255) // 2
    return f"rgb({r},{g},{b})"


class AssignCustomerDialog(QtWidgets.QDialog):
    def __init__(self, core: POSCore, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self.selected_customer_id: Optional[int] = None
        self.selected_customer_name: Optional[str] = None
        self.setWindowTitle("Asignar cliente")
        self.resize(640, 460)
        self._build_ui()
        self._wire_events()
        self.refresh_table()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel("Selecciona un cliente")
        header.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(header)

        search_row = QtWidgets.QHBoxLayout()
        self.search_line = QtWidgets.QLineEdit()
        self.search_line.setPlaceholderText("Buscar nombre o teléfono…")
        self.vip_only = QtWidgets.QCheckBox("Solo VIP")
        search_row.addWidget(self.search_line)
        search_row.addWidget(self.vip_only)
        layout.addLayout(search_row)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Avatar", "Nombre", "Teléfono", "Email", "Crédito"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.assign_btn = QtWidgets.QPushButton("Asignar")
        self.cancel_btn = QtWidgets.QPushButton("Cancelar")
        btns.addWidget(self.assign_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

    def _wire_events(self) -> None:
        self.search_line.textChanged.connect(self.refresh_table)
        self.vip_only.stateChanged.connect(self.refresh_table)
        self.assign_btn.clicked.connect(self._assign_selected)
        self.cancel_btn.clicked.connect(self.reject)
        self.table.itemDoubleClicked.connect(lambda *_: self._assign_selected())
        self.search_line.returnPressed.connect(self.refresh_table)

    def refresh_table(self) -> None:
        query = self.search_line.text().strip()
        customers = self.core.search_customers(query) if query else self.core.list_customers(limit=300)
        filtered = [c for c in customers if not self.vip_only.isChecked() or c.get("vip")]
        self.table.setRowCount(len(filtered))
        for row_idx, row in enumerate(filtered):
            record = dict(row)
            full_name = (record.get("full_name") or "").strip() or record.get("first_name") or ""
            initials = "".join([p[0] for p in full_name.split() if p][:2]).upper() or "CL"
            bg = _pastel(full_name or initials)
            values = [
                record.get("id"),
                initials,
                full_name,
                record.get("phone") or "",
                record.get("email") or "",
                f"{float(record.get('credit_balance', 0.0) or 0.0):.2f}",
            ]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if col == 1:
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                    item.setBackground(QtGui.QColor(bg))
                self.table.setItem(row_idx, col, item)

    def _assign_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Elige un cliente para asignar")
            return
        self.selected_customer_id = int(self.table.item(row, 0).text())
        self.selected_customer_name = self.table.item(row, 2).text()
        self.accept()
