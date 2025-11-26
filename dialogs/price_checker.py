"""Price checker dialog with KDE-inspired styling."""
from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from utils.animations import fade_in

from pos_core import POSCore, STATE


class ResultsDialog(QtWidgets.QDialog):
    def __init__(self, results: list[dict[str, Any]], parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Resultados de búsqueda")
        self.setModal(True)
        self.resize(600, 400)
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["SKU", "Nombre", "Precio", "Existencias"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.table)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._populate(results)

    def _populate(self, results: list[dict[str, Any]]) -> None:
        self.table.setRowCount(len(results))
        for row_idx, product in enumerate(results):
            values = [
                product.get("sku", ""),
                product.get("name", ""),
                f"{float(product.get('price', 0.0)):.2f}",
                str(int(product.get("stock", 0) or 0)),
            ]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_idx, col, cell)
        if results:
            self.table.selectRow(0)

    def selected_index(self) -> int:
        row = self.table.currentRow()
        return max(row, 0)


class PriceCheckerDialog(QtWidgets.QDialog):
    def __init__(
        self,
        core: POSCore,
        *,
        branch_id: Optional[int] = None,
        on_add: Optional[Callable[[dict[str, Any]], None]] = None,
        parent: QtWidgets.QWidget | None = None,
    ):
        super().__init__(parent)
        self.core = core
        self.branch_id = branch_id or STATE.branch_id
        self.on_add = on_add
        self.selected_product: Optional[dict[str, Any]] = None
        self.setWindowTitle("Verificador de Precios")
        self.resize(640, 420)
        self._build_ui()
        fade_in(self)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f7f8fb;
            }
            QFrame#Card {
                background: white;
                border: 1px solid #dce1e7;
                border-radius: 10px;
                padding: 12px;
            }
            QLabel#Title {
                font-size: 20px;
                font-weight: 600;
                color: #1b2631;
            }
            QPushButton#Primary {
                background: #2e86de;
                color: white;
                border-radius: 6px;
                padding: 8px 14px;
            }
            QPushButton#Primary:hover { background: #1f6fc4; }
            QPushButton#Secondary {
                background: #ecf0f1;
                color: #2c3e50;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton#Secondary:hover { background: #dfe6e9; }
            QLabel#ProductName { font-size: 18px; font-weight: 600; }
            QLabel#PriceMajor { font-size: 16px; font-weight: 600; }
            QLabel#PriceMinor { color: #27ae60; font-weight: 600; }
            QLabel#StockLabel { color: #7f8c8d; }
            QLineEdit#SearchField {
                font-size: 16px;
                padding: 8px;
                border: 1px solid #d0d7de;
                border-radius: 6px;
            }
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        layout.addWidget(card)
        card_layout = QtWidgets.QVBoxLayout(card)

        title = QtWidgets.QLabel("VERIFICADOR DE PRECIOS")
        title.setObjectName("Title")
        card_layout.addWidget(title, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        search_layout = QtWidgets.QHBoxLayout()
        self.search_line = QtWidgets.QLineEdit()
        self.search_line.setObjectName("SearchField")
        self.search_line.setPlaceholderText("Escanea código o escribe parte del nombre")
        self.search_line.returnPressed.connect(self.do_search)
        self.search_line.setFocus()
        search_btn = QtWidgets.QPushButton("Buscar")
        search_btn.setObjectName("Primary")
        search_btn.clicked.connect(self.do_search)
        clear_btn = QtWidgets.QPushButton("Limpiar")
        clear_btn.setObjectName("Secondary")
        clear_btn.clicked.connect(self.clear_result)
        search_layout.addWidget(self.search_line, 3)
        search_layout.addWidget(search_btn)
        search_layout.addWidget(clear_btn)
        card_layout.addLayout(search_layout)

        self.result_panel = QtWidgets.QFrame()
        self.result_panel.setObjectName("Card")
        self.result_panel.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        result_layout = QtWidgets.QVBoxLayout(self.result_panel)
        self.name_lbl = QtWidgets.QLabel("Esperando búsqueda...")
        self.name_lbl.setObjectName("ProductName")
        self.sku_lbl = QtWidgets.QLabel("")
        self.price_lbl = QtWidgets.QLabel("")
        self.price_lbl.setObjectName("PriceMajor")
        self.wholesale_lbl = QtWidgets.QLabel("")
        self.wholesale_lbl.setObjectName("PriceMinor")
        self.stock_lbl = QtWidgets.QLabel("")
        self.stock_lbl.setObjectName("StockLabel")
        self.sale_type_lbl = QtWidgets.QLabel("")
        for widget in [self.name_lbl, self.sku_lbl, self.sale_type_lbl, self.price_lbl, self.wholesale_lbl, self.stock_lbl]:
            result_layout.addWidget(widget)
        card_layout.addWidget(self.result_panel)

        btn_layout = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton("F1 – Agregar a venta")
        self.add_btn.setObjectName("Primary")
        self.add_btn.clicked.connect(self.accept_with_result)
        close_btn = QtWidgets.QPushButton("ESC – Cerrar")
        close_btn.setObjectName("Secondary")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(close_btn)
        card_layout.addLayout(btn_layout)

        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self, self.reject)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F1), self, self.accept_with_result)

    def clear_result(self) -> None:
        self.selected_product = None
        self.name_lbl.setText("Esperando búsqueda...")
        self.sku_lbl.clear()
        self.price_lbl.clear()
        self.wholesale_lbl.clear()
        self.stock_lbl.clear()

    def _pick_from_results(self, results: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        dlg = ResultsDialog(results, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            idx = dlg.selected_index()
            return results[idx]
        return None

    def _display_product(self, product: Optional[dict[str, Any]]) -> None:
        if not product:
            self.clear_result()
            self.name_lbl.setText("Producto no encontrado")
            return
        self.selected_product = {
            "product_id": product.get("id"),
            "sku": product.get("sku"),
            "name": product.get("name"),
            "price": float(product.get("price", 0.0)),
            "price_wholesale": product.get("price_wholesale"),
            "stock": int(product.get("stock", 0) or 0),
            "sale_type": (product.get("sale_type") or "unit").lower(),
        }
        self.name_lbl.setText(str(product.get("name", "")))
        self.sku_lbl.setText(f"SKU/EAN: {product.get('sku', '')}")
        sale_type = (product.get("sale_type") or "unit").lower()
        if sale_type == "kit":
            self.sale_type_lbl.setText("Tipo: Kit")
            try:
                components = self.core.get_kit_items(product.get("id"))  # type: ignore[attr-defined]
                comp_text = ", ".join([f"{c.get('qty',1)}x{c.get('product_id')}" for c in components])
                if comp_text:
                    self.stock_lbl.setText(self.stock_lbl.text() + f" | Kit: {comp_text}")
            except Exception:
                pass
        elif sale_type == "weight":
            self.sale_type_lbl.setText("Tipo: Granel (precio por peso)")
        else:
            self.sale_type_lbl.setText("Tipo: Unidad")
        self.price_lbl.setText(f"Precio normal: ${float(product.get('price', 0.0)):.2f}")
        price_wholesale = float(product.get("price_wholesale", 0.0) or 0.0)
        if price_wholesale > 0:
            self.wholesale_lbl.setText(f"Precio mayoreo: ${price_wholesale:.2f}")
            self.wholesale_lbl.show()
        else:
            self.wholesale_lbl.hide()
        self.stock_lbl.setText(f"Existencias: {int(product.get('stock', 0) or 0)}")

    def do_search(self) -> None:
        text = self.search_line.text().strip()
        if not text:
            QtWidgets.QMessageBox.information(self, "Buscar", "Escribe un SKU o nombre para buscar")
            return
        looks_code = text.isdigit() or len(text) <= 6
        product_row = None
        if looks_code:
            product_row = self.core.get_product_by_sku_or_barcode(text)
        results: list[dict[str, Any]] = []
        if product_row:
            stock_row = self.core.get_stock_info(product_row["id"], self.branch_id)
            merged = dict(product_row)
            if stock_row:
                merged["stock"] = stock_row.get("stock", 0)
            results = [merged]
        else:
            results = [dict(r) for r in self.core.search_products(text, limit=20, branch_id=self.branch_id)]
            if len(results) > 1:
                picked = self._pick_from_results(results)
                results = [picked] if picked else []
        self._display_product(results[0] if results else None)

    def accept_with_result(self) -> None:
        if not self.selected_product:
            QtWidgets.QMessageBox.warning(self, "Sin producto", "Busca y selecciona un producto primero")
            return
        if self.on_add:
            try:
                self.on_add(self.selected_product)
            except Exception:  # pragma: no cover - UI feedback
                pass
        self.accept()


__all__ = ["PriceCheckerDialog"]
