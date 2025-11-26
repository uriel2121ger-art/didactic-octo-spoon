#!/usr/bin/env python3
"""Customer Pro dialog with avatar, VIP flag and credit settings."""
from __future__ import annotations

import hashlib
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from utils.animations import fade_in


def _pastel_color(seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    r = (r + 255) // 2
    g = (g + 255) // 2
    b = (b + 255) // 2
    return f"rgb({r},{g},{b})"


class CustomerProDialog(QtWidgets.QDialog):
    def __init__(self, customer: Optional[dict] = None, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Cliente PRO")
        self.setModal(True)
        self.resize(520, 420)
        self.customer = customer or {}
        self.result_data: Optional[dict] = None
        self._build_ui()
        fade_in(self)
        if customer:
            self._load_customer(customer)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        frame = QtWidgets.QFrame()
        frame.setStyleSheet("QFrame { background: #f6f8ff; border-radius: 12px; padding: 14px; }")
        form_layout = QtWidgets.QGridLayout(frame)

        self.avatar = QtWidgets.QLabel("CL")
        self.avatar.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedSize(80, 80)
        self.avatar.setStyleSheet(
            "QLabel { border-radius: 40px; background: #dfe8ff; font-weight: 700; font-size: 22px; color: #1f3b87; }"
        )

        name_title = QtWidgets.QLabel("Datos del cliente")
        name_title.setStyleSheet("font-size:18px; font-weight:700;")

        self.first_name = QtWidgets.QLineEdit()
        self.last_name = QtWidgets.QLineEdit()
        self.phone = QtWidgets.QLineEdit()
        self.email = QtWidgets.QLineEdit()
        self.rfc = QtWidgets.QLineEdit()
        self.razon_social = QtWidgets.QLineEdit()
        self.domicilio1 = QtWidgets.QLineEdit()
        self.domicilio2 = QtWidgets.QLineEdit()
        self.colonia = QtWidgets.QLineEdit()
        self.municipio = QtWidgets.QLineEdit()
        self.estado = QtWidgets.QLineEdit()
        self.codigo_postal = QtWidgets.QLineEdit()
        self.regimen_fiscal = QtWidgets.QLineEdit()
        self.notes = QtWidgets.QPlainTextEdit()
        self.vip_cb = QtWidgets.QCheckBox("Cliente VIP")
        self.credit_enabled = QtWidgets.QCheckBox("Tiene crédito autorizado")
        self.credit_enabled.setChecked(True)
        self.credit_limit = QtWidgets.QDoubleSpinBox()
        self.credit_limit.setMaximum(1_000_000)
        self.credit_limit.setPrefix("$")
        self.credit_limit.setDecimals(2)
        self.credit_balance = QtWidgets.QLabel("$0.00")
        self.credit_balance.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.credit_balance.setStyleSheet("font-weight:700; color:#1c2833;")

        form_layout.addWidget(self.avatar, 0, 0, 2, 1)
        form_layout.addWidget(name_title, 0, 1, 1, 2)
        form_layout.addWidget(QtWidgets.QLabel("Nombre(s)"), 1, 1)
        form_layout.addWidget(self.first_name, 1, 2)
        form_layout.addWidget(QtWidgets.QLabel("Apellidos"), 2, 1)
        form_layout.addWidget(self.last_name, 2, 2)
        form_layout.addWidget(QtWidgets.QLabel("Teléfono"), 3, 1)
        form_layout.addWidget(self.phone, 3, 2)
        form_layout.addWidget(QtWidgets.QLabel("Email"), 4, 1)
        form_layout.addWidget(self.email, 4, 2)
        form_layout.addWidget(QtWidgets.QLabel("RFC"), 5, 1)
        form_layout.addWidget(self.rfc, 5, 2)
        form_layout.addWidget(QtWidgets.QLabel("Razón social"), 6, 1)
        form_layout.addWidget(self.razon_social, 6, 2)
        form_layout.addWidget(QtWidgets.QLabel("Domicilio línea 1"), 7, 1)
        form_layout.addWidget(self.domicilio1, 7, 2)
        form_layout.addWidget(QtWidgets.QLabel("Domicilio línea 2"), 8, 1)
        form_layout.addWidget(self.domicilio2, 8, 2)
        form_layout.addWidget(QtWidgets.QLabel("Colonia"), 9, 1)
        form_layout.addWidget(self.colonia, 9, 2)
        form_layout.addWidget(QtWidgets.QLabel("Municipio"), 10, 1)
        form_layout.addWidget(self.municipio, 10, 2)
        form_layout.addWidget(QtWidgets.QLabel("Estado"), 11, 1)
        form_layout.addWidget(self.estado, 11, 2)
        form_layout.addWidget(QtWidgets.QLabel("Código postal"), 12, 1)
        form_layout.addWidget(self.codigo_postal, 12, 2)
        form_layout.addWidget(QtWidgets.QLabel("Régimen fiscal"), 13, 1)
        form_layout.addWidget(self.regimen_fiscal, 13, 2)
        form_layout.addWidget(QtWidgets.QLabel("Notas internas"), 14, 1)
        form_layout.addWidget(self.notes, 14, 2)
        form_layout.addWidget(self.vip_cb, 15, 1, 1, 2)
        form_layout.addWidget(self.credit_enabled, 16, 1, 1, 2)
        form_layout.addWidget(QtWidgets.QLabel("Límite de crédito"), 17, 1)
        form_layout.addWidget(self.credit_limit, 17, 2)
        form_layout.addWidget(QtWidgets.QLabel("Saldo actual"), 18, 1)
        form_layout.addWidget(self.credit_balance, 18, 2)

        layout.addWidget(frame)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        self.save_btn = QtWidgets.QPushButton("✔ Guardar")
        self.cancel_btn = QtWidgets.QPushButton("✖ Cancelar")
        self.save_btn.setDefault(True)
        btns.addWidget(self.save_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

        self.save_btn.clicked.connect(self._on_accept)
        self.cancel_btn.clicked.connect(self.reject)

    def _load_customer(self, customer: dict) -> None:
        self.first_name.setText(customer.get("first_name") or "")
        self.last_name.setText(customer.get("last_name") or "")
        self.phone.setText(customer.get("phone") or "")
        self.email.setText(customer.get("email") or "")
        self.rfc.setText(customer.get("rfc") or "")
        self.razon_social.setText(customer.get("razon_social") or "")
        self.domicilio1.setText(customer.get("domicilio1") or "")
        self.domicilio2.setText(customer.get("domicilio2") or "")
        self.colonia.setText(customer.get("colonia") or "")
        self.municipio.setText(customer.get("municipio") or "")
        self.estado.setText(customer.get("estado") or "")
        self.codigo_postal.setText(customer.get("codigo_postal") or "")
        self.regimen_fiscal.setText(customer.get("regimen_fiscal") or "")
        self.notes.setPlainText(customer.get("notes") or "")
        self.vip_cb.setChecked(bool(customer.get("vip")))
        self.credit_limit.setValue(float(customer.get("credit_limit", 0.0) or 0.0))
        self.credit_enabled.setChecked(float(customer.get("credit_limit", 0.0) or 0.0) > 0)
        balance = float(customer.get("credit_balance", 0.0) or 0.0)
        self.credit_balance.setText(f"${balance:,.2f}")
        initials = self._initials()
        self._update_avatar(initials)

    def _initials(self) -> str:
        parts = [self.first_name.text().strip(), self.last_name.text().strip()]
        return "".join([p[0] for p in parts if p][:2]).upper() or "CL"

    def _update_avatar(self, initials: str) -> None:
        bg = _pastel_color(initials)
        self.avatar.setText(initials)
        self.avatar.setStyleSheet(
            f"QLabel {{ border-radius: 40px; background: {bg}; font-weight: 700; font-size: 22px; color: white; }}"
        )

    def _on_accept(self) -> None:
        first = self.first_name.text().strip()
        if not first:
            QtWidgets.QMessageBox.warning(self, "Nombre requerido", "El nombre no puede estar vacío")
            return
        initials = self._initials()
        self._update_avatar(initials)
        credit_limit = self.credit_limit.value() if self.credit_enabled.isChecked() else 0.0
        credit_balance = 0.0 if not self.credit_enabled.isChecked() else None
        self.result_data = {
            "first_name": first,
            "last_name": self.last_name.text().strip(),
            "phone": self.phone.text().strip(),
            "email": self.email.text().strip(),
            "rfc": self.rfc.text().strip(),
            "razon_social": self.razon_social.text().strip(),
            "domicilio1": self.domicilio1.text().strip(),
            "domicilio2": self.domicilio2.text().strip(),
            "colonia": self.colonia.text().strip(),
            "municipio": self.municipio.text().strip(),
            "estado": self.estado.text().strip(),
            "codigo_postal": self.codigo_postal.text().strip(),
            "regimen_fiscal": self.regimen_fiscal.text().strip(),
            "notes": self.notes.toPlainText().strip(),
            "vip": self.vip_cb.isChecked(),
            "credit_limit": credit_limit,
            "credit_balance": credit_balance,
        }
        self.accept()
