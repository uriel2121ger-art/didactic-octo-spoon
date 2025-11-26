from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from pos_core import POSCore, STATE
from utils.animations import fade_in

logger = logging.getLogger(__name__)


class ProductDeleteDialog(QtWidgets.QDialog):
    """KDE-styled dialog to delete or deactivate a product safely."""

    def __init__(
        self,
        core: POSCore,
        product_id: Optional[int] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.core = core
        self.product_id = product_id
        self.product: Optional[dict[str, Any]] = None
        self.setModal(True)
        self.setWindowTitle("Eliminar producto")
        self.resize(520, 420)
        self._build_ui()
        self._wire_shortcuts()
        fade_in(self)
        if product_id:
            self._load_product_by_id(product_id)

    # ------------------------------------------------------------------
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
            QLabel#Title { font-size: 18px; font-weight: 600; color: #1b2631; }
            QPushButton#Danger {
                background: #e74c3c;
                color: white;
                border-radius: 6px;
                padding: 8px 14px;
            }
            QPushButton#Danger:hover { background: #c0392b; }
            QPushButton#Secondary {
                background: #ecf0f1;
                color: #2c3e50;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QLineEdit#SearchField {
                font-size: 14px;
                padding: 8px;
                border: 1px solid #d0d7de;
                border-radius: 6px;
            }
            QFrame#Warning {
                background: #fff4e5;
                border: 1px solid #f4d03f;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel#WarnText { color: #c27c0e; font-weight: 600; }
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        layout.addWidget(card)
        vbox = QtWidgets.QVBoxLayout(card)

        title = QtWidgets.QLabel("ELIMINAR PRODUCTO")
        title.setObjectName("Title")
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        vbox.addWidget(title)

        search_row = QtWidgets.QHBoxLayout()
        self.code_edit = QtWidgets.QLineEdit()
        self.code_edit.setObjectName("SearchField")
        self.code_edit.setPlaceholderText("SKU / Código de barras")
        self.code_edit.returnPressed.connect(self._lookup)
        search_btn = QtWidgets.QPushButton("Buscar")
        search_btn.setObjectName("Secondary")
        search_btn.clicked.connect(self._lookup)
        search_row.addWidget(self.code_edit, 3)
        search_row.addWidget(search_btn)
        vbox.addLayout(search_row)

        self.summary_labels: dict[str, QtWidgets.QLabel] = {}
        grid = QtWidgets.QGridLayout()
        labels = [
            ("Código", "sku"),
            ("Descripción", "name"),
            ("Tipo", "unit"),
            ("Precio", "price"),
            ("Mayoreo", "price_wholesale"),
            ("Departamento", "department"),
            ("Proveedor", "provider"),
            ("Inventario", "stock"),
        ]
        for row, (title_text, key) in enumerate(labels):
            grid.addWidget(QtWidgets.QLabel(f"{title_text}:"), row, 0)
            lbl = QtWidgets.QLabel("-")
            grid.addWidget(lbl, row, 1)
            self.summary_labels[key] = lbl
        vbox.addLayout(grid)

        warn = QtWidgets.QFrame()
        warn.setObjectName("Warning")
        warn_layout = QtWidgets.QVBoxLayout(warn)
        warn_lbl = QtWidgets.QLabel("Esta acción no se puede revertir.")
        warn_lbl.setObjectName("WarnText")
        warn_sub = QtWidgets.QLabel(
            "Si el producto tiene ventas históricas se desactivará en lugar de borrar."
        )
        warn_layout.addWidget(warn_lbl)
        warn_layout.addWidget(warn_sub)
        vbox.addWidget(warn)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self.delete_btn = QtWidgets.QPushButton("Eliminar DEFINITIVAMENTE")
        self.delete_btn.setObjectName("Danger")
        self.delete_btn.clicked.connect(self._confirm_delete)
        cancel_btn = QtWidgets.QPushButton("Cancelar")
        cancel_btn.setObjectName("Secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(cancel_btn)
        vbox.addLayout(btn_row)

    def _wire_shortcuts(self) -> None:
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self, self.reject)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Return), self, self._confirm_delete)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Enter), self, self._confirm_delete)

    # ------------------------------------------------------------------
    def _lookup(self) -> None:
        code = self.code_edit.text().strip()
        if not code:
            QtWidgets.QMessageBox.information(self, "Buscar", "Ingresa un código para buscar")
            return
        try:
            row = self.core.get_product_by_sku_or_barcode(code)
        except Exception as exc:  # pragma: no cover - UI feedback
            logger.exception("Error buscando producto")
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo buscar: {exc}")
            return
        if not row:
            QtWidgets.QMessageBox.information(self, "Sin resultado", "No se encontró el producto")
            return
        self._set_product(dict(row))

    def _load_product_by_id(self, product_id: int) -> None:
        try:
            row = self.core.get_product_by_id(product_id)
        except Exception as exc:  # pragma: no cover - UI feedback
            logger.exception("Error cargando producto")
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo cargar: {exc}")
            return
        if row:
            self._set_product(dict(row))

    def _set_product(self, product: dict[str, Any]) -> None:
        self.product = product
        self.product_id = int(product.get("id")) if product.get("id") else None
        self.code_edit.setText(product.get("sku") or product.get("barcode") or "")
        branch = STATE.branch_id
        stock = None
        try:
            stock_row = self.core.get_stock_info(self.product_id, branch)
            stock = stock_row.get("stock") if stock_row else None
        except Exception:
            stock = product.get("stock")
        mapping = {
            "sku": product.get("sku") or product.get("barcode") or "-",
            "name": product.get("name", "-"),
            "unit": product.get("unit", "Unidad"),
            "price": f"${float(product.get('price', 0.0) or 0.0):.2f}",
            "price_wholesale": f"${float(product.get('price_wholesale', 0.0) or 0.0):.2f}",
            "department": product.get("department") or product.get("category") or "-",
            "provider": product.get("provider") or "-",
            "stock": str(int(stock or 0)),
        }
        for key, lbl in self.summary_labels.items():
            lbl.setText(mapping.get(key, "-"))

    # ------------------------------------------------------------------
    def _confirm_delete(self) -> None:
        if not self.product_id:
            QtWidgets.QMessageBox.warning(
                self, "Selecciona", "Busca y selecciona un producto antes de eliminar"
            )
            return
        first = QtWidgets.QMessageBox.question(
            self,
            "Confirmar",
            "¿Seguro que deseas eliminar este producto?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if first != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        second = QtWidgets.QMessageBox.question(
            self,
            "Confirmar nuevamente",
            "Esta acción no se puede revertir. ¿Eliminar definitivamente?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if second != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._execute_delete()

    def _execute_delete(self) -> None:
        assert self.product_id
        try:
            has_sales = self._has_sales_history(self.product_id)
            if has_sales:
                if hasattr(self.core, "deactivate_product"):
                    self.core.deactivate_product(self.product_id)
                elif not self._soft_deactivate():
                    QtWidgets.QMessageBox.warning(
                        self,
                        "No eliminado",
                        "El producto tiene ventas y no se pudo desactivar con seguridad.",
                    )
                    return
            else:
                if hasattr(self.core, "delete_product"):
                    self.core.delete_product(self.product_id)
                else:
                    self._hard_delete_fallback()
            QtWidgets.QMessageBox.information(self, "Listo", "Producto eliminado/desactivado")
            self.accept()
        except Exception as exc:  # pragma: no cover - UI feedback
            logger.exception("Error al eliminar producto")
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo eliminar: {exc}")

    def _has_sales_history(self, product_id: int) -> bool:
        try:
            with self.core.connect() as conn:  # type: ignore[attr-defined]
                cur = conn.execute("SELECT 1 FROM sale_items WHERE product_id = ? LIMIT 1", (product_id,))
                return cur.fetchone() is not None
        except Exception:
            return False

    def _soft_deactivate(self) -> bool:
        try:
            with self.core.connect() as conn:  # type: ignore[attr-defined]
                cols = [row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()]
                if "is_active" in cols:
                    conn.execute(
                        "UPDATE products SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (self.product_id,),
                    )
                    return True
        except Exception:
            logger.exception("No se pudo desactivar el producto")
        return False

    def _hard_delete_fallback(self) -> None:
        with self.core.connect() as conn:  # type: ignore[attr-defined]
            conn.execute("DELETE FROM products WHERE id = ?", (self.product_id,))


__all__ = ["ProductDeleteDialog"]
