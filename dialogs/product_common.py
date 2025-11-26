from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class ProductCommonDialog(QtWidgets.QDialog):
    """Dialog to capture an ad-hoc product line (Producto Común)."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Producto Común")
        self.setModal(True)
        self.result_data: Optional[dict] = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #eef2fb; }
            QFrame#Card { background: #ffffff; border-radius: 12px; border: 1px solid #d8e1f1; }
            QLabel#Title { font-size: 22px; font-weight: 600; color: #1f2d4d; }
            QLabel { font-size: 14px; color: #2f3b52; }
            QLineEdit, QDoubleSpinBox { padding: 8px; border: 1px solid #c9d4ec; border-radius: 8px; font-size: 14px; }
            QCheckBox { font-size: 14px; color: #2f3b52; }
            QPushButton { padding: 10px 16px; border-radius: 10px; font-size: 15px; }
            QPushButton#accept { background: #2b8be6; color: white; }
            QPushButton#accept:hover { background: #1f74c2; }
            QPushButton#cancel { background: #e8edf7; color: #2f3b52; }
            QPushButton#cancel:hover { background: #d3dbf0; }
            """
        )

        main_layout = QtWidgets.QVBoxLayout(self)
        container = QtWidgets.QFrame()
        container.setObjectName("Card")
        card_layout = QtWidgets.QHBoxLayout(container)
        form_layout = QtWidgets.QFormLayout()

        self.desc_input = QtWidgets.QLineEdit()
        self.desc_input.setPlaceholderText("Ej. Reparación rápida")
        self.qty_input = QtWidgets.QDoubleSpinBox()
        self.qty_input.setDecimals(3)
        self.qty_input.setRange(0.001, 1_000_000)
        self.qty_input.setValue(1.0)
        self.price_input = QtWidgets.QDoubleSpinBox()
        self.price_input.setDecimals(2)
        self.price_input.setMaximum(1_000_000)
        self.price_input.setValue(0.0)
        self.price_includes_tax = QtWidgets.QCheckBox("Este precio YA incluye IVA")

        form_layout.addRow("Descripción", self.desc_input)
        form_layout.addRow("Cantidad", self.qty_input)
        form_layout.addRow("Precio", self.price_input)
        form_layout.addRow(self.price_includes_tax)
        help_label = QtWidgets.QLabel("Ingrese el precio final que desea cobrar al cliente")
        help_label.setWordWrap(True)
        form_layout.addRow(help_label)

        card_layout.addLayout(form_layout, 3)

        btn_layout = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("PRODUCTO COMÚN")
        title.setObjectName("Title")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        btn_layout.addWidget(title)
        btn_layout.addStretch(1)

        self.accept_btn = QtWidgets.QPushButton("✔ Aceptar")
        self.accept_btn.setObjectName("accept")
        self.accept_btn.clicked.connect(self.accept)
        self.accept_btn.setDefault(True)

        self.cancel_btn = QtWidgets.QPushButton("✖ Cancelar")
        self.cancel_btn.setObjectName("cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.accept_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch(1)
        card_layout.addLayout(btn_layout, 1)

        main_layout.addStretch(1)
        main_layout.addWidget(container)
        main_layout.addStretch(1)

        self.setMinimumWidth(520)

    def accept(self) -> None:  # type: ignore[override]
        name = self.desc_input.text().strip()
        qty = float(self.qty_input.value())
        price = float(self.price_input.value())
        if not name:
            QtWidgets.QMessageBox.warning(self, "Descripción requerida", "Ingresa la descripción del producto")
            return
        if qty <= 0:
            QtWidgets.QMessageBox.warning(self, "Cantidad inválida", "La cantidad debe ser mayor a cero")
            return
        if price <= 0:
            QtWidgets.QMessageBox.warning(self, "Precio inválido", "El precio debe ser mayor a cero")
            return
        self.result_data = {
            "name": name,
            "qty": qty,
            "price": price,
            "price_includes_tax": self.price_includes_tax.isChecked(),
        }
        super().accept()

    def reject(self) -> None:  # type: ignore[override]
        self.result_data = None
        super().reject()
