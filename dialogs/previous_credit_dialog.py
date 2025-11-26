"""Dialog to view previous consolidated credit balance."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from utils.animations import fade_in


class PreviousCreditDialog(QtWidgets.QDialog):
    def __init__(self, customer_name: str, balance_info: dict | None, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Crédito anterior")
        self.setModal(True)
        self.resize(420, 240)
        self.balance_info = balance_info or {}
        self._build_ui(customer_name)
        fade_in(self)

    def _build_ui(self, customer_name: str) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel(f"Crédito anterior de {customer_name}")
        header.setStyleSheet("font-size:18px; font-weight:700;")
        layout.addWidget(header)

        frame = QtWidgets.QFrame()
        frame.setStyleSheet("QFrame { background:#f7f9ff; border-radius:10px; padding:12px; }")
        v = QtWidgets.QVBoxLayout(frame)
        if self.balance_info:
            balance = float(self.balance_info.get("balance", 0.0) or 0.0)
            desc = self.balance_info.get("description") or "Saldo migrado"
            created = self.balance_info.get("created_at") or "--"
            v.addWidget(QtWidgets.QLabel(f"Saldo consolidado: <b>${balance:,.2f}</b>"))
            v.addWidget(QtWidgets.QLabel(f"Descripción: {desc}"))
            v.addWidget(QtWidgets.QLabel(f"Registrado: {created}"))
        else:
            msg = QtWidgets.QLabel("Sin crédito anterior registrado.")
            msg.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            v.addWidget(msg)
        layout.addWidget(frame)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        close_btn = QtWidgets.QPushButton("Cerrar")
        close_btn.clicked.connect(self.reject)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self, self.reject)
