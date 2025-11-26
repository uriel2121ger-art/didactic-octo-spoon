"""Product search dialog (PASO 1) with KDE-inspired styling."""
from __future__ import annotations

from typing import Any, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from pos_core import POSCore, STATE
from utils.animations import fade_in


class ProductSearchDialog(QtWidgets.QDialog):
    """Advanced product search dialog.

    Supports partial searches, exact lookups with ``@`` prefix, and SKU/EAN searches.
    Double click or ENTER accepts the product and closes the dialog, exposing
    ``selected_product`` with the product payload.
    """

    def __init__(self, core: POSCore, *, branch_id: Optional[int] = None, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self.branch_id = branch_id or STATE.branch_id
        self.selected_product: Optional[dict[str, Any]] = None
        self._rows: list[dict[str, Any]] = []
        self.setWindowTitle("Buscador de productos")
        self.resize(900, 540)
        self._build_ui()
        fade_in(self)
        self.search_line.setFocus()

    # ------------------------------------------------------------------
    # UI
    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #f7f8fb; }
            QFrame#Card {
                background: white;
                border: 1px solid #dce1e7;
                border-radius: 10px;
                padding: 12px;
            }
            QLabel#Title { font-size: 20px; font-weight: 600; color: #1b2631; }
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
            QLineEdit#SearchField {
                font-size: 15px;
                padding: 8px;
                border: 1px solid #d0d7de;
                border-radius: 6px;
            }
            QTableWidget {
                background: white;
                alternate-background-color: #f5f7fa;
                gridline-color: #e5e7eb;
                selection-background-color: #d6e9ff;
                border-radius: 6px;
            }
            QHeaderView::section {
                background: #eef2f7;
                padding: 6px;
                border: none;
            }
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        layout.addWidget(card)
        vbox = QtWidgets.QVBoxLayout(card)

        title = QtWidgets.QLabel("BUSCAR PRODUCTO")
        title.setObjectName("Title")
        vbox.addWidget(title, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        search_row = QtWidgets.QHBoxLayout()
        self.search_line = QtWidgets.QLineEdit()
        self.search_line.setObjectName("SearchField")
        self.search_line.setPlaceholderText("F10 – Buscar | @exacto | SKU/EAN")
        self.search_line.returnPressed.connect(self.do_search)
        search_btn = QtWidgets.QPushButton("Buscar")
        search_btn.setObjectName("Primary")
        search_btn.clicked.connect(self.do_search)
        clear_btn = QtWidgets.QPushButton("Limpiar")
        clear_btn.setObjectName("Secondary")
        clear_btn.clicked.connect(self.clear_results)
        search_row.addWidget(self.search_line, 3)
        search_row.addWidget(search_btn)
        search_row.addWidget(clear_btn)
        vbox.addLayout(search_row)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Código", "Descripción", "Precio", "Mayoreo", "Departamento", "Inventario", "Fav"]
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.itemDoubleClicked.connect(self.accept_selected)
        vbox.addWidget(self.table)

        btn_row = QtWidgets.QHBoxLayout()
        self.modify_btn = QtWidgets.QPushButton("Modificar")
        self.modify_btn.setObjectName("Secondary")
        self.modify_btn.clicked.connect(self._on_modify)
        self.delete_btn = QtWidgets.QPushButton("Eliminar")
        self.delete_btn.setObjectName("Secondary")
        self.delete_btn.clicked.connect(self._on_delete)
        self.favorite_btn = QtWidgets.QPushButton("★ Favorito")
        self.favorite_btn.setObjectName("Secondary")
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        btn_row.addWidget(self.modify_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(self.favorite_btn)
        btn_row.addStretch(1)

        self.accept_btn = QtWidgets.QPushButton("Aceptar")
        self.accept_btn.setObjectName("Primary")
        self.accept_btn.clicked.connect(self.accept_selected)
        cancel_btn = QtWidgets.QPushButton("Cancelar")
        cancel_btn.setObjectName("Secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.accept_btn)
        btn_row.addWidget(cancel_btn)
        vbox.addLayout(btn_row)

        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self, self.reject)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Return), self, self.accept_selected)

    # ------------------------------------------------------------------
    def clear_results(self) -> None:
        self._rows = []
        self.table.setRowCount(0)
        self.selected_product = None

    def _current_row(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0 and self._rows:
            return 0
        if 0 <= row < len(self._rows):
            return row
        return None

    def accept_selected(self) -> None:
        idx = self._current_row()
        if idx is None:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Selecciona un producto")
            return
        self.selected_product = self._rows[idx]
        self.accept()

    # ------------------------------------------------------------------
    def do_search(self) -> None:
        term = self.search_line.text().strip()
        if not term:
            QtWidgets.QMessageBox.information(self, "Buscar", "Escribe un término para buscar")
            return

        results: list[dict[str, Any]] = []
        try:
            if term.startswith("@"):
                exact = term[1:].strip()
                if not exact:
                    QtWidgets.QMessageBox.information(self, "Buscar", "Ingresa texto después de @ para búsqueda exacta")
                    return
                matches = [dict(r) for r in self.core.search_products(exact, limit=50, branch_id=self.branch_id)]
                results = [r for r in matches if (r.get("name") or "").lower() == exact.lower() or r.get("sku") == exact]
            elif term.isdigit() or len(term) <= 6:
                row = self.core.get_product_by_sku_or_barcode(term)
                if row:
                    stock_row = self.core.get_stock_info(row["id"], self.branch_id)
                    merged = dict(row)
                    if stock_row:
                        merged["stock"] = stock_row.get("stock", 0)
                    results = [merged]
            else:
                results = [dict(r) for r in self.core.search_products(term, limit=50, branch_id=self.branch_id)]
        except Exception as exc:  # pragma: no cover - UI feedback
            QtWidgets.QMessageBox.critical(self, "Error", f"Error al buscar: {exc}")
            return

        if not results:
            QtWidgets.QMessageBox.information(self, "Sin resultados", "No se encontraron productos")
        self._populate(results)

    def _populate(self, rows: list[dict[str, Any]]) -> None:
        self.table.setUpdatesEnabled(False)
        self._rows = rows
        self.table.setRowCount(len(rows))
        for r_index, row in enumerate(rows):
            sale_type = (row.get("sale_type") or "unit").lower()
            badge = "[Kit] " if sale_type == "kit" else ("[Granel] " if sale_type == "weight" else "")
            values = [
                row.get("sku") or row.get("barcode") or "",
                f"{badge}{row.get('name', '')}",
                f"${float(row.get('price', 0.0)):.2f}",
                f"${float(row.get('price_wholesale', 0.0)):.2f}",
                row.get("category") or row.get("department") or "",
                str(int(row.get("stock", 0) or 0)),
                "★" if row.get("is_favorite") else "",
            ]
            for c_index, val in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if c_index == 6 and val:
                    item.setForeground(QtGui.QColor("#f1c40f"))
                self.table.setItem(r_index, c_index, item)
        if rows:
            self.table.selectRow(0)
        self.table.setUpdatesEnabled(True)

    # ------------------------------------------------------------------
    def toggle_favorite(self) -> None:
        idx = self._current_row()
        if idx is None:
            QtWidgets.QMessageBox.information(self, "Favorito", "Selecciona un producto primero")
            return
        product = self._rows[idx]
        if hasattr(self.core, "toggle_product_favorite"):
            try:
                new_state = self.core.toggle_product_favorite(product["id"])
                product["is_favorite"] = new_state
                self._populate(self._rows)
            except Exception as exc:  # pragma: no cover - UI feedback
                QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo actualizar favorito: {exc}")
        else:
            QtWidgets.QMessageBox.information(
                self,
                "Favorito",
                "La función de favoritos aún no está disponible en el núcleo.",
            )

    def _on_modify(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "Modificar",
            "El editor de productos se abrirá en el siguiente paso.",
        )

    def _on_delete(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "Eliminar",
            "La confirmación de eliminación se implementará en el siguiente paso.",
        )


__all__ = ["ProductSearchDialog"]
