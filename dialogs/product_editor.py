from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from pos_core import STATE, POSCore

logger = logging.getLogger(__name__)


class ProductEditorDialog(QtWidgets.QDialog):
    """
    Dialogo de creación/edición de productos al estilo Eleventa/KDE.
    Permite captura de precios, ganancia, inventario y tipo de venta.
    """

    def __init__(
        self,
        core: POSCore,
        product: Optional[dict[str, Any]] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.core = core
        self.product = product
        self.product_id: Optional[int] = product.get("id") if product else None
        self._updating_fields = False
        self.setWindowTitle("Editar producto" if self.product_id else "Nuevo producto")
        self.setModal(True)
        self.resize(620, 520)
        self._build_ui()
        self._wire_shortcuts()
        if product:
            self._load_product(product)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        frame = QtWidgets.QFrame()
        frame.setObjectName("kdeFrame")
        frame.setStyleSheet(
            """
            QFrame#kdeFrame {
                background: #f6f8fb;
                border-radius: 10px;
                padding: 12px;
            }
            """
        )
        frame_layout = QtWidgets.QVBoxLayout(frame)
        header = QtWidgets.QLabel("<b style='font-size:16px'>PRODUCTOS</b>")
        header.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(header)

        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.sku_edit = QtWidgets.QLineEdit()
        self.sku_edit.setPlaceholderText("Código / SKU / EAN")
        self.sku_edit.setClearButtonEnabled(True)
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("Descripción")

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItem("Unidad", {"unit": "Unidad", "allow_decimal": False, "is_kit": False})
        self.type_combo.addItem("A granel", {"unit": "Granel", "allow_decimal": True, "is_kit": False})
        self.type_combo.addItem("Paquete / Kit", {"unit": "Paquete", "allow_decimal": False, "is_kit": True})

        self.cost_spin = QtWidgets.QDoubleSpinBox()
        self.cost_spin.setMaximum(1_000_000)
        self.cost_spin.setDecimals(2)
        self.cost_spin.valueChanged.connect(self._recalc_from_cost)

        self.margin_spin = QtWidgets.QDoubleSpinBox()
        self.margin_spin.setSuffix(" %")
        self.margin_spin.setDecimals(2)
        self.margin_spin.setRange(-1000, 1000)
        self.margin_spin.valueChanged.connect(self._recalc_from_margin)

        self.price_spin = QtWidgets.QDoubleSpinBox()
        self.price_spin.setMaximum(1_000_000)
        self.price_spin.setDecimals(2)
        self.price_spin.valueChanged.connect(self._recalc_margin_from_price)

        self.wholesale_spin = QtWidgets.QDoubleSpinBox()
        self.wholesale_spin.setMaximum(1_000_000)
        self.wholesale_spin.setDecimals(2)

        self.dept_combo = QtWidgets.QComboBox()
        self.dept_combo.setEditable(True)
        self.dept_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.dept_combo.setPlaceholderText("Departamento")

        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.setEditable(True)
        self.provider_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.provider_combo.setPlaceholderText("Proveedor")

        self.inv_checkbox = QtWidgets.QCheckBox("Este producto SÍ utiliza inventario")
        self.inv_checkbox.setChecked(True)
        self.inv_checkbox.stateChanged.connect(self._toggle_inventory_fields)
        self.stock_spin = QtWidgets.QDoubleSpinBox()
        self.stock_spin.setDecimals(3)
        self.stock_spin.setRange(0, 1_000_000)
        self.min_spin = QtWidgets.QDoubleSpinBox()
        self.min_spin.setDecimals(3)
        self.min_spin.setRange(0, 1_000_000)
        self.max_spin = QtWidgets.QDoubleSpinBox()
        self.max_spin.setDecimals(3)
        self.max_spin.setRange(0, 1_000_000)

        row = 0
        form.addWidget(QtWidgets.QLabel("Código / SKU"), row, 0)
        form.addWidget(self.sku_edit, row, 1)
        row += 1
        form.addWidget(QtWidgets.QLabel("Descripción"), row, 0)
        form.addWidget(self.name_edit, row, 1, 1, 2)
        row += 1
        form.addWidget(QtWidgets.QLabel("Tipo de venta"), row, 0)
        form.addWidget(self.type_combo, row, 1)
        row += 1
        form.addWidget(QtWidgets.QLabel("Costo"), row, 0)
        form.addWidget(self.cost_spin, row, 1)
        form.addWidget(QtWidgets.QLabel("% Ganancia"), row, 2)
        form.addWidget(self.margin_spin, row, 3)
        row += 1
        form.addWidget(QtWidgets.QLabel("Precio venta"), row, 0)
        form.addWidget(self.price_spin, row, 1)
        form.addWidget(QtWidgets.QLabel("Precio mayoreo"), row, 2)
        form.addWidget(self.wholesale_spin, row, 3)
        row += 1
        form.addWidget(QtWidgets.QLabel("Departamento"), row, 0)
        form.addWidget(self.dept_combo, row, 1)
        form.addWidget(QtWidgets.QLabel("Proveedor"), row, 2)
        form.addWidget(self.provider_combo, row, 3)
        row += 1

        inv_group = QtWidgets.QGroupBox("Inventario")
        inv_layout = QtWidgets.QGridLayout(inv_group)
        inv_layout.addWidget(self.inv_checkbox, 0, 0, 1, 2)
        inv_layout.addWidget(QtWidgets.QLabel("Hay"), 1, 0)
        inv_layout.addWidget(self.stock_spin, 1, 1)
        inv_layout.addWidget(QtWidgets.QLabel("Mín"), 2, 0)
        inv_layout.addWidget(self.min_spin, 2, 1)
        inv_layout.addWidget(QtWidgets.QLabel("Máx"), 3, 0)
        inv_layout.addWidget(self.max_spin, 3, 1)

        frame_layout.addLayout(form)
        frame_layout.addWidget(inv_group)
        layout.addWidget(frame)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch(1)
        self.save_btn = QtWidgets.QPushButton("Guardar")
        self.cancel_btn = QtWidgets.QPushButton("Cancelar")
        self.save_btn.clicked.connect(self._save)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _wire_shortcuts(self) -> None:
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+S"), self, activated=self._save)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self, activated=self.reject)

    # ------------------------------------------------------------------
    def _toggle_inventory_fields(self) -> None:
        enabled = self.inv_checkbox.isChecked()
        for w in (self.stock_spin, self.min_spin, self.max_spin):
            w.setEnabled(enabled)

    def _recalc_from_cost(self) -> None:
        if self._updating_fields:
            return
        self._updating_fields = True
        try:
            cost = float(self.cost_spin.value())
            margin = float(self.margin_spin.value())
            price = cost * (1 + margin / 100.0) if cost >= 0 else 0.0
            self.price_spin.setValue(price)
            self._recalc_margin_from_price()
        finally:
            self._updating_fields = False

    def _recalc_from_margin(self) -> None:
        if self._updating_fields:
            return
        self._updating_fields = True
        try:
            cost = float(self.cost_spin.value())
            margin = float(self.margin_spin.value())
            price = cost * (1 + margin / 100.0) if cost >= 0 else 0.0
            self.price_spin.setValue(price)
        finally:
            self._updating_fields = False

    def _recalc_margin_from_price(self) -> None:
        if self._updating_fields:
            return
        self._updating_fields = True
        try:
            cost = float(self.cost_spin.value())
            price = float(self.price_spin.value())
            if cost > 0:
                margin = ((price - cost) / cost) * 100.0
            else:
                margin = 0.0
            self.margin_spin.setValue(margin)
        finally:
            self._updating_fields = False

    def _load_product(self, product: dict[str, Any]) -> None:
        self.sku_edit.setText(str(product.get("sku", "")))
        self.name_edit.setText(product.get("name", ""))
        self.cost_spin.setValue(float(product.get("cost", 0.0) or 0.0))
        self.price_spin.setValue(float(product.get("price", 0.0) or 0.0))
        self.wholesale_spin.setValue(float(product.get("price_wholesale", 0.0) or 0.0))
        if product.get("allow_decimal"):
            self.type_combo.setCurrentIndex(1)
        elif product.get("is_kit"):
            self.type_combo.setCurrentIndex(2)
        else:
            self.type_combo.setCurrentIndex(0)
        stock_row = None
        try:
            stock_row = self.core.get_stock_info(int(product["id"]), STATE.branch_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("No stock info for product %s: %s", product.get("id"), exc)
        if stock_row:
            self.stock_spin.setValue(float(stock_row.get("stock", 0.0)))
            self.min_spin.setValue(float(stock_row.get("min_stock", 0.0)))
        self._recalc_margin_from_price()

    # ------------------------------------------------------------------
    def _save(self) -> None:
        sku = self.sku_edit.text().strip()
        name = self.name_edit.text().strip()
        if not sku or not name:
            QtWidgets.QMessageBox.warning(self, "Datos faltantes", "SKU y descripción son obligatorios")
            return

        type_data = self.type_combo.currentData() or {}
        allow_decimal = bool(type_data.get("allow_decimal"))
        is_kit = bool(type_data.get("is_kit"))
        unit = str(type_data.get("unit") or "Unidad")

        data = {
            "sku": sku,
            "barcode": sku,
            "name": name,
            "description": name,
            "price": float(self.price_spin.value()),
            "price_wholesale": float(self.wholesale_spin.value()),
            "cost": float(self.cost_spin.value()),
            "unit": unit,
            "allow_decimal": allow_decimal,
            "is_kit": is_kit,
        }

        try:
            if self.product_id:
                if hasattr(self.core, "update_product"):
                    self.core.update_product(self.product_id, data)
                else:
                    self.core.upsert_product(**data)
            else:
                if hasattr(self.core, "create_product"):
                    self.product_id = self.core.create_product(data)
                else:
                    self.product_id = self.core.upsert_product(**data)
        except Exception as exc:  # pragma: no cover - UI feedback
            logger.exception("No se pudo guardar el producto")
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo guardar el producto: {exc}")
            return

        if self.inv_checkbox.isChecked() and self.product_id:
            desired = float(self.stock_spin.value())
            current_stock = 0.0
            stock_row = self.core.get_stock_info(self.product_id, STATE.branch_id)
            if stock_row:
                current_stock = float(stock_row.get("stock", 0.0))
            delta = desired - current_stock
            if abs(delta) > 1e-9:
                try:
                    self.core.add_stock(
                        self.product_id,
                        delta,
                        branch_id=STATE.branch_id,
                        reason="ajuste desde editor de producto",
                    )
                except Exception as exc:  # pragma: no cover
                    logger.exception("No se pudo ajustar inventario")
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Inventario",
                        f"Producto guardado, pero el ajuste de inventario falló: {exc}",
                    )
        self.accept()


__all__ = ["ProductEditorDialog"]
