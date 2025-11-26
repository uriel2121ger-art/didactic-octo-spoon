"""Discount dialog for line and global discounts (Eleventa-style).

Provides modern KDE-styled UI to apply discounts by amount or percentage
with dynamic recalculation and validation.
"""
from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from utils.animations import fade_in


class DiscountDialog(QtWidgets.QDialog):
    def __init__(self, price_normal: float, *, current_price: Optional[float] = None, parent=None):
        super().__init__(parent)
        self.price_normal = max(float(price_normal), 0.0)
        self.current_price = float(current_price) if current_price is not None else self.price_normal
        self.result_data: Optional[dict[str, float | str]] = None
        self.setWindowTitle("Descuento")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._build_ui()
        self._recalculate()
        fade_in(self)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f7f9fc;
            }
            QFrame#card {
                background: white;
                border-radius: 14px;
                border: 1px solid #dfe6f1;
            }
            QLabel#title {
                font-size: 22px;
                font-weight: 700;
                color: #2c3e50;
            }
            QRadioButton {
                font-size: 14px;
            }
            QDoubleSpinBox {
                font-size: 16px;
                padding: 8px;
                border: 1px solid #cfd8e3;
                border-radius: 8px;
            }
            QPushButton#confirm {
                background: #27ae60;
                color: white;
                font-weight: 600;
                padding: 10px 18px;
                border-radius: 10px;
            }
            QPushButton#cancel {
                background: #ecf0f1;
                color: #2c3e50;
                font-weight: 600;
                padding: 10px 18px;
                border-radius: 10px;
            }
            QLabel.value-label {
                font-size: 18px;
                font-weight: 600;
                qproperty-alignment: AlignCenter;
            }
            """
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        card = QtWidgets.QFrame()
        card.setObjectName("card")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(16)

        title = QtWidgets.QLabel("DESCUENTO")
        title.setObjectName("title")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        body_layout = QtWidgets.QHBoxLayout()
        body_layout.setSpacing(18)

        form_layout = QtWidgets.QVBoxLayout()
        self.rb_amount = QtWidgets.QRadioButton("Por Monto ($)")
        self.rb_percent = QtWidgets.QRadioButton("Porcentaje (%)")
        self.rb_amount.setChecked(True)
        self.rb_amount.toggled.connect(self._recalculate)
        self.rb_percent.toggled.connect(self._recalculate)

        self.sb_value = QtWidgets.QDoubleSpinBox()
        self.sb_value.setDecimals(2)
        self.sb_value.setMaximum(1_000_000)
        self.sb_value.setValue(0.0)
        self.sb_value.valueChanged.connect(self._recalculate)

        form_layout.addWidget(self.rb_amount)
        form_layout.addWidget(self.rb_percent)
        form_layout.addWidget(self.sb_value)
        form_layout.addStretch(1)

        body_layout.addLayout(form_layout, 1)

        info_layout = QtWidgets.QVBoxLayout()
        info_layout.setSpacing(8)
        info_layout.addWidget(QtWidgets.QLabel("Precio normal:"))
        self.lbl_price_normal = QtWidgets.QLabel()
        self.lbl_price_normal.setProperty("class", "value-label")
        info_layout.addWidget(self.lbl_price_normal)

        info_layout.addWidget(QtWidgets.QLabel("Nuevo precio:"))
        self.lbl_new_price = QtWidgets.QLabel()
        self.lbl_new_price.setProperty("class", "value-label")
        info_layout.addWidget(self.lbl_new_price)

        self.lbl_discount = QtWidgets.QLabel()
        self.lbl_discount.setProperty("class", "value-label")
        info_layout.addWidget(self.lbl_discount)
        info_layout.addStretch(1)

        body_layout.addLayout(info_layout, 1)
        card_layout.addLayout(body_layout)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch(1)
        self.accept_btn = QtWidgets.QPushButton("Aceptar")
        self.accept_btn.setObjectName("confirm")
        self.accept_btn.clicked.connect(self.accept)
        self.cancel_btn = QtWidgets.QPushButton("Cancelar")
        self.cancel_btn.setObjectName("cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.accept_btn)
        card_layout.addLayout(btn_layout)

        layout.addWidget(card)

        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Return), self, activated=self.accept)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Enter), self, activated=self.accept)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self, activated=self.reject)

    def _recalculate(self) -> None:
        mode = "amount" if self.rb_amount.isChecked() else "percent"
        value = float(self.sb_value.value())
        discount_amount = 0.0
        discount_percent = 0.0
        if self.price_normal <= 0:
            new_price = 0.0
        else:
            if mode == "percent":
                discount_percent = value
                discount_amount = self.price_normal * (discount_percent / 100.0)
            else:
                discount_amount = value
                discount_percent = (discount_amount / self.price_normal) * 100 if self.price_normal else 0
            new_price = max(self.price_normal - discount_amount, 0)
        self.lbl_price_normal.setText(f"${self.price_normal:,.2f}")
        self.lbl_new_price.setText(f"${new_price:,.2f}")
        if mode == "percent":
            self.lbl_discount.setText(f"Descuento: {discount_percent:.2f}%")
        else:
            self.lbl_discount.setText(f"Descuento: ${discount_amount:,.2f}")
        self._preview = {
            "type": mode,
            "value": value,
            "discount_amount": discount_amount,
            "discount_percent": discount_percent,
            "new_price": new_price,
        }

    def accept(self) -> None:  # type: ignore[override]
        mode = "amount" if self.rb_amount.isChecked() else "percent"
        value = float(self.sb_value.value())
        if mode == "percent" and value > 100:
            QtWidgets.QMessageBox.warning(self, "Porcentaje inválido", "El porcentaje no puede ser mayor a 100%")
            return
        if mode == "amount" and value >= self.price_normal:
            QtWidgets.QMessageBox.warning(
                self,
                "Monto inválido",
                "El monto de descuento no puede ser mayor o igual al precio normal",
            )
            return
        # Re-run to ensure preview consistent
        self._recalculate()
        self.result_data = self._preview
        super().accept()
