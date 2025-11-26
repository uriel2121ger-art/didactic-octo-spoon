#!/usr/bin/env python3
"""PySide6 application shell for POS Novedades Lupita Ultra Pro Max 2025.

This module wires the Qt UI with :mod:`pos_core`, providing base
implementations for every main tab. Each tab is intentionally simple but
functional, ready to be extended with advanced dialogs and workflows.
"""
from __future__ import annotations

import csv
import json
import secrets
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, List

from PySide6 import QtCharts, QtCore, QtGui, QtWidgets

import initialize_pos_env
from pos_core import APP_NAME, DATA_DIR, POSCore, STATE
from utils.export_csv import export_inventory_to_csv, export_product_catalog_to_csv
from utils.export_excel import export_inventory_to_excel, export_product_catalog_to_excel
from dialogs.discount_dialog import DiscountDialog
from dialogs.payment_dialog import PaymentDialog
from dialogs.product_common import ProductCommonDialog
from dialogs.product_search import ProductSearchDialog
from dialogs.product_editor import ProductEditorDialog
from dialogs.product_delete import ProductDeleteDialog
from dialogs.assign_customer import AssignCustomerDialog
from dialogs.customer_pro import CustomerProDialog
from dialogs.credit_statement_dialog import CreditStatementDialog
from dialogs.price_checker import PriceCheckerDialog
from dialogs.credit_overview import CreditOverviewDialog
from dialogs.credit_payment_dialog import CreditPaymentDialog
from dialogs.layaway_create_dialog import LayawayCreateDialog
from dialogs.layaway_payment_dialog import LayawayPaymentDialog
from dialogs.layaway_detail_dialog import LayawayDetailDialog
from dialogs.cash_movement_dialog import CashMovementDialog
from dialogs.turn_open_dialog import TurnOpenDialog
from dialogs.turn_partial_dialog import TurnPartialDialog
from dialogs.turn_close_dialog import TurnCloseDialog
from dialogs.report_export_dialog import ReportExportDialog
from dialogs.backup_restore_dialog import BackupRestoreDialog
from utils.customer_exporter import export_customers_to_csv, export_customers_to_excel
from dialogs.backup_settings_test_dialog import BackupSettingsTestDialog
from utils import charts_helper, permissions, ticket_engine
from utils import pdf_helper
from utils.network_client import MultiCajaClient, NetworkClient
from utils.websocket_client import WebsocketClient
from utils.theme_manager import ThemeManager, theme_manager
from utils.animations import fade_in
from utils.scanner_camera import CameraScannerThread
from utils.backup_engine import BackupEngine

OFFLINE_QUEUE_FILE = DATA_DIR / "offline_sales_queue.json"
OFFLINE_INVENTORY_QUEUE_FILE = DATA_DIR / "offline_inventory_queue.json"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_DIR = ASSETS_DIR / "icons"
logger = logging.getLogger(__name__)


def export_products_to_csv(products: list[dict[str, Any]], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "SKU",
                "Descripción",
                "Tipo",
                "Precio",
                "Mayoreo",
                "Departamento",
                "Proveedor",
                "Inventario",
                "Min",
                "Max",
                "Favorito",
            ]
        )
        for p in products:
            writer.writerow(
                [
                    p.get("sku", ""),
                    p.get("name", ""),
                    p.get("sale_type", ""),
                    p.get("price", ""),
                    p.get("price_wholesale", ""),
                    p.get("category") or p.get("department") or "",
                    p.get("provider") or "",
                    p.get("stock", ""),
                    p.get("min_stock", ""),
                    p.get("max_stock", ""),
                    "★" if p.get("is_favorite") else "",
                ]
            )


def export_products_to_excel(products: list[dict[str, Any]], path: str) -> None:
    try:
        from openpyxl import Workbook
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("openpyxl no está disponible para exportar a Excel") from exc

    wb = Workbook()
    ws = wb.active
    ws.title = "Productos"
    headers = [
        "SKU",
        "Descripción",
        "Tipo",
        "Precio",
        "Mayoreo",
        "Departamento",
        "Proveedor",
        "Inventario",
        "Min",
        "Max",
        "Favorito",
    ]
    ws.append(headers)
    for p in products:
        ws.append(
            [
                p.get("sku", ""),
                p.get("name", ""),
                p.get("sale_type", ""),
                p.get("price", ""),
                p.get("price_wholesale", ""),
                p.get("category") or p.get("department") or "",
                p.get("provider") or "",
                p.get("stock", ""),
                p.get("min_stock", ""),
                p.get("max_stock", ""),
                "★" if p.get("is_favorite") else "",
            ]
        )
    wb.save(path)


# ---------------------------------------------------------------------------
# Base Tab Widgets
class SalesTab(QtWidgets.QWidget):
    def __init__(
        self,
        core: POSCore,
        parent: QtWidgets.QWidget | None = None,
        *,
        mode: str = "server",
        network_client: NetworkClient | None = None,
    ):
        super().__init__(parent)
        self.core = core
        self.mode = mode
        self.network_client = network_client
        self.cart: list[dict[str, Any]] = []
        self.totals: dict[str, float] = {"subtotal": 0.0, "tax": 0.0, "total": 0.0}
        self.tax_rate = self.core.get_tax_rate(STATE.branch_id)
        self.app_config = self.core.get_app_config()
        self.scanner_prefix = self.app_config.get("scanner_prefix", "")
        self.scanner_suffix = self.app_config.get("scanner_suffix", "")
        self.camera_enabled = bool(self.app_config.get("camera_scanner_enabled", False))
        self.camera_index = int(self.app_config.get("camera_scanner_index", 0))
        self.global_discount: dict[str, Any] | None = None
        self._last_total_before_global = 0.0
        self.current_customer_id: int | None = None
        self.current_customer_name: str | None = None
        self.offline_queue_file = OFFLINE_QUEUE_FILE
        self.camera_thread: CameraScannerThread | None = None
        self._build_ui()
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F12), self, self._handle_charge)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+P"), self, self.add_common_product)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+D"), self, self.apply_line_discount)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+D"), self, self.apply_global_discount)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F11), self, self.apply_mayoreo)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F9), self, self.open_price_checker)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F10), self, self._open_product_search)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F2), self, self.open_assign_customer)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Equal), self, self.clear_customer)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F7), self, self._cash_in)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F8), self, self._cash_out)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F6), self, self._create_layaway_from_cart)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        form_layout = QtWidgets.QHBoxLayout()
        self.sku_input = QtWidgets.QLineEdit()
        self.sku_input.setPlaceholderText("SKU/EAN")
        self.qty_input = QtWidgets.QSpinBox()
        self.qty_input.setRange(1, 100000)
        self.add_btn = QtWidgets.QPushButton("Agregar")
        self.add_btn.clicked.connect(self.add_item)
        self.camera_btn = QtWidgets.QPushButton("📷 Escanear")
        self.camera_btn.clicked.connect(self._scan_with_camera)

        form_layout.addWidget(QtWidgets.QLabel("SKU/EAN"))
        form_layout.addWidget(self.sku_input, 2)
        form_layout.addWidget(QtWidgets.QLabel("Cantidad"))
        form_layout.addWidget(self.qty_input)
        form_layout.addWidget(self.add_btn)
        form_layout.addWidget(self.camera_btn)

        layout.addLayout(form_layout)
        self.sku_input.setFocus()
        self.sku_input.installEventFilter(self)
        self.sku_input.returnPressed.connect(self.add_item)

        self.offline_banner = QtWidgets.QLabel("Modo Offline Activo")
        self.offline_banner.setStyleSheet(
            "background: #f9d9a9; color: #8a4f00; padding: 6px; border-radius: 6px; font-weight: 700;"
        )
        self.offline_banner.setVisible(False)
        layout.addWidget(self.offline_banner)

        discounts_layout = QtWidgets.QHBoxLayout()
        self.line_discount_btn = QtWidgets.QPushButton("Desc. línea (Ctrl+D)")
        self.line_discount_btn.clicked.connect(self.apply_line_discount)
        self.global_discount_btn = QtWidgets.QPushButton("Desc. global (Ctrl+Shift+D)")
        self.global_discount_btn.clicked.connect(self.apply_global_discount)
        discounts_layout.addWidget(self.line_discount_btn)
        discounts_layout.addWidget(self.global_discount_btn)
        discounts_layout.addStretch(1)
        layout.addLayout(discounts_layout)

        customer_layout = QtWidgets.QHBoxLayout()
        self.customer_avatar = QtWidgets.QLabel("NC")
        self.customer_avatar.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.customer_avatar.setFixedSize(40, 40)
        self.customer_avatar.setStyleSheet(
            "border-radius: 20px; background: #dfe8ff; font-weight: 700; color: #1f3b87;"
        )
        self.customer_label = QtWidgets.QLabel("Sin cliente")
        self.customer_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.customer_btn = QtWidgets.QPushButton()
        self.customer_btn.clicked.connect(self._customer_button_clicked)
        self.clear_customer_btn = QtWidgets.QPushButton("Quitar (=)")
        self.clear_customer_btn.clicked.connect(self.clear_customer)
        customer_layout.addWidget(self.customer_avatar)
        customer_layout.addWidget(self.customer_label)
        customer_layout.addStretch(1)
        customer_layout.addWidget(self.customer_btn)
        customer_layout.addWidget(self.clear_customer_btn)
        layout.addLayout(customer_layout)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["SKU", "Nombre", "Precio", "Cant", "Subtotal"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        totals_layout = QtWidgets.QFormLayout()
        self.subtotal_lbl = QtWidgets.QLabel("0.00")
        self.global_discount_lbl = QtWidgets.QLabel("0.00")
        self.tax_lbl = QtWidgets.QLabel("0.00")
        self.total_lbl = QtWidgets.QLabel("0.00")
        totals_layout.addRow("Subtotal:", self.subtotal_lbl)
        totals_layout.addRow("Desc. global:", self.global_discount_lbl)
        totals_layout.addRow("IVA:", self.tax_lbl)
        totals_layout.addRow("Total:", self.total_lbl)
        layout.addLayout(totals_layout)

        actions_layout = QtWidgets.QHBoxLayout()
        self.layaway_btn = QtWidgets.QPushButton("Apartar")
        self.layaway_btn.clicked.connect(self._create_layaway_from_cart)
        self.charge_btn = QtWidgets.QPushButton("Cobrar (F12)")
        self.charge_btn.clicked.connect(self._handle_charge)
        actions_layout.addStretch(1)
        actions_layout.addWidget(self.layaway_btn)
        actions_layout.addWidget(self.charge_btn)
        layout.addLayout(actions_layout)
        self._update_customer_badge()

    # ------------------------------------------------------------------
    def add_item(self) -> None:
        identifier = self._normalize_scan(self.sku_input.text())
        qty = self.qty_input.value()
        if not identifier:
            QtWidgets.QMessageBox.warning(self, "Falta SKU", "Ingresa un SKU o código de barras")
            return

        product = self._fetch_product(identifier)
        if not product:
            QtWidgets.QMessageBox.warning(self, "No encontrado", "Producto no existe")
            return

        sale_type = (product.get("sale_type") or "unit").lower()
        if sale_type == "weight":
            qty, ok = QtWidgets.QInputDialog.getDouble(self, "Cantidad", "Cantidad a vender", value=qty or 1.0, min=0.001, decimals=3)
            if not ok:
                return
        kit_items = []
        if sale_type == "kit":
            kit_items = self.core.get_kit_items(product["id"]) if hasattr(self.core, "get_kit_items") else []
            for comp in kit_items:
                comp_stock = self.core.get_stock_info(comp.get("product_id"), STATE.branch_id) or {}
                if float(comp_stock.get("stock", 0.0) or 0.0) < qty * float(comp.get("qty", 1)):
                    QtWidgets.QMessageBox.warning(self, "Stock insuficiente", "Un componente del kit no tiene inventario")
                    return

        stock_row = self.core.get_stock_info(product["id"], STATE.branch_id)
        available = stock_row["stock"] if stock_row else 0
        if available < qty:
            QtWidgets.QMessageBox.warning(self, "Sin stock", "No hay suficiente inventario")
            return

        line = {
            "product_id": product["id"],
            "sku": product["sku"],
            "name": product["name"],
            "price": float(product["price"]),
            "base_price": float(product["price"]),
            "price_normal": float(product["price"]),
            "price_wholesale": float(product.get("price_wholesale", 0.0) or 0.0),
            "is_wholesale": False,
            "qty": qty,
            "price_includes_tax": False,
            "discount": 0.0,
            "sale_type": sale_type,
            "kit_items": kit_items,
        }
        self.cart.append(line)
        self._refresh_table()
        self.sku_input.clear()
        self.qty_input.setValue(1)

    def add_common_product(self) -> None:
        dialog = ProductCommonDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.result_data:
            result = dialog.result_data
            line = {
                "product_id": None,
                "sku": "COMMON",
                "name": result["name"],
                "price": float(result["price"]),
                "base_price": float(result["price"]),
                "price_normal": float(result["price"]),
                "price_wholesale": 0.0,
                "is_wholesale": False,
                "qty": float(result["qty"]),
                "price_includes_tax": bool(result.get("price_includes_tax", False)),
                "discount": 0.0,
            }
            self.cart.append(line)
            self._refresh_table()

    def open_price_checker(self, preset_query: str | None = None) -> None:
        dialog = PriceCheckerDialog(
            self.core, branch_id=STATE.branch_id, on_add=self.add_product_from_checker, parent=self
        )
        if preset_query:
            dialog.search_line.setText(preset_query)
            dialog.do_search()
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.selected_product:
            self.add_product_from_checker(dialog.selected_product)

    def _open_price_checker_from_field(self) -> None:
        preset = self._normalize_scan(self.sku_input.text())
        self.open_price_checker(preset if preset else None)

    def _open_product_search(self) -> None:
        dialog = ProductSearchDialog(core=self.core, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.selected_product:
            self.add_product_from_search(dialog.selected_product)

    def add_product_from_checker(self, product: dict[str, Any]) -> None:
        qty = self.qty_input.value()
        stock_available = int(product.get("stock", 0) or 0)
        if stock_available and stock_available < qty:
            QtWidgets.QMessageBox.warning(self, "Sin stock", "No hay suficiente inventario")
            return
        line = {
            "product_id": product.get("product_id") or product.get("id"),
            "sku": product.get("sku"),
            "name": product.get("name"),
            "price": float(product.get("price", 0.0)),
            "base_price": float(product.get("price", 0.0)),
            "price_normal": float(product.get("price", 0.0)),
            "price_wholesale": float(product.get("price_wholesale", 0.0) or 0.0),
            "is_wholesale": False,
            "qty": qty,
            "price_includes_tax": False,
            "discount": 0.0,
        }
        self.cart.append(line)
        self._refresh_table()

    def add_product_from_search(self, product: dict[str, Any]) -> None:
        sale_type = (product.get("sale_type") or product.get("unit_type") or "unit").lower()
        qty = float(self.qty_input.value())
        if sale_type in {"weight", "granel"}:
            qty, ok = QtWidgets.QInputDialog.getDouble(
                self,
                "Cantidad",
                "Cantidad a vender",
                value=qty or 1.0,
                min=0.001,
                decimals=3,
            )
            if not ok:
                return
        product_id = product.get("product_id") or product.get("id")
        stock_available = float(product.get("stock", 0.0) or 0.0)
        kit_items = []
        if sale_type == "kit":
            kit_items = self.core.get_kit_items(product_id)
            for comp in kit_items:
                comp_stock = self.core.get_stock_info(comp.get("product_id"), STATE.branch_id) or {}
                if float(comp_stock.get("stock", 0.0) or 0.0) < qty * float(comp.get("qty", 1)):
                    QtWidgets.QMessageBox.warning(self, "Sin stock", "Componente de kit sin inventario")
                    return
        if stock_available and stock_available < qty and sale_type != "kit":
            QtWidgets.QMessageBox.warning(self, "Sin stock", "No hay suficiente inventario")
            return
        line = {
            "product_id": product_id,
            "sku": product.get("sku"),
            "name": product.get("name"),
            "price": float(product.get("price", 0.0)),
            "base_price": float(product.get("price", 0.0)),
            "price_normal": float(product.get("price", 0.0)),
            "price_wholesale": float(product.get("price_wholesale", 0.0) or 0.0),
            "is_wholesale": False,
            "qty": qty,
            "price_includes_tax": False,
            "discount": 0.0,
            "sale_type": sale_type,
            "kit_items": kit_items,
        }
        self.cart.append(line)
        self._refresh_table()

    def _normalize_scan(self, text: str) -> str:
        value = (text or "").strip()
        if self.scanner_prefix and value.startswith(self.scanner_prefix):
            value = value[len(self.scanner_prefix) :]
        if self.scanner_suffix and value.endswith(self.scanner_suffix):
            value = value[: -len(self.scanner_suffix)]
        return value.strip()

    def _fetch_product(self, identifier: str) -> Any:
        if self.mode == "client" and self.network_client:
            try:
                data = self.network_client.fetch_product(identifier)
                if data:
                    return {
                        "id": data.get("id"),
                        "sku": data.get("sku"),
                        "barcode": data.get("barcode"),
                        "name": data.get("name"),
                        "price": data.get("price"),
                        "price_wholesale": data.get("price_wholesale", 0.0),
                    }
            except Exception:
                self._set_offline(True)
        return self.core.get_product_by_sku_or_barcode(identifier)

    def _customer_button_clicked(self) -> None:
        if self.current_customer_id:
            self.clear_customer()
        else:
            self.open_assign_customer()

    def _avatar_color(self, seed: str) -> str:
        h = hash(seed) & 0xFFFFFF
        r = (((h >> 16) & 0xFF) + 255) // 2
        g = (((h >> 8) & 0xFF) + 255) // 2
        b = ((h & 0xFF) + 255) // 2
        return f"rgb({r},{g},{b})"

    def _update_customer_badge(self) -> None:
        if self.current_customer_id and self.current_customer_name:
            initials = "".join([part[0] for part in self.current_customer_name.split() if part][:2]).upper()
            self.customer_avatar.setText(initials or "CL")
            color = self._avatar_color(self.current_customer_name)
            self.customer_avatar.setStyleSheet(
                f"border-radius: 20px; background: {color}; font-weight: 700; color: white;"
            )
            self.customer_label.setText(f"Cliente: {self.current_customer_name}")
            self.customer_btn.setText("Cambiar (F2)")
        else:
            self.customer_avatar.setText("NC")
            self.customer_avatar.setStyleSheet(
                "border-radius: 20px; background: #dfe8ff; font-weight: 700; color: #1f3b87;"
            )
            self.customer_label.setText("Sin cliente")
            self.customer_btn.setText("F2 – Asignar Cliente")

    def _set_offline(self, offline: bool) -> None:
        self.offline_banner.setVisible(offline)

    def _scan_with_camera(self) -> None:
        if not self.camera_enabled:
            QtWidgets.QMessageBox.information(self, "Escáner", "Habilita el lector por cámara en Configuración")
            return
        if self.camera_thread and self.camera_thread.isRunning():
            return
        try:
            self.camera_thread = CameraScannerThread(self.camera_index, self)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Cámara", f"No se pudo iniciar la cámara: {exc}")
            return
        self.camera_thread.code_detected.connect(self._on_camera_code)
        self.camera_thread.start()

    def _on_camera_code(self, code: str) -> None:
        normalized = self._normalize_scan(code)
        self.sku_input.setText(normalized)
        self.add_item()
        if self.camera_thread:
            self.camera_thread.stop()

    def open_assign_customer(self) -> None:
        dialog = AssignCustomerDialog(self.core, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.selected_customer_id:
            self.current_customer_id = dialog.selected_customer_id
            self.current_customer_name = dialog.selected_customer_name
            self._update_customer_badge()

    def clear_customer(self) -> None:
        self.current_customer_id = None
        self.current_customer_name = None
        self._update_customer_badge()

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.cart))
        subtotal = 0.0
        tax_total = 0.0
        total_before_global = 0.0
        discount_color = QtGui.QColor("#fff3cd")
        wholesale_color = QtGui.QColor("#d8f5d0")
        weight_color = QtGui.QColor("#d6eaf8")
        kit_color = QtGui.QColor("#f5e8ff")
        for row_idx, item in enumerate(self.cart):
            qty = float(item.get("qty", 1))
            base_price = float(item.get("base_price", item.get("price", 0)))
            includes_tax = bool(item.get("price_includes_tax", False))
            is_wholesale = bool(item.get("is_wholesale", False))
            line_discount = 0.0 if is_wholesale else float(item.get("discount", 0.0))
            line_base = base_price * qty
            if includes_tax:
                gross = max(line_base - line_discount, 0)
                base_without_tax = gross / (1 + self.tax_rate)
                line_tax = gross - base_without_tax
                line_total = gross
            else:
                base_without_tax = max(line_base - line_discount, 0)
                line_tax = base_without_tax * self.tax_rate
                line_total = base_without_tax + line_tax
            subtotal += base_without_tax
            tax_total += line_tax
            total_before_global += line_total
            effective_unit_price = max((line_base - line_discount), 0) / qty if qty else 0.0
            for col, value in enumerate([
                item.get("sku", ""),
                item.get("name", ""),
                f"{effective_unit_price:.2f}",
                f"{qty:.3g}",
                f"{line_total:.2f}",
            ]):
                cell = QtWidgets.QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_idx, col, cell)
            bg_color: QtGui.QColor | None = None
            if is_wholesale:
                bg_color = wholesale_color
            elif line_discount > 0:
                bg_color = discount_color
            sale_type = (item.get("sale_type") or "unit").lower()
            if sale_type == "weight":
                bg_color = weight_color
            elif sale_type == "kit":
                bg_color = kit_color
            for col_idx in range(self.table.columnCount()):
                cell = self.table.item(row_idx, col_idx)
                if cell:
                    cell.setBackground(bg_color or QtGui.QColor("white"))
        discount_amount = 0.0
        if self.global_discount:
            if self.global_discount["type"] == "percent":
                discount_amount = total_before_global * (float(self.global_discount["value"]) / 100.0)
            else:
                discount_amount = float(self.global_discount["value"])
            discount_amount = min(discount_amount, total_before_global)
        total = max(total_before_global - discount_amount, 0)
        self._last_total_before_global = total_before_global
        self.subtotal_lbl.setText(f"{subtotal:.2f}")
        self.global_discount_lbl.setText(f"-{discount_amount:.2f}")
        self.tax_lbl.setText(f"{tax_total:.2f}")
        self.total_lbl.setText(f"{total:.2f}")
        self.totals = {"subtotal": subtotal, "tax": tax_total, "total": total, "global_discount": discount_amount}

    def _handle_charge(self) -> None:
        if not self.cart:
            QtWidgets.QMessageBox.information(self, "Sin productos", "Agrega productos antes de cobrar")
            return
        credit_available = 0.0
        allow_credit = False
        if self.current_customer_id:
            info = self.core.get_customer_credit_info(self.current_customer_id)
            credit_limit = float(info.get("credit_limit", 0.0) or 0.0)
            credit_balance = float(info.get("credit_balance", 0.0) or 0.0)
            authorized = bool(info.get("credit_authorized") or credit_limit != 0)
            allow_credit = authorized
            if credit_limit < 0:
                credit_available = float("inf")
            else:
                credit_available = max(credit_limit - credit_balance, 0.0)
        cfg = self.core.get_app_config()
        payment_dialog = PaymentDialog(
            self.totals["total"],
            self,
            allow_credit=bool(self.current_customer_id and allow_credit),
            customer_name=self.current_customer_name or "",
            customer_id=self.current_customer_id,
            credit_available=credit_available,
            card_fee_percent=float(cfg.get("card_fee_percent", 0.0) or 0.0),
            default_exchange=float(cfg.get("usd_exchange_rate", 17.0) or 17.0),
        )
        cart_snapshot = [dict(item) for item in self.cart]
        if payment_dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and payment_dialog.result_data:
            method = payment_dialog.result_data.get("method")
            if method == "credit" and not self.current_customer_id:
                QtWidgets.QMessageBox.warning(self, "Crédito no disponible", "Asigna un cliente antes de vender a crédito")
                return
            payload = {
                "items": self.cart,
                "payment": payment_dialog.result_data,
                "branch_id": STATE.branch_id,
                "discount": self.totals.get("global_discount", 0.0),
                "customer_id": self.current_customer_id,
                "user_id": STATE.user_id,
            }
            try:
                if self.mode == "client" and self.network_client:
                    resp = self.network_client.post("/api/sales", payload)
                    sale_id = resp.get("sale_id") if isinstance(resp, dict) else None
                    if sale_id:
                        self._set_offline(False)
                    else:
                        raise RuntimeError("Respuesta inválida del servidor")
                else:
                    sale_id = self.core.create_sale(
                        self.cart,
                        payment_dialog.result_data,
                        branch_id=STATE.branch_id,
                        discount=self.totals.get("global_discount", 0.0),
                        customer_id=self.current_customer_id,
                    )
                if self.mode == "client" and self.network_client:
                    try:
                        self.network_client.post(
                            "/api/inventory/apply_sale",
                            {"items": cart_snapshot, "branch_id": STATE.branch_id},
                        )
                    except Exception:
                        if hasattr(self.network_client, "inventory_queue"):
                            self.network_client.inventory_queue.append(
                                {"items": cart_snapshot, "branch_id": STATE.branch_id}
                            )
            except Exception as exc:  # pragma: no cover - UI notification
                if self.mode == "client" and self.network_client:
                    self._enqueue_offline_sale(payload)
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Modo offline",
                        "Venta guardada en cola offline. Se enviará al reconectar.",
                    )
                    self._clear_after_sale()
                    return
                QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo registrar la venta: {exc}")
                return
            self._print_sale_ticket(sale_id, cart_snapshot, payment_dialog.result_data)
            self._clear_after_sale()
            extra = ""
            if method == "cash" and payment_dialog.result_data.get("change") is not None:
                extra = f" Cambio: ${float(payment_dialog.result_data.get('change', 0.0)):.2f}"
            QtWidgets.QMessageBox.information(
                self,
                "Venta registrada",
                f"Venta #{sale_id} cobrada con {method}.{extra}",
            )

    def _clear_after_sale(self) -> None:
        self.cart.clear()
        self.global_discount = None
        self.clear_customer()
        self._refresh_table()
        self.sku_input.clear()
        self.qty_input.setValue(1)
        self.sku_input.setFocus()

    def _print_sale_ticket(self, sale_id: Any, cart: list[dict[str, Any]], payment_data: dict[str, Any]) -> None:
        cfg = self.core.get_app_config()
        if not cfg.get("auto_print_tickets"):
            return
        printer_name = cfg.get("printer_name")
        lines = [
            APP_NAME,
            f"Venta #{sale_id if sale_id is not None else 'N/A'}",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            "--- Items ---",
        ]
        for item in cart:
            qty = float(item.get("qty", 0))
            price = float(item.get("price", 0))
            discount = float(item.get("discount", 0.0))
            subtotal = max((qty * price) - discount, 0.0)
            lines.append(f"{qty:g} x ${price:.2f} = ${subtotal:.2f}  {item.get('name','')}")
        lines.append(f"Subtotal: ${self.totals.get('subtotal', 0.0):.2f}")
        if self.totals.get("global_discount", 0.0):
            lines.append(f"Desc. global: -${self.totals['global_discount']:.2f}")
        lines.append(f"IVA: ${self.totals.get('tax', 0.0):.2f}")
        lines.append(f"TOTAL: ${self.totals.get('total', 0.0):.2f}")
        lines.extend(ticket_engine.render_payment_lines(payment_data))
        try:
            ticket_engine.print_ticket("\n".join(lines), printer_name)
        except Exception:  # noqa: BLE001
            logging.exception("No se pudo imprimir el ticket")

        if cfg.get("cash_drawer_enabled"):
            pulse_str = cfg.get("cash_drawer_pulse_bytes", "\\x1B\\x70\\x00\\x19\\xFA")
            try:
                pulse_bytes = bytes(pulse_str, "utf-8").decode("unicode_escape").encode("latin1")
                ticket_engine.open_cash_drawer(printer_name or "", pulse_bytes)
            except Exception:  # noqa: BLE001
                logging.exception("No se pudo abrir el cajón de dinero")

    def _enqueue_offline_sale(self, payload: dict[str, Any]) -> None:
        if hasattr(self.network_client, "sales_queue"):
            self.network_client.sales_queue.append(payload)
        else:
            queue: list[dict[str, Any]] = []
            if self.offline_queue_file.exists():
                try:
                    queue = json.loads(self.offline_queue_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    queue = []
            queue.append(payload)
            self.offline_queue_file.parent.mkdir(parents=True, exist_ok=True)
            self.offline_queue_file.write_text(json.dumps(queue, indent=2), encoding="utf-8")
        self._set_offline(True)

    def sync_offline_sales(self) -> None:
        if self.mode != "client" or not self.network_client:
            return
        if hasattr(self.network_client, "flush_queue_when_online"):
            try:
                self.network_client.flush_queue_when_online()
                self._set_offline(getattr(self.network_client, "offline_mode", False))
            except Exception:
                pass

    def _create_layaway_from_cart(self) -> None:
        if not self.cart:
            QtWidgets.QMessageBox.warning(self, "Sin productos", "Agrega productos antes de generar un apartado")
            return
        missing_products = [item for item in self.cart if not item.get("product_id")]
        if missing_products:
            QtWidgets.QMessageBox.warning(
                self,
                "Producto común no permitido",
                "No se pueden generar apartados con productos sin identificar (COMMON).",
            )
            return
        dialog = LayawayCreateDialog(self.cart, self.totals.get("total", 0.0), self)
        dialog.set_customer(self.current_customer_id, self.current_customer_name)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted or not dialog.result_data:
            return
        data = dialog.result_data
        deposit = float(data.get("deposit") or 0.0)
        total = float(self.totals.get("total", 0.0))
        if deposit > total:
            deposit = total
        try:
            layaway_id = self.core.create_layaway(
                self.cart,
                deposit=deposit,
                due_date=data.get("due_date"),
                customer_id=data.get("customer_id"),
                branch_id=STATE.branch_id,
                notes=data.get("notes"),
                user_id=STATE.user_id,
            )
        except Exception as exc:  # pragma: no cover - UI feedback
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo crear el apartado: {exc}")
            return
        self.cart.clear()
        self.global_discount = None
        self.clear_customer()
        self._refresh_table()
        try:
            layaway = self.core.get_layaway(layaway_id)
            items = self.core.get_layaway_items(layaway_id)
            ticket_engine.print_layaway_create(dict(layaway or {}), [dict(i) for i in items])
        except Exception:
            pass
        QtWidgets.QMessageBox.information(
            self,
            "Apartado creado",
            f"Apartado #{layaway_id} registrado correctamente. Depósito: ${deposit:,.2f}",
        )

    def _cash_in(self) -> None:
        dialog = CashMovementDialog("in", self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.result_data:
            try:
                self.core.register_cash_movement(
                    None,
                    "in",
                    dialog.result_data["amount"],
                    reason=dialog.result_data.get("reason"),
                    branch_id=STATE.branch_id,
                    user_id=STATE.user_id,
                )
                QtWidgets.QMessageBox.information(self, "Entrada registrada", "Movimiento guardado")
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.critical(self, "Error", str(exc))

    def _cash_out(self) -> None:
        dialog = CashMovementDialog("out", self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.result_data:
            try:
                self.core.register_cash_movement(
                    None,
                    "out",
                    dialog.result_data["amount"],
                    reason=dialog.result_data.get("reason"),
                    branch_id=STATE.branch_id,
                    user_id=STATE.user_id,
                )
                QtWidgets.QMessageBox.information(self, "Salida registrada", "Movimiento guardado")
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.critical(self, "Error", str(exc))

    def apply_mayoreo(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Selecciona una línea para alternar mayoreo")
            return
        item = self.cart[row]
        if not item.get("product_id"):
            QtWidgets.QMessageBox.warning(self, "No aplica", "El producto común no soporta precio de mayoreo")
            return
        sku = item.get("sku")
        product = self.core.get_product_by_sku_or_barcode(sku) if sku else None
        if not product:
            QtWidgets.QMessageBox.warning(self, "Producto no encontrado", "No se pudo cargar el producto seleccionado")
            return
        price_wholesale = float(product.get("price_wholesale", 0.0) or 0.0)
        if price_wholesale <= 0:
            QtWidgets.QMessageBox.information(
                self, "Sin mayoreo", "Este producto no tiene precio de mayoreo configurado."
            )
            return
        item.setdefault("price_normal", float(product.get("price", 0.0)))
        item["price_wholesale"] = price_wholesale
        if not item.get("is_wholesale"):
            item["is_wholesale"] = True
            item["price"] = price_wholesale
            item["base_price"] = price_wholesale
            item["discount"] = 0.0
        else:
            normal_price = float(item.get("price_normal", product.get("price", 0.0)))
            item["is_wholesale"] = False
            item["price"] = normal_price
            item["base_price"] = normal_price
            item["discount"] = 0.0
        self._refresh_table()

    def apply_line_discount(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Selecciona una línea para aplicar descuento")
            return
        item = self.cart[row]
        if item.get("is_wholesale"):
            QtWidgets.QMessageBox.warning(
                self,
                "Precio mayoreo activo",
                "Quita el precio de mayoreo (F11) antes de aplicar descuento en esta línea.",
            )
            return
        base_price = float(item.get("base_price", item.get("price", 0.0)))
        qty = float(item.get("qty", 1))
        if item.get("discount", 0.0) > 0:
            confirm = QtWidgets.QMessageBox.question(
                self,
                "Reemplazar descuento",
                "Este producto ya tiene un descuento aplicado. ¿Reemplazar descuento?",
            )
            if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        dialog = DiscountDialog(base_price, current_price=max(base_price - (item.get("discount", 0.0) / max(qty, 1)), 0), parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.result_data:
            result = dialog.result_data
            discount_amount_unit = float(result["discount_amount"])
            item["base_price"] = base_price
            item["price"] = base_price
            item["discount"] = max(discount_amount_unit * qty, 0.0)
            self._refresh_table()

    def apply_global_discount(self) -> None:
        if not self.cart:
            QtWidgets.QMessageBox.warning(self, "Sin productos", "Agrega productos antes de aplicar descuento")
            return
        if self.global_discount:
            confirm = QtWidgets.QMessageBox.question(
                self,
                "Reemplazar descuento",
                "Ya existe un descuento global aplicado. ¿Reemplazarlo?",
            )
            if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        base_total = self._last_total_before_global or self.totals.get("total", 0.0)
        dialog = DiscountDialog(base_total, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.result_data:
            result = dialog.result_data
            self.global_discount = {"type": result["type"], "value": float(result["value"])}
            self._refresh_table()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # noqa: N802
        if obj is self.sku_input and event.type() == QtCore.QEvent.Type.FocusIn:
            QtCore.QTimer.singleShot(0, self.sku_input.selectAll)
        return super().eventFilter(obj, event)

class ProductsTab(QtWidgets.QWidget):
    def __init__(self, core: POSCore, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self._build_ui()
        self.refresh_table()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        toolbar = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Buscar por nombre, SKU o proveedor (F10)")
        self.search_btn = QtWidgets.QPushButton("Buscar")
        self.search_btn.clicked.connect(self._open_search_dialog)
        self.new_btn = QtWidgets.QPushButton("Nuevo producto (F2)")
        self.edit_btn = QtWidgets.QPushButton("Modificar (F3)")
        self.del_btn = QtWidgets.QPushButton("Eliminar (Supr)")
        self.export_catalog_btn = QtWidgets.QPushButton("Exportar catálogo…")
        self.export_inventory_btn = QtWidgets.QPushButton("Exportar inventario…")
        for btn, handler in [
            (self.search_btn, self._open_search_dialog),
            (self.new_btn, self._new_product),
            (self.edit_btn, self._edit_selected),
            (self.del_btn, self._delete_selected),
        ]:
            btn.clicked.connect(handler)
        toolbar.addWidget(self.search_input, 2)
        toolbar.addWidget(self.search_btn)
        toolbar.addWidget(self.new_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.del_btn)
        toolbar.addWidget(self.export_catalog_btn)
        toolbar.addWidget(self.export_inventory_btn)
        layout.addLayout(toolbar)

        self.table = QtWidgets.QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Código",
                "Descripción",
                "Tipo",
                "Precio",
                "Mayoreo",
                "Departamento",
                "Proveedor",
                "Inventario",
                "Min",
                "Max",
                "★",
            ]
        )
        self.table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda *_: self._edit_selected())
        layout.addWidget(self.table)

        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F2), self, self._new_product)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F3), self, self._edit_selected)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Delete), self, self._delete_selected)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+E"), self, self._export_catalog)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F10), self, self._open_search_dialog)
        self.export_catalog_btn.clicked.connect(self._export_catalog)
        self.export_inventory_btn.clicked.connect(lambda: self._export_catalog(inventory_only=True))

    def _selected_product_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return int(self.table.item(row, 0).text())

    def _open_search_dialog(self) -> None:
        dialog = ProductSearchDialog(core=self.core, parent=self)
        dialog.search_input.setText(self.search_input.text())
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.selected_product:
            product = dialog.selected_product
            self._open_editor(product.get("id"))
        self.refresh_table()

    def _new_product(self) -> None:
        self._open_editor(None)

    def _edit_selected(self) -> None:
        product_id = self._selected_product_id()
        if not product_id:
            QtWidgets.QMessageBox.warning(self, "Productos", "Selecciona un producto")
            return
        self._open_editor(product_id)

    def _open_editor(self, product_id: int | None) -> None:
        dialog = ProductEditorDialog(core=self.core, product_id=product_id, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            QtWidgets.QMessageBox.information(self, "Productos", "Producto guardado correctamente")
            self.refresh_table()

    def _delete_selected(self) -> None:
        product_id = self._selected_product_id()
        if not product_id:
            QtWidgets.QMessageBox.warning(self, "Productos", "Selecciona un producto")
            return
        dialog = ProductDeleteDialog(core=self.core, product_id=product_id, parent=self)
        dialog.exec()
        self.refresh_table()

    def _export_catalog(self, inventory_only: bool = False) -> None:
        products = self.core.list_products_for_export()
        if inventory_only:
            products = [p for p in products if p.get("uses_inventory", True)]
        path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Exportar productos",
            "productos",
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not path:
            return
        try:
            if selected_filter.startswith("Excel") or path.lower().endswith(".xlsx"):
                if inventory_only:
                    export_inventory_to_excel(products, path)
                else:
                    export_product_catalog_to_excel(products, path)
            else:
                if inventory_only:
                    export_inventory_to_csv(products, path)
                else:
                    export_product_catalog_to_csv(products, path)
            QtWidgets.QMessageBox.information(self, "Exportar", "Exportación completada")
        except Exception as exc:  # noqa: BLE001
            logging.exception("export products failed")
            QtWidgets.QMessageBox.critical(self, "Exportar", f"No se pudo exportar: {exc}")

    def refresh_table(self) -> None:
        query = self.search_input.text().strip()
        products = self.core.get_products_for_search(query)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(products))
        for row_idx, product in enumerate(products):
            record = dict(product)
            values = [
                record.get("id"),
                record.get("sku"),
                record.get("name"),
                record.get("sale_type") or "unidad",
                f"{float(record.get('price', 0.0) or 0.0):.2f}",
                f"{float(record.get('price_wholesale', 0.0) or 0.0):.2f}",
                record.get("category") or record.get("department") or "",
                record.get("provider") or "",
                f"{float(record.get('stock', 0.0) or 0.0):.2f}",
                f"{float(record.get('min_stock', 0.0) or 0.0):.2f}",
                f"{float(record.get('max_stock', 0.0) or 0.0):.2f}",
                "★" if record.get("is_favorite") else "",
            ]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if col == 11:  # favorite column
                    cell.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, cell)
        self.table.setUpdatesEnabled(True)


class InventoryTab(QtWidgets.QWidget):
    def __init__(self, core: POSCore, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self._build_ui()
        self.refresh_table()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        form_layout = QtWidgets.QHBoxLayout()
        self.sku_input = QtWidgets.QLineEdit()
        self.sku_input.setPlaceholderText("SKU")
        self.search_btn = QtWidgets.QPushButton("Buscar…")
        self.search_btn.clicked.connect(self._pick_product)
        self.qty_input = QtWidgets.QDoubleSpinBox()
        self.qty_input.setDecimals(2)
        self.qty_input.setRange(-1_000_000, 1_000_000)
        self.reason_input = QtWidgets.QLineEdit()
        self.reason_input.setPlaceholderText("Razón")
        self.adjust_btn = QtWidgets.QPushButton("Aplicar ajuste")
        self.adjust_btn.clicked.connect(self.adjust_stock)

        form_layout.addWidget(QtWidgets.QLabel("SKU"))
        form_layout.addWidget(self.sku_input)
        form_layout.addWidget(self.search_btn)
        form_layout.addWidget(QtWidgets.QLabel("Cantidad"))
        form_layout.addWidget(self.qty_input)
        form_layout.addWidget(self.reason_input)
        form_layout.addWidget(self.adjust_btn)

        layout.addLayout(form_layout)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "SKU", "Nombre", "Tipo", "Stock", "Min", "Max"])
        self.table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda *_: self._edit_product_from_table())
        layout.addWidget(self.table)

        detail_layout = QtWidgets.QHBoxLayout()
        self.kit_list = QtWidgets.QListWidget()
        self.kit_list.setMinimumWidth(240)
        #self.kit_list.setPlaceholderText("Componentes del kit")
        self.movements_btn = QtWidgets.QPushButton("Ver movimientos")
        self.movements_btn.clicked.connect(self._show_movements)
        detail_layout.addWidget(self.kit_list)
        detail_layout.addWidget(self.movements_btn)
        layout.addLayout(detail_layout)

    def _pick_product(self) -> None:
        dialog = ProductSearchDialog(core=self.core, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.selected_product:
            self.sku_input.setText(dialog.selected_product.get("sku", ""))

    def _edit_product_from_table(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        product_id = int(self.table.item(row, 0).text())
        dlg = ProductEditorDialog(core=self.core, product_id=product_id, parent=self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.refresh_table()

    def adjust_stock(self) -> None:
        sku = self.sku_input.text().strip()
        qty = float(self.qty_input.value())
        if not sku or qty == 0:
            QtWidgets.QMessageBox.warning(self, "Datos faltantes", "SKU y cantidad son obligatorios")
            return
        product = self.core.get_product_by_sku_or_barcode(sku)
        if not product:
            QtWidgets.QMessageBox.warning(self, "No encontrado", "Producto no existe")
            return
        self.core.add_stock(product["id"], qty, reason=self.reason_input.text() or "ajuste manual")
        self.refresh_table()
        self.qty_input.setValue(0)

    def refresh_table(self) -> None:
        products = self.core.list_products_for_export()
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(products))
        for row_idx, row in enumerate(products):
            values = [
                row.get("id") or row.get("product_id"),
                row.get("sku"),
                row.get("name"),
                row.get("sale_type") or "unidad",
                f"{float(row.get('stock', 0.0) or 0.0):.2f}",
                f"{float(row.get('min_stock', 0.0) or 0.0):.2f}",
                f"{float(row.get('max_stock', 0.0) or 0.0):.2f}",
            ]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_idx, col, cell)
        self.table.itemSelectionChanged.connect(self._update_kit_panel)
        self.table.setUpdatesEnabled(True)

    def _update_kit_panel(self) -> None:
        row = self.table.currentRow()
        self.kit_list.clear()
        if row < 0:
            return
        product_id = int(self.table.item(row, 0).text())
        product = self.core.get_product(product_id)
        if not product or (product.get("sale_type") or "unit") != "kit":
            return
        for comp in self.core.get_kit_items(product_id):
            self.kit_list.addItem(f"{comp.get('qty', 1)} x {comp.get('product_id')}")

    def _show_movements(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        product_id = int(self.table.item(row, 0).text())
        movements = self.core.get_inventory_movements(product_id)
        if not movements:
            QtWidgets.QMessageBox.information(self, "Movimientos", "Sin movimientos recientes")
            return
        text = "\n".join(
            f"{m['created_at']} | {m['reason']} | {m['qty_change']}" if isinstance(m, dict) else str(dict(m))
            for m in movements
        )
        QtWidgets.QMessageBox.information(self, "Movimientos", text)


class CustomersTab(QtWidgets.QWidget):
    def __init__(self, core: POSCore, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self.selected_customer_id: int | None = None
        self._build_ui()
        self.refresh_table()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        search_layout = QtWidgets.QHBoxLayout()
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Buscar por nombre, teléfono, email o RFC…")
        self.search_input.textChanged.connect(self.refresh_table)
        search_layout.addWidget(QtWidgets.QLabel("Buscar"))
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        btn_layout = QtWidgets.QHBoxLayout()
        self.new_btn = QtWidgets.QPushButton("Nuevo Cliente")
        self.save_btn = QtWidgets.QPushButton("Guardar")
        self.delete_btn = QtWidgets.QPushButton("Eliminar")
        self.payment_btn = QtWidgets.QPushButton("Abonar cuenta")
        self.overview_btn = QtWidgets.QPushButton("Estado de Cuenta")
        self.export_btn = QtWidgets.QPushButton("Exportar…")
        for btn, handler in [
            (self.new_btn, self.new_customer),
            (self.save_btn, self.save_customer),
            (self.delete_btn, self.delete_customer),
            (self.payment_btn, self.open_payment_dialog),
            (self.overview_btn, self.open_overview),
            (self.export_btn, self.export_customers),
        ]:
            btn.clicked.connect(handler)
        btn_layout.addWidget(self.new_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.payment_btn)
        btn_layout.addWidget(self.overview_btn)
        btn_layout.addWidget(self.export_btn)
        layout.addLayout(btn_layout)

        splitter = QtWidgets.QSplitter()
        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_container)
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Avatar", "Nombre", "Tel", "Email", "Crédito límite", "Saldo"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self.load_selected)
        self.table.itemDoubleClicked.connect(lambda *_: self.overview_btn.click())
        left_layout.addWidget(self.table)

        right_container = QtWidgets.QScrollArea()
        right_container.setWidgetResizable(True)
        form_host = QtWidgets.QWidget()
        form_layout = QtWidgets.QFormLayout(form_host)
        self.first_name = QtWidgets.QLineEdit()
        self.last_name = QtWidgets.QLineEdit()
        self.phone = QtWidgets.QLineEdit()
        self.email = QtWidgets.QLineEdit()
        self.email_fiscal = QtWidgets.QLineEdit()
        self.rfc = QtWidgets.QLineEdit()
        self.razon_social = QtWidgets.QLineEdit()
        self.regimen_fiscal = QtWidgets.QLineEdit()
        self.domicilio1 = QtWidgets.QLineEdit()
        self.domicilio2 = QtWidgets.QLineEdit()
        self.colonia = QtWidgets.QLineEdit()
        self.municipio = QtWidgets.QLineEdit()
        self.estado = QtWidgets.QLineEdit()
        self.pais = QtWidgets.QLineEdit("México")
        self.codigo_postal = QtWidgets.QLineEdit()
        self.notes = QtWidgets.QPlainTextEdit()
        self.vip_cb = QtWidgets.QCheckBox("Cliente VIP")
        self.credit_enabled = QtWidgets.QCheckBox("Tiene crédito autorizado")
        self.credit_mode = QtWidgets.QComboBox()
        self.credit_mode.addItems(["De máximo", "Ilimitado"])
        self.credit_limit = QtWidgets.QDoubleSpinBox()
        self.credit_limit.setMaximum(1_000_000)
        self.credit_limit.setPrefix("$")
        self.credit_limit.setDecimals(2)
        self.credit_balance = QtWidgets.QLabel("$0.00")
        self.credit_balance.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        form_layout.addRow("Nombre(s)", self.first_name)
        form_layout.addRow("Apellidos", self.last_name)
        form_layout.addRow("Teléfono", self.phone)
        form_layout.addRow("Email", self.email)
        form_layout.addRow("Email fiscal", self.email_fiscal)
        form_layout.addRow("RFC", self.rfc)
        form_layout.addRow("Razón social", self.razon_social)
        form_layout.addRow("Régimen fiscal", self.regimen_fiscal)
        form_layout.addRow("Domicilio 1", self.domicilio1)
        form_layout.addRow("Domicilio 2", self.domicilio2)
        form_layout.addRow("Colonia", self.colonia)
        form_layout.addRow("Municipio/Estado", self.municipio)
        form_layout.addRow("Estado/Provincia", self.estado)
        form_layout.addRow("País", self.pais)
        form_layout.addRow("Código postal", self.codigo_postal)
        form_layout.addRow("Notas", self.notes)
        form_layout.addRow(self.vip_cb)
        form_layout.addRow(self.credit_enabled)
        form_layout.addRow("Modo de crédito", self.credit_mode)
        form_layout.addRow("Límite de crédito", self.credit_limit)
        form_layout.addRow("Saldo actual", self.credit_balance)
        right_container.setWidget(form_host)

        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F2), self, self.open_overview)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Delete), self, self.delete_customer)
        QtGui.QShortcut(QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.New), self, self.new_customer)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Return), self, self.save_customer)

    def _avatar_color(self, seed: str) -> str:
        h = hash(seed) & 0xFFFFFF
        r = (((h >> 16) & 0xFF) + 255) // 2
        g = (((h >> 8) & 0xFF) + 255) // 2
        b = ((h & 0xFF) + 255) // 2
        return f"rgb({r},{g},{b})"

    def _reset_form(self) -> None:
        for widget in [
            self.first_name,
            self.last_name,
            self.phone,
            self.email,
            self.email_fiscal,
            self.rfc,
            self.razon_social,
            self.regimen_fiscal,
            self.domicilio1,
            self.domicilio2,
            self.colonia,
            self.municipio,
            self.estado,
            self.pais,
            self.codigo_postal,
        ]:
            widget.clear()
        self.pais.setText("México")
        self.notes.clear()
        self.vip_cb.setChecked(False)
        self.credit_enabled.setChecked(False)
        self.credit_mode.setCurrentIndex(0)
        self.credit_limit.setValue(0.0)
        self.credit_balance.setText("$0.00")

    def _gather_data(self) -> dict[str, Any]:
        credit_authorized = self.credit_enabled.isChecked()
        credit_limit = -1.0 if credit_authorized and self.credit_mode.currentText() == "Ilimitado" else self.credit_limit.value()
        return {
            "first_name": self.first_name.text().strip(),
            "last_name": self.last_name.text().strip(),
            "phone": self.phone.text().strip(),
            "email": self.email.text().strip(),
            "email_fiscal": self.email_fiscal.text().strip(),
            "rfc": self.rfc.text().strip(),
            "razon_social": self.razon_social.text().strip(),
            "regimen_fiscal": self.regimen_fiscal.text().strip(),
            "domicilio1": self.domicilio1.text().strip(),
            "domicilio2": self.domicilio2.text().strip(),
            "colonia": self.colonia.text().strip(),
            "municipio": self.municipio.text().strip(),
            "estado": self.estado.text().strip(),
            "pais": self.pais.text().strip(),
            "codigo_postal": self.codigo_postal.text().strip(),
            "notes": self.notes.toPlainText().strip(),
            "vip": self.vip_cb.isChecked(),
            "credit_authorized": credit_authorized,
            "credit_limit": credit_limit if credit_authorized else 0.0,
        }

    def refresh_table(self) -> None:
        query = self.search_input.text().strip()
        customers = self.core.search_customers(query) if query else self.core.list_customers(limit=300)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(customers))
        for row_idx, row in enumerate(customers):
            customer = dict(row)
            full_name = (customer.get("full_name") or "").strip() or customer.get("first_name") or ""
            initials = "".join([part[0] for part in full_name.split() if part][:2]).upper() or "CL"
            bg = self._avatar_color(full_name or initials)
            values = [
                customer["id"],
                initials,
                full_name,
                customer.get("phone") or "",
                customer.get("email") or "",
                "Ilimitado" if float(customer.get("credit_limit", 0.0) or 0.0) < 0 else f"{float(customer.get('credit_limit', 0.0) or 0.0):.2f}",
                f"{float(customer.get('credit_balance', 0.0) or 0.0):.2f}",
            ]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if col == 1:
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                    item.setBackground(QtGui.QColor(bg))
                self.table.setItem(row_idx, col, item)
        self.table.setUpdatesEnabled(True)

    def load_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            self.selected_customer_id = None
            return
        self.selected_customer_id = int(self.table.item(row, 0).text())
        record_row = self.core.get_customer(self.selected_customer_id)
        if not record_row:
            return
        record = dict(record_row)
        self.first_name.setText(record.get("first_name") or "")
        self.last_name.setText(record.get("last_name") or "")
        self.phone.setText(record.get("phone") or "")
        self.email.setText(record.get("email") or "")
        self.email_fiscal.setText(record.get("email_fiscal") or "")
        self.rfc.setText(record.get("rfc") or "")
        self.razon_social.setText(record.get("razon_social") or "")
        self.regimen_fiscal.setText(record.get("regimen_fiscal") or "")
        self.domicilio1.setText(record.get("domicilio1") or "")
        self.domicilio2.setText(record.get("domicilio2") or "")
        self.colonia.setText(record.get("colonia") or "")
        self.municipio.setText(record.get("municipio") or "")
        self.estado.setText(record.get("estado") or "")
        self.pais.setText(record.get("pais") or "México")
        self.codigo_postal.setText(record.get("codigo_postal") or "")
        self.notes.setPlainText(record.get("notes") or "")
        self.vip_cb.setChecked(bool(record.get("vip")))
        credit_limit = float(record.get("credit_limit", 0.0) or 0.0)
        authorized = bool(record.get("credit_authorized") or credit_limit != 0)
        self.credit_enabled.setChecked(authorized)
        if credit_limit < 0:
            self.credit_mode.setCurrentText("Ilimitado")
        else:
            self.credit_mode.setCurrentText("De máximo")
            self.credit_limit.setValue(max(0.0, credit_limit))
        balance = float(record.get("credit_balance", 0.0) or 0.0)
        self.credit_balance.setText(f"$ {balance:,.2f}")
        self.payment_btn.setEnabled(balance > 0)

    def new_customer(self) -> None:
        self.selected_customer_id = None
        self._reset_form()
        self.first_name.setFocus()

    def save_customer(self) -> None:
        data = self._gather_data()
        if not data["first_name"]:
            QtWidgets.QMessageBox.warning(self, "Nombre requerido", "El nombre es obligatorio")
            return
        try:
            if self.selected_customer_id:
                self.core.update_customer(self.selected_customer_id, data)
                QtWidgets.QMessageBox.information(self, "Actualizado", "Cliente actualizado")
            else:
                self.selected_customer_id = self.core.create_customer(data)
                QtWidgets.QMessageBox.information(self, "Guardado", "Cliente creado correctamente")
            self.refresh_table()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo guardar: {exc}")

    def delete_customer(self) -> None:
        if not self.selected_customer_id:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Elige un cliente a eliminar")
            return
        if QtWidgets.QMessageBox.question(self, "Eliminar", "¿Borrar cliente seleccionado?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.core.delete_customer(self.selected_customer_id)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", str(exc))
            return
        QtWidgets.QMessageBox.information(self, "Eliminado", "Cliente eliminado exitosamente")
        self.selected_customer_id = None
        self.refresh_table()
        self._reset_form()

    def open_payment_dialog(self) -> None:
        if not self.selected_customer_id:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Elige un cliente para abonar")
            return
        customer_row = self.core.get_customer(self.selected_customer_id)
        if not customer_row:
            QtWidgets.QMessageBox.warning(self, "No encontrado", "Cliente no disponible")
            return
        customer = dict(customer_row)
        balance = float(customer.get("credit_balance", 0.0) or 0.0)
        if balance <= 0:
            QtWidgets.QMessageBox.information(self, "Sin saldo", "Este cliente no tiene saldo pendiente")
            return
        dlg = CreditPaymentDialog(
            customer_name=(customer.get("full_name") or "").strip() or customer.get("first_name") or "Cliente",
            credit_limit=float(customer.get("credit_limit", 0.0) or 0.0),
            credit_balance=balance,
            parent=self,
        )
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg.result_data:
            try:
                self.core.register_credit_payment(
                    self.selected_customer_id,
                    dlg.result_data["amount"],
                    dlg.result_data.get("notes") or None,
                    STATE.user_id,
                )
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo registrar el abono: {exc}")
                return
            QtWidgets.QMessageBox.information(self, "Abono registrado", "El abono se registró correctamente")
            self.refresh_table()
            self.load_selected()

    def open_overview(self) -> None:
        if not self.selected_customer_id:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Elige un cliente")
            return
        customer_row = self.core.get_customer_full_profile(self.selected_customer_id)
        customer_name = (customer_row.get("full_name") if customer_row else "Cliente") if customer_row else "Cliente"
        dlg = CreditStatementDialog(self.core, self.selected_customer_id, customer_name, self)
        dlg.exec()

    def export_customers(self) -> None:
        customers = self.core.list_all_customers_with_credit_meta()
        if not customers:
            QtWidgets.QMessageBox.information(self, "Exportar", "No hay clientes para exportar")
            return
        path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Exportar clientes",
            "clientes",
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not path:
            return
        try:
            if selected_filter.startswith("Excel") or path.endswith(".xlsx"):
                export_customers_to_excel(customers, path)
            else:
                export_customers_to_csv(customers, path)
            QtWidgets.QMessageBox.information(self, "Exportar", "Catálogo exportado correctamente")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Exportar", f"No se pudo exportar: {exc}")

class HistoryTab(QtWidgets.QWidget):
    def __init__(self, core: POSCore, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self._build_ui()
        self.refresh_sales()

    def _build_ui(self) -> None:
        layout = QtWidgets.QHBoxLayout(self)

        left = QtWidgets.QVBoxLayout()
        self.sales_table = QtWidgets.QTableWidget(0, 4)
        self.sales_table.setHorizontalHeaderLabels(["ID", "Fecha", "Total", "CFDI"])
        self.sales_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.sales_table.selectionModel()
        self.sales_table.itemSelectionChanged.connect(self.refresh_items)
        left.addWidget(QtWidgets.QLabel("Ventas recientes"))
        left.addWidget(self.sales_table)

        btns = QtWidgets.QHBoxLayout()
        self.issue_cfdi_btn = QtWidgets.QPushButton("Facturar venta")
        self.view_cfdi_btn = QtWidgets.QPushButton("Ver CFDI")
        self.cancel_cfdi_btn = QtWidgets.QPushButton("Cancelar CFDI")
        self.issue_cfdi_btn.clicked.connect(self._issue_cfdi)
        self.view_cfdi_btn.clicked.connect(self._view_cfdi)
        self.cancel_cfdi_btn.clicked.connect(self._cancel_cfdi)
        btns.addWidget(self.issue_cfdi_btn)
        btns.addWidget(self.view_cfdi_btn)
        btns.addWidget(self.cancel_cfdi_btn)
        left.addLayout(btns)

        right = QtWidgets.QVBoxLayout()
        self.items_table = QtWidgets.QTableWidget(0, 4)
        self.items_table.setHorizontalHeaderLabels(["Producto", "Cantidad", "Precio", "Total"])
        self.items_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        right.addWidget(QtWidgets.QLabel("Detalle"))
        right.addWidget(self.items_table)

        layout.addLayout(left, 2)
        layout.addLayout(right, 3)

    def refresh_sales(self) -> None:
        sales = self.core.list_recent_sales(limit=50)
        self.sales_table.setUpdatesEnabled(False)
        self.sales_table.setRowCount(0)
        self.sales_table.setRowCount(len(sales))
        for row_idx, sale in enumerate(sales):
            cfdi = self.core.get_cfdi_for_sale(int(sale["id"]))
            cfdi_flag = "Sí" if cfdi else "No"
            values = [sale["id"], sale["ts"], f"{sale['total']:.2f}", cfdi_flag]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.sales_table.setItem(row_idx, col, item)
        self.sales_table.setUpdatesEnabled(True)

    def refresh_items(self) -> None:
        row = self.sales_table.currentRow()
        if row < 0:
            return
        sale_id = int(self.sales_table.item(row, 0).text())
        items = self.core.get_sale_items(sale_id)
        self.items_table.setUpdatesEnabled(False)
        self.items_table.setRowCount(0)
        self.items_table.setRowCount(len(items))
        for idx, item in enumerate(items):
            values = [item["name"], f"{item['qty']:.2f}", f"{item['price']:.2f}", f"{item['total']:.2f}"]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(idx, col, cell)
        self.items_table.setUpdatesEnabled(True)

    def _selected_sale_id(self) -> int | None:
        row = self.sales_table.currentRow()
        if row < 0:
            return None
        return int(self.sales_table.item(row, 0).text())

    def _issue_cfdi(self) -> None:
        sale_id = self._selected_sale_id()
        if not sale_id:
            QtWidgets.QMessageBox.warning(self, "CFDI", "Selecciona una venta")
            return
        if self.core.get_cfdi_for_sale(sale_id):
            QtWidgets.QMessageBox.information(self, "CFDI", "Esta venta ya tiene CFDI")
            return
        uso, ok = QtWidgets.QInputDialog.getText(self, "Uso CFDI", "Uso CFDI:", text="G03")
        if not ok:
            return
        forma, ok = QtWidgets.QInputDialog.getText(self, "Forma de pago", "Forma de pago:", text="01")
        if not ok:
            return
        metodo, ok = QtWidgets.QInputDialog.getText(self, "Método de pago", "Método de pago:", text="PUE")
        if not ok:
            return
        try:
            result = self.core.issue_cfdi_for_sale(sale_id, uso_cfdi=uso or "G03", forma_pago=forma or "01", metodo_pago=metodo or "PUE")
            QtWidgets.QMessageBox.information(self, "CFDI", f"Timbrado correcto UUID: {result.get('uuid')}")
            self.refresh_sales()
        except Exception as exc:  # noqa: BLE001
            logging.exception("CFDI issue failed")
            QtWidgets.QMessageBox.critical(self, "CFDI", str(exc))

    def _view_cfdi(self) -> None:
        sale_id = self._selected_sale_id()
        if not sale_id:
            return
        cfdi = self.core.get_cfdi_for_sale(sale_id)
        if not cfdi or not cfdi.get("pdf_path"):
            QtWidgets.QMessageBox.information(self, "CFDI", "Sin CFDI para esta venta")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(cfdi["pdf_path"]))

    def _cancel_cfdi(self) -> None:
        sale_id = self._selected_sale_id()
        if not sale_id:
            return
        cfdi = self.core.get_cfdi_for_sale(sale_id)
        if not cfdi:
            QtWidgets.QMessageBox.warning(self, "CFDI", "No hay CFDI para cancelar")
            return
        motivo, ok = QtWidgets.QInputDialog.getText(self, "Cancelar CFDI", "Motivo:")
        if not ok or not motivo.strip():
            return
        try:
            self.core.cancel_cfdi(int(cfdi["id"]), motivo.strip())
            QtWidgets.QMessageBox.information(self, "CFDI", "CFDI cancelado")
            self.refresh_sales()
        except Exception as exc:  # noqa: BLE001
            logging.exception("CFDI cancel failed")
            QtWidgets.QMessageBox.critical(self, "CFDI", str(exc))


class LayawaysTab(QtWidgets.QWidget):
    def __init__(self, core: POSCore, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self._layaways_cache: list[QtCore.QObject] | list[dict] = []
        self._build_ui()
        self.refresh_layaways()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        filter_layout = QtWidgets.QHBoxLayout()
        self.status_filter = QtWidgets.QComboBox()
        self.status_filter.addItems(["Todos", "Pendiente", "Liquidado", "Cancelado", "Vencido"])
        self.status_filter.currentIndexChanged.connect(self.refresh_layaways)
        self.customer_search = QtWidgets.QLineEdit()
        self.customer_search.setPlaceholderText("Filtrar por cliente")
        self.customer_search.textChanged.connect(self.refresh_layaways)
        self.date_from = QtWidgets.QDateEdit(QtCore.QDate.currentDate().addMonths(-1))
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setCalendarPopup(True)
        self.date_to = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setCalendarPopup(True)
        refresh_btn = QtWidgets.QPushButton("Refrescar")
        refresh_btn.clicked.connect(self.refresh_layaways)
        filter_layout.addWidget(QtWidgets.QLabel("Estado:"))
        filter_layout.addWidget(self.status_filter)
        filter_layout.addWidget(QtWidgets.QLabel("Cliente:"))
        filter_layout.addWidget(self.customer_search)
        filter_layout.addWidget(QtWidgets.QLabel("Desde"))
        filter_layout.addWidget(self.date_from)
        filter_layout.addWidget(QtWidgets.QLabel("Hasta"))
        filter_layout.addWidget(self.date_to)
        filter_layout.addStretch(1)
        filter_layout.addWidget(refresh_btn)
        layout.addLayout(filter_layout)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Fecha", "Cliente", "Total", "Pagado", "Saldo", "Estado"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.refresh_items)
        self.table.doubleClicked.connect(self._open_detail)
        layout.addWidget(self.table)

        detail_layout = QtWidgets.QHBoxLayout()
        self.items_table = QtWidgets.QTableWidget(0, 4)
        self.items_table.setHorizontalHeaderLabels(["Producto", "Cantidad", "Precio", "Total"])
        self.items_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        detail_layout.addWidget(self.items_table, 3)

        self.payments_table = QtWidgets.QTableWidget(0, 3)
        self.payments_table.setHorizontalHeaderLabels(["Fecha", "Monto", "Notas"])
        self.payments_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        detail_layout.addWidget(self.payments_table, 2)
        layout.addLayout(detail_layout)

        btn_layout = QtWidgets.QHBoxLayout()
        self.pay_btn = QtWidgets.QPushButton("Registrar abono")
        self.liquidate_btn = QtWidgets.QPushButton("Liquidar")
        self.cancel_btn = QtWidgets.QPushButton("Cancelar")
        self.pay_btn.clicked.connect(self._register_payment)
        self.liquidate_btn.clicked.connect(self._liquidate)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.pay_btn)
        btn_layout.addWidget(self.liquidate_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _status_code(self) -> str | None:
        mapping = {
            "Pendiente": "pendiente",
            "Liquidado": "liquidado",
            "Cancelado": "cancelado",
            "Vencido": "vencido",
            "Todos": "all",
        }
        return mapping.get(self.status_filter.currentText(), "pendiente")

    def _selected_layaway(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._layaways_cache):
            return None
        return self._layaways_cache[row]

    def refresh_layaways(self) -> None:
        status = self._status_code()
        date_range = None
        if self.date_from.date().isValid() and self.date_to.date().isValid():
            date_range = (
                self.date_from.date().toString("yyyy-MM-dd"),
                self.date_to.date().toString("yyyy-MM-dd"),
            )
        layaways = self.core.list_layaways(
            branch_id=STATE.branch_id,
            status=status,
            date_range=date_range,
        )
        search = self.customer_search.text().strip().lower()
        if search:
            layaways = [l for l in layaways if search in (l.get("customer_name", "").lower())]
        self._layaways_cache = [dict(l) for l in layaways]
        self.table.setRowCount(len(layaways))
        for row_idx, layaway in enumerate(layaways):
            paid = float(layaway.get("paid_total", 0.0))
            balance = float(layaway.get("balance_calc", layaway.get("balance", 0.0)))
            values = [
                layaway["id"],
                layaway.get("created_at", ""),
                layaway["customer_name"] or "",
                f"{layaway['total']:.2f}",
                f"{paid:.2f}",
                f"{balance:.2f}",
                layaway.get("display_status", layaway.get("status", "")),
            ]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                if col in (3, 4, 5):
                    cell.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, col, cell)
        self.items_table.setRowCount(0)
        self.payments_table.setRowCount(0)

    def refresh_items(self) -> None:
        layaway = self._selected_layaway()
        if not layaway:
            return
        layaway_id = layaway["id"]
        items = self.core.get_layaway_items(layaway_id)
        self.items_table.setRowCount(len(items))
        for idx, item in enumerate(items):
            values = [item["name"], f"{item['qty']:.2f}", f"{item['price']:.2f}", f"{item['total']:.2f}"]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(idx, col, cell)

        payments = self.core.get_layaway_payments(layaway_id)
        self.payments_table.setRowCount(len(payments))
        for idx, pay in enumerate(payments):
            values = [pay["timestamp"], f"{pay['amount']:.2f}", pay.get("notes", "") or ""]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(str(value))
                cell.setFlags(cell.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.payments_table.setItem(idx, col, cell)

    def _register_payment(self) -> None:
        layaway = self._selected_layaway()
        if not layaway:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Selecciona un apartado")
            return
        balance = float(layaway.get("balance_calc", layaway.get("balance", 0.0)))
        if balance <= 0:
            QtWidgets.QMessageBox.information(self, "Sin saldo", "Este apartado no tiene saldo pendiente")
            return
        dialog = LayawayPaymentDialog(
            layaway.get("customer_name") or "Cliente",
            layaway["total"],
            layaway.get("paid_total", layaway.get("deposit", 0)),
            balance,
            self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted or not dialog.result_data:
            return
        try:
            self.core.add_layaway_payment(
                layaway["id"], dialog.result_data["amount"], notes=dialog.result_data.get("notes"), user_id=STATE.user_id
            )
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo registrar el abono: {exc}")
            return
        try:
            refreshed = self.core.get_layaway(layaway["id"])
            ticket_engine.print_layaway_payment(
                dict(refreshed or {}),
                {"amount": dialog.result_data["amount"], "notes": dialog.result_data.get("notes")},
            )
        except Exception:
            pass
        self.refresh_layaways()
        self.refresh_items()

    def _cancel(self) -> None:
        layaway = self._selected_layaway()
        if not layaway:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Selecciona un apartado")
            return
        if QtWidgets.QMessageBox.question(self, "Cancelar", "¿Cancelar este apartado?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.core.cancel_layaway(layaway["id"], user_id=STATE.user_id)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo cancelar: {exc}")
            return
        self.refresh_layaways()

    def _liquidate(self) -> None:
        layaway = self._selected_layaway()
        if not layaway:
            QtWidgets.QMessageBox.warning(self, "Selecciona", "Selecciona un apartado")
            return
        if QtWidgets.QMessageBox.question(self, "Liquidar", "¿Liquidar y consumir el stock reservado?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.core.liquidate_layaway(layaway["id"], user_id=STATE.user_id)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"No se pudo liquidar: {exc}")
            return
        try:
            refreshed = self.core.get_layaway(layaway["id"])
            ticket_engine.print_layaway_liquidation(dict(refreshed or {}))
        except Exception:
            pass
        self.refresh_layaways()

    def _open_detail(self, *_: object) -> None:
        layaway = self._selected_layaway()
        if not layaway:
            return
        dlg = LayawayDetailDialog(self.core, layaway["id"], self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.result_action:
            self.refresh_layaways()


class TurnTab(QtWidgets.QWidget):
    def __init__(self, core: POSCore, parent: QtWidgets.QWidget | None = None, *, backup_engine: BackupEngine | None = None):
        super().__init__(parent)
        self.core = core
        self.backup_engine = backup_engine
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        button_bar = QtWidgets.QHBoxLayout()
        self.open_btn = QtWidgets.QPushButton("Abrir turno")
        self.open_btn.clicked.connect(self._open_turn)
        self.in_btn = QtWidgets.QPushButton("Entrada (F7)")
        self.in_btn.clicked.connect(lambda: self._cash_movement("in"))
        self.out_btn = QtWidgets.QPushButton("Salida (F8)")
        self.out_btn.clicked.connect(lambda: self._cash_movement("out"))
        self.drawer_btn = QtWidgets.QPushButton("Abrir cajón")
        self.drawer_btn.clicked.connect(self._open_drawer)
        self.partial_btn = QtWidgets.QPushButton("Corte parcial")
        self.partial_btn.clicked.connect(self._partial)
        self.close_btn = QtWidgets.QPushButton("Cerrar turno")
        self.close_btn.clicked.connect(self._close_turn)
        for btn in (self.open_btn, self.in_btn, self.out_btn, self.drawer_btn, self.partial_btn, self.close_btn):
            button_bar.addWidget(btn)
        layout.addLayout(button_bar)

        self.summary_lbl = QtWidgets.QLabel()
        layout.addWidget(self.summary_lbl)

        self.movements = QtWidgets.QTableWidget(0, 4)
        self.movements.setHorizontalHeaderLabels(["Fecha", "Tipo", "Monto", "Motivo"])
        self.movements.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.movements)

    def refresh(self) -> None:
        turn = self.core.get_current_turn(STATE.branch_id, STATE.user_id)
        if not turn:
            self.summary_lbl.setText("Sin turno activo")
            self.movements.setRowCount(0)
            return
        summary = self.core.get_turn_summary(turn["id"])
        self.summary_lbl.setText(
            f"Turno #{turn['id']} | Efectivo esperado: ${summary.get('expected_cash',0):.2f} | Ventas ef.: ${summary.get('cash_sales',0):.2f}"
        )
        moves = self.core.get_turn_movements(turn["id"])
        self.movements.setRowCount(0)
        for mov in moves:
            row = self.movements.rowCount()
            self.movements.insertRow(row)
            self.movements.setItem(row, 0, QtWidgets.QTableWidgetItem(str(mov.get("created_at"))))
            self.movements.setItem(row, 1, QtWidgets.QTableWidgetItem("Entrada" if mov.get("movement_type") == "in" else "Salida"))
            self.movements.setItem(row, 2, QtWidgets.QTableWidgetItem(f"$ {float(mov.get('amount',0)):.2f}"))
            self.movements.setItem(row, 3, QtWidgets.QTableWidgetItem(mov.get("reason") or ""))

    def _open_turn(self) -> None:
        dlg = TurnOpenDialog(STATE.username or "Usuario", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.result_data:
            try:
                turn_id = self.core.open_turn(STATE.branch_id, STATE.user_id, dlg.result_data["opening_amount"], dlg.result_data.get("notes"))
                ticket_engine.print_turn_open({
                    "id": turn_id,
                    "user": STATE.username or "",
                    "branch": STATE.branch_id,
                    "opening_amount": dlg.result_data["opening_amount"],
                    "notes": dlg.result_data.get("notes"),
                    "opened_at": "",
                })
                QtWidgets.QMessageBox.information(self, "Turno", "Turno abierto")
                self.refresh()
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.critical(self, "Error", str(exc))

    def _cash_movement(self, movement_type: str) -> None:
        if not self.core.get_current_turn(STATE.branch_id, STATE.user_id):
            QtWidgets.QMessageBox.warning(self, "Turno", "Abre un turno primero")
            return
        dlg = CashMovementDialog(movement_type, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.result_data:
            try:
                self.core.register_cash_movement(
                    None,
                    movement_type,
                    dlg.result_data["amount"],
                    reason=dlg.result_data.get("reason"),
                    branch_id=STATE.branch_id,
                    user_id=STATE.user_id,
                )
                QtWidgets.QMessageBox.information(self, "Movimiento", "Movimiento registrado")
                self.refresh()
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.critical(self, "Error", str(exc))

    def _partial(self) -> None:
        turn = self.core.get_current_turn(STATE.branch_id, STATE.user_id)
        if not turn:
            QtWidgets.QMessageBox.warning(self, "Turno", "No hay turno abierto")
            return
        summary = self.core.get_turn_summary(turn["id"])
        dlg = TurnPartialDialog(summary, self)
        dlg.exec()

    def _open_drawer(self) -> None:
        cfg = self.core.get_app_config()
        if not cfg.get("cash_drawer_enabled"):
            QtWidgets.QMessageBox.information(self, "Cajón", "Habilita el cajón en Configuración")
            return
        printer = cfg.get("printer_name") or ""
        pulse_str = cfg.get("cash_drawer_pulse_bytes", "\\x1B\\x70\\x00\\x19\\xFA")
        try:
            pulse_bytes = bytes(pulse_str, "utf-8").decode("unicode_escape").encode("latin1")
            ticket_engine.open_cash_drawer(printer, pulse_bytes)
        except Exception:  # noqa: BLE001
            logging.exception("No se pudo abrir el cajón")
            QtWidgets.QMessageBox.critical(self, "Cajón", "No se pudo abrir el cajón")

    def _close_turn(self) -> None:
        turn = self.core.get_current_turn(STATE.branch_id, STATE.user_id)
        if not turn:
            QtWidgets.QMessageBox.information(self, "Turno", "No hay turno abierto")
            return
        summary = self.core.get_turn_summary(turn["id"])
        dlg = TurnCloseDialog(summary, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.result_data:
            try:
                self.core.close_turn(turn["id"], dlg.result_data["closing_amount"], dlg.result_data.get("notes"))
                if self.backup_engine:
                    self.backup_engine.auto_backup_flow()
                QtWidgets.QMessageBox.information(self, "Turno", "Turno cerrado")
                self.refresh()
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.critical(self, "Error", str(exc))


class ReportsTab(QtWidgets.QWidget):
    def __init__(self, core: POSCore, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self.latest_data: dict[str, dict[str, list[list[str]]]] = {}
        self._build_ui()
        self.generate_reports()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        filter_layout = QtWidgets.QHBoxLayout()
        self.date_from = QtWidgets.QDateEdit(QtCore.QDate.currentDate().addMonths(-1))
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_to = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.branch_combo = QtWidgets.QComboBox()
        for br in self.core.list_branches():
            self.branch_combo.addItem(br["name"], br["id"])
            if br["is_default"]:
                self.branch_combo.setCurrentIndex(self.branch_combo.count() - 1)
        self.generate_btn = QtWidgets.QPushButton("CALCULAR")
        self.generate_btn.clicked.connect(self.generate_reports)

        filter_layout.addWidget(QtWidgets.QLabel("Desde"))
        filter_layout.addWidget(self.date_from)
        filter_layout.addWidget(QtWidgets.QLabel("Hasta"))
        filter_layout.addWidget(self.date_to)
        filter_layout.addWidget(QtWidgets.QLabel("Sucursal"))
        filter_layout.addWidget(self.branch_combo)
        filter_layout.addStretch(1)
        filter_layout.addWidget(self.generate_btn)
        layout.addLayout(filter_layout)

        self.tab_widget = QtWidgets.QTabWidget()
        self.sales_tab = self._build_sales_tab()
        self.top_tab = self._build_top_products_tab()
        self.daily_tab = self._build_daily_tab()
        self.payment_tab = self._build_payment_tab()
        self.credit_tab = self._build_credit_tab()
        self.layaway_tab = self._build_layaway_tab()
        self.turn_tab = self._build_turn_tab()
        self.backup_tab = self._build_backup_tab()
        self.cfdi_tab = self._build_cfdi_tab()

        self.tab_widget.addTab(self.sales_tab, "Ventas generales")
        self.tab_widget.addTab(self.top_tab, "Productos más vendidos")
        self.tab_widget.addTab(self.daily_tab, "Ventas por día")
        self.tab_widget.addTab(self.payment_tab, "Método de pago")
        self.tab_widget.addTab(self.credit_tab, "Créditos / CxC")
        self.tab_widget.addTab(self.layaway_tab, "Apartados")
        self.tab_widget.addTab(self.turn_tab, "Caja / Turnos")
        self.tab_widget.addTab(self.backup_tab, "Backups & Integridad")
        self.tab_widget.addTab(self.cfdi_tab, "CFDIs emitidos")
        layout.addWidget(self.tab_widget)

    # --- builders -------------------------------------------------
    def _chart_table_layout(self) -> tuple[QtWidgets.QHBoxLayout, QtCharts.QChartView, QtWidgets.QTableWidget]:
        chart_view = QtCharts.QChartView()
        chart_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        table = QtWidgets.QTableWidget()
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(chart_view, 1)
        layout.addWidget(table, 1)
        return layout, chart_view, table

    def _build_sales_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        layout, chart_view, table = self._chart_table_layout()
        self.sales_chart_view = chart_view
        self.sales_table = table
        self.sales_table.setColumnCount(6)
        self.sales_table.setHorizontalHeaderLabels(["Fecha", "Subtotal", "IVA", "Total", "Cliente", "Pago"])
        v.addLayout(layout)
        self.sales_summary = QtWidgets.QLabel("--")
        btn = QtWidgets.QPushButton("EXPORTAR")
        btn.clicked.connect(lambda: self._export_dataset("Ventas", "sales", pdf_helper.export_sales_summary_pdf))
        v.addWidget(self.sales_summary)
        v.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        return w

    def _build_top_products_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        layout, chart_view, table = self._chart_table_layout()
        self.top_chart_view = chart_view
        self.top_table = table
        self.top_table.setColumnCount(4)
        self.top_table.setHorizontalHeaderLabels(["Producto", "Cantidad", "Total", "% del Total"])
        btn = QtWidgets.QPushButton("EXPORTAR")
        btn.clicked.connect(lambda: self._export_dataset("Top Productos", "top", pdf_helper.export_top_products_pdf))
        v.addLayout(layout)
        v.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        return w

    def _build_daily_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        layout, chart_view, table = self._chart_table_layout()
        self.daily_chart_view = chart_view
        self.daily_table = table
        self.daily_table.setColumnCount(2)
        self.daily_table.setHorizontalHeaderLabels(["Día", "Total"])
        btn = QtWidgets.QPushButton("EXPORTAR")
        btn.clicked.connect(lambda: self._export_dataset("Ventas por día", "daily", pdf_helper.export_daily_sales_pdf))
        v.addLayout(layout)
        v.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        return w

    def _build_payment_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        layout, chart_view, table = self._chart_table_layout()
        self.payment_chart_view = chart_view
        self.payment_table = table
        self.payment_table.setColumnCount(3)
        self.payment_table.setHorizontalHeaderLabels(["Método", "Monto", "%"])
        btn = QtWidgets.QPushButton("EXPORTAR")
        btn.clicked.connect(lambda: self._export_dataset("Métodos de pago", "payment", pdf_helper.export_sales_summary_pdf))
        v.addLayout(layout)
        v.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        return w

    def _build_credit_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        layout, chart_view, table = self._chart_table_layout()
        self.credit_chart_view = chart_view
        self.credit_table = table
        self.credit_table.setColumnCount(3)
        self.credit_table.setHorizontalHeaderLabels(["Cliente", "Saldo", "Límite"])
        self.credit_total_label = QtWidgets.QLabel("--")
        btn_layout = QtWidgets.QHBoxLayout()
        stmt_btn = QtWidgets.QPushButton("Estado de Cuenta…")
        stmt_btn.clicked.connect(self._open_credit_statement_from_report)
        export_btn = QtWidgets.QPushButton("EXPORTAR")
        export_btn.clicked.connect(lambda: self._export_dataset("Créditos", "credit", pdf_helper.export_credit_report_pdf))
        btn_layout.addWidget(stmt_btn)
        btn_layout.addStretch(1)
        btn_layout.addWidget(export_btn)
        v.addLayout(layout)
        v.addWidget(self.credit_total_label)
        v.addLayout(btn_layout)
        return w

    def _build_layaway_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        layout, chart_view, table = self._chart_table_layout()
        self.layaway_chart_view = chart_view
        self.layaway_table = table
        self.layaway_table.setColumnCount(7)
        self.layaway_table.setHorizontalHeaderLabels(["ID", "Cliente", "Fecha", "Total", "Pagado", "Saldo", "Estado"])
        self.layaway_total_label = QtWidgets.QLabel("--")
        btn = QtWidgets.QPushButton("EXPORTAR")
        btn.clicked.connect(lambda: self._export_dataset("Apartados", "layaway", pdf_helper.export_layaway_report_pdf))
        v.addLayout(layout)
        v.addWidget(self.layaway_total_label)
        v.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        return w

    def _build_turn_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        layout, chart_view, table = self._chart_table_layout()
        self.turn_chart_view = chart_view
        self.turn_table = table
        self.turn_table.setColumnCount(5)
        self.turn_table.setHorizontalHeaderLabels(["ID", "Usuario", "Fondo", "Efectivo esperado", "Cierre"])
        self.turn_summary = QtWidgets.QLabel("--")
        btn = QtWidgets.QPushButton("EXPORTAR")
        btn.clicked.connect(lambda: self._export_dataset("Turnos", "turns", pdf_helper.export_turn_report_pdf))
        v.addLayout(layout)
        v.addWidget(self.turn_summary)
        v.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        return w

    def _build_backup_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        self.backup_table = QtWidgets.QTableWidget(0, 6)
        self.backup_table.setHorizontalHeaderLabels(["Fecha", "Archivo", "SHA256", "Tamaño", "Ubicación", "Notas"])
        self.backup_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.backup_table)
        self.backup_summary = QtWidgets.QLabel("--")
        v.addWidget(self.backup_summary)
        btn = QtWidgets.QPushButton("EXPORTAR")
        btn.clicked.connect(lambda: self._export_dataset("Backups", "backups", None))
        v.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        return w

    def _build_cfdi_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        self.cfdi_table = QtWidgets.QTableWidget(0, 7)
        self.cfdi_table.setHorizontalHeaderLabels(["ID", "UUID", "Serie/Folio", "Fecha", "Cliente", "Total", "Estado"])
        self.cfdi_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.cfdi_table)
        btn = QtWidgets.QPushButton("EXPORTAR")
        btn.clicked.connect(lambda: self._export_dataset("CFDI", "cfdi", None))
        v.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        return w

    # --- population ------------------------------------------------
    def generate_reports(self) -> None:
        date_from = self.date_from.date().toString("yyyy-MM-dd") if self.date_from.date().isValid() else None
        date_to = self.date_to.date().toString("yyyy-MM-dd") if self.date_to.date().isValid() else None
        branch_id = self.branch_combo.currentData()

        self._populate_sales(date_from, date_to, branch_id)
        self._populate_top_products(date_from, date_to, branch_id)
        self._populate_daily(date_from, date_to, branch_id)
        self._populate_payment(date_from, date_to, branch_id)
        self._populate_credit(date_from, date_to, branch_id)
        self._populate_layaways(date_from, date_to, branch_id)
        self._populate_turns(date_from, date_to, branch_id)
        self._populate_backups()
        self._populate_cfdi(date_from, date_to)

    def _populate_sales(self, date_from: str | None, date_to: str | None, branch_id: int | None) -> None:
        rows: list[list[str]] = []
        sales = self.core.get_sales_by_range(date_from=date_from, date_to=date_to, branch_id=branch_id)
        for s in sales:
            rows.append(
                [
                    s["ts"],
                    f"{float(s['subtotal'] or 0):.2f}",
                    f"{float((s['total'] or 0) - (s['subtotal'] or 0)):.2f}",
                    f"{float(s['total'] or 0):.2f}",
                    s.get("customer_name") or "",
                    s.get("payment_methods") or s.get("payment_method", ""),
                ]
            )
        totals = sum(float(r["total"] or 0) for r in sales)
        avg = totals / len(sales) if sales else 0
        self.sales_summary.setText(f"Tickets: {len(sales)} | Total: ${totals:.2f} | Ticket prom: ${avg:.2f}")
        chart = charts_helper.make_line_chart("Ventas", [r[0] for r in rows], [float(r[3]) for r in rows]) if rows else QtCharts.QChart()
        self.sales_chart_view.setChart(chart)
        self._populate_table(self.sales_table, rows)
        self.latest_data["sales"] = {"headers": ["Fecha", "Subtotal", "IVA", "Total", "Cliente", "Pago"], "rows": rows}

    def _populate_top_products(self, date_from: str | None, date_to: str | None, branch_id: int | None) -> None:
        items = self.core.get_sale_items_by_range(date_from=date_from, date_to=date_to, branch_id=branch_id)
        total_revenue = sum(float(i["total"] or 0) for i in items) or 1
        rows: list[list[str]] = []
        categories: list[str] = []
        values: list[float] = []
        for item in items[:10]:
            revenue = float(item["total"] or 0)
            percent = (revenue / total_revenue) * 100
            rows.append([item["name"], f"{float(item['qty'] or 0):.2f}", f"{revenue:.2f}", f"{percent:.1f}%"])
            categories.append(item["name"])
            values.append(float(item["qty"] or 0))
        chart = charts_helper.make_bar_chart("Top productos", categories, values) if categories else QtCharts.QChart()
        self.top_chart_view.setChart(chart)
        self._populate_table(self.top_table, rows)
        self.latest_data["top"] = {"headers": ["Producto", "Cantidad", "Total", "% del Total"], "rows": rows}

    def _populate_backups(self) -> None:
        backups = self.core.list_backups()
        rows: list[list[str]] = []
        for b in backups[:20]:
            rows.append(
                [
                    b.get("created_at", ""),
                    b.get("filename", ""),
                    b.get("sha256", ""),
                    f"{int(b.get('size_bytes') or 0)}",
                    ", ".join(
                        loc
                        for flag, loc in [
                            (b.get("storage_local"), "Local"),
                            (b.get("storage_nas"), "NAS"),
                            (b.get("storage_cloud"), "Nube"),
                        ]
                        if flag
                    ),
                    b.get("notes", ""),
                ]
            )
        self._populate_table(self.backup_table, rows)
        self.backup_summary.setText(f"Total respaldos: {len(backups)}")
        self.latest_data["backups"] = {
            "headers": ["Fecha", "Archivo", "SHA256", "Tamaño", "Ubicación", "Notas"],
            "rows": rows,
        }

    def _populate_cfdi(self, date_from: str | None, date_to: str | None) -> None:
        cfdis = self.core.list_cfdi(date_from=date_from, date_to=date_to, customer_id=None, status=None)
        rows: list[list[str]] = []
        for c in cfdis:
            rows.append(
                [
                    c.get("id"),
                    c.get("uuid"),
                    f"{c.get('serie', '')}{c.get('folio', '')}",
                    c.get("fecha"),
                    c.get("customer_name") or "",
                    f"{float(c.get('total') or 0):.2f}",
                    c.get("status", ""),
                ]
            )
        self._populate_table(self.cfdi_table, rows)
        self.latest_data["cfdi"] = {
            "headers": ["ID", "UUID", "Serie/Folio", "Fecha", "Cliente", "Total", "Estado"],
            "rows": rows,
        }

    def _populate_daily(self, date_from: str | None, date_to: str | None, branch_id: int | None) -> None:
        data = self.core.get_sales_grouped_by_date(date_from=date_from, date_to=date_to, branch_id=branch_id)
        labels = [row["day"] for row in data]
        values = [float(row["total"] or 0) for row in data]
        rows = [[row["day"], f"{float(row['total'] or 0):.2f}"] for row in data]
        chart = charts_helper.make_line_chart("Ventas por día", labels, values) if labels else QtCharts.QChart()
        self.daily_chart_view.setChart(chart)
        self._populate_table(self.daily_table, rows)
        self.latest_data["daily"] = {"headers": ["Día", "Total"], "rows": rows}

    def _populate_payment(self, date_from: str | None, date_to: str | None, branch_id: int | None) -> None:
        grouped = self.core.get_sales_by_method(date_from=date_from, date_to=date_to, branch_id=branch_id)
        total = sum(float(r["amount"] or 0) for r in grouped) or 1
        rows: list[list[str]] = []
        labels: list[str] = []
        values: list[float] = []
        for row in grouped:
            amount = float(row["amount"] or 0)
            pct = (amount / total) * 100
            rows.append([row["method"], f"{amount:.2f}", f"{pct:.1f}%"])
            labels.append(row["method"])
            values.append(amount)
        chart = charts_helper.make_pie_chart("Métodos de pago", labels, values) if labels else QtCharts.QChart()
        self.payment_chart_view.setChart(chart)
        self._populate_table(self.payment_table, rows)
        self.latest_data["payment"] = {"headers": ["Método", "Monto", "%"], "rows": rows}

    def _populate_credit(self, date_from: str | None, date_to: str | None, branch_id: int | None) -> None:
        report = self.core.get_credit_report(date_from=date_from, date_to=date_to, branch_id=branch_id)
        rows: list[list[str]] = []
        labels: list[str] = []
        values: list[float] = []
        for acc in report["accounts"]:
            balance = float(acc["credit_balance"] or 0)
            rows.append([acc.get("full_name") or "", f"{balance:.2f}", f"{float(acc.get('credit_limit',0) or 0):.2f}"])
            labels.append(acc.get("full_name") or "")
            values.append(balance)
        chart = charts_helper.make_bar_chart("Cuentas por cobrar", labels, values) if labels else QtCharts.QChart()
        self.credit_chart_view.setChart(chart)
        self._populate_table(self.credit_table, rows)
        self.credit_total_label.setText(f"Saldo pendiente: ${float(report['total'] or 0):.2f}")
        self.latest_data["credit"] = {"headers": ["Cliente", "Saldo", "Límite"], "rows": rows}

    def _populate_layaways(self, date_from: str | None, date_to: str | None, branch_id: int | None) -> None:
        report = self.core.get_layaway_report(date_from=date_from, date_to=date_to, branch_id=branch_id)
        rows: list[list[str]] = []
        labels: list[str] = []
        values: list[float] = []
        for lay in report["layaways"]:
            balance = float(lay.get("balance_calc", lay.get("balance", 0.0)) or 0)
            rows.append(
                [
                    str(lay["id"]),
                    lay.get("customer_name") or "--",
                    lay.get("created_at", ""),
                    f"{float(lay['total'] or 0):.2f}",
                    f"{float(lay.get('paid_total', 0.0)):.2f}",
                    f"{balance:.2f}",
                    lay.get("display_status", lay.get("status", "")),
                ]
            )
            labels.append(f"#{lay['id']}")
            values.append(balance)
        chart = charts_helper.make_bar_chart("Apartados", labels, values) if labels else QtCharts.QChart()
        self.layaway_chart_view.setChart(chart)
        self._populate_table(self.layaway_table, rows)
        self.layaway_total_label.setText(
            f"Total saldo: ${float(report['total_balance'] or 0):.2f} | Depósitos: ${float(report['total_deposits'] or 0):.2f}"
        )
        self.latest_data["layaway"] = {
            "headers": ["ID", "Cliente", "Fecha", "Total", "Pagado", "Saldo", "Estado"],
            "rows": rows,
        }

    def _populate_turns(self, date_from: str | None, date_to: str | None, branch_id: int | None) -> None:
        turns = self.core.get_turns_by_range(date_from=date_from, date_to=date_to, branch_id=branch_id)
        rows: list[list[str]] = []
        labels: list[str] = []
        values: list[float] = []
        for t in turns:
            expected = float((t.get("expected_amount") if isinstance(t, dict) else t["expected_amount"]) or 0)
            rows.append(
                [
                    str(t["id"]),
                    str(t.get("user_id") if isinstance(t, dict) else t["user_id"]),
                    f"{float(t['opening_amount'] or 0):.2f}",
                    f"{expected:.2f}",
                    t.get("closed_at") if isinstance(t, dict) else t["closed_at"],
                ]
            )
            labels.append(f"#{t['id']}")
            values.append(expected)
        chart = charts_helper.make_bar_chart("Turnos", labels, values) if labels else QtCharts.QChart()
        self.turn_chart_view.setChart(chart)
        self._populate_table(self.turn_table, rows)
        total_expected = sum(values)
        self.turn_summary.setText(f"Turnos: {len(rows)} | Efectivo esperado acumulado: ${total_expected:.2f}")
        self.latest_data["turns"] = {
            "headers": ["ID", "Usuario", "Fondo", "Efectivo esperado", "Cierre"],
            "rows": rows,
        }

    # --- helpers ---------------------------------------------------
    def _open_credit_statement_from_report(self) -> None:
        row = self.credit_table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.information(self, "Selecciona", "Elige un cliente con saldo")
            return
        customer_name = self.credit_table.item(row, 0).text()
        customer_row = self.core.search_customers(customer_name, limit=1)
        if not customer_row:
            QtWidgets.QMessageBox.warning(self, "No encontrado", "No se localizó el cliente seleccionado")
            return
        customer_id = int(customer_row[0]["id"])
        dlg = CreditStatementDialog(self.core, customer_id, customer_name, self)
        dlg.exec()

    def _populate_table(self, table: QtWidgets.QTableWidget, rows: list[list[str]]) -> None:
        table.setRowCount(len(rows))
        for r, vals in enumerate(rows):
            for c, val in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(val)
                if isinstance(val, str) and val.replace(".", "", 1).replace("-", "", 1).isdigit():
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                table.setItem(r, c, item)

    def _export_dataset(self, title: str, key: str, pdf_fn) -> None:
        dataset = self.latest_data.get(key) or {}
        headers = dataset.get("headers", [])
        rows = dataset.get("rows", [])
        pdf_exporter = (lambda path: pdf_fn(dataset, path)) if pdf_fn else None
        dlg = ReportExportDialog(title, headers, rows, pdf_exporter=pdf_exporter, parent=self)
        dlg.exec()


class SettingsTab(QtWidgets.QWidget):
    """Basic settings tab with MultiCaja network configuration."""

    def __init__(self, core: POSCore, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.core = core
        self.cfg = self.core.get_app_config()
        self.fiscal_cfg = self.core.get_fiscal_config()
        layout = QtWidgets.QVBoxLayout(self)

        general_box = QtWidgets.QGroupBox("Modo")
        g_layout = QtWidgets.QFormLayout(general_box)
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["server", "client"])
        self.mode_combo.setCurrentText(self.cfg.get("mode", "server"))
        g_layout.addRow("Modo de trabajo", self.mode_combo)
        layout.addWidget(general_box)

        net_box = QtWidgets.QGroupBox("MultiCaja / Red")
        n_layout = QtWidgets.QFormLayout(net_box)
        self.server_ip = QtWidgets.QLineEdit(self.cfg.get("server_ip", "127.0.0.1"))
        self.server_port = QtWidgets.QSpinBox()
        self.server_port.setRange(1, 65535)
        self.server_port.setValue(int(self.cfg.get("server_port", 8000)))
        self.sync_interval = QtWidgets.QSpinBox()
        self.sync_interval.setRange(5, 3600)
        self.sync_interval.setValue(int(self.cfg.get("sync_interval_seconds", 10)))
        self.test_btn = QtWidgets.QPushButton("Probar conexión")
        self.test_btn.clicked.connect(self._test_connection)
        self.status_lbl = QtWidgets.QLabel("Estado desconocido")
        self.status_lbl.setStyleSheet("color: #f39c12;")
        n_layout.addRow("IP Servidor", self.server_ip)
        n_layout.addRow("Puerto", self.server_port)
        n_layout.addRow("Intervalo sync (s)", self.sync_interval)
        n_layout.addRow(self.test_btn, self.status_lbl)
        layout.addWidget(net_box)

        theme_box = QtWidgets.QGroupBox("Tema visual")
        t_layout = QtWidgets.QFormLayout(theme_box)
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "AMOLED", "Pastel", "RosaLupita"])
        self.theme_combo.setCurrentText(self.cfg.get("theme", "Light"))
        self.apply_theme_btn = QtWidgets.QPushButton("Aplicar tema")
        self.apply_theme_btn.clicked.connect(self._apply_theme)
        t_layout.addRow("Tema", self.theme_combo)
        t_layout.addRow(self.apply_theme_btn)
        layout.addWidget(theme_box)

        scanner_box = QtWidgets.QGroupBox("Lectores")
        s_layout = QtWidgets.QFormLayout(scanner_box)
        self.prefix_input = QtWidgets.QLineEdit(self.cfg.get("scanner_prefix", ""))
        self.suffix_input = QtWidgets.QLineEdit(self.cfg.get("scanner_suffix", ""))
        self.camera_enabled = QtWidgets.QCheckBox("Habilitar lector por cámara")
        self.camera_enabled.setChecked(bool(self.cfg.get("camera_scanner_enabled", False)))
        self.camera_index = QtWidgets.QSpinBox()
        self.camera_index.setRange(0, 8)
        self.camera_index.setValue(int(self.cfg.get("camera_scanner_index", 0)))
        s_layout.addRow("Prefijo escáner", self.prefix_input)
        s_layout.addRow("Sufijo escáner", self.suffix_input)
        s_layout.addRow(self.camera_enabled)
        s_layout.addRow("Índice de cámara", self.camera_index)
        layout.addWidget(scanner_box)

        printer_box = QtWidgets.QGroupBox("Impresora de tickets")
        p_layout = QtWidgets.QFormLayout(printer_box)
        self.printer_name = QtWidgets.QLineEdit(self.cfg.get("printer_name", ""))
        self.paper_width = QtWidgets.QComboBox()
        self.paper_width.addItems(["58mm", "80mm"])
        self.paper_width.setCurrentText(self.cfg.get("ticket_paper_width", "80mm"))
        self.auto_print = QtWidgets.QCheckBox("Imprimir automáticamente al cobrar")
        self.auto_print.setChecked(bool(self.cfg.get("auto_print_tickets", False)))
        self.test_print_btn = QtWidgets.QPushButton("Probar impresión")
        self.test_print_btn.clicked.connect(self._test_print)
        p_layout.addRow("Impresora CUPS", self.printer_name)
        p_layout.addRow("Ancho de papel", self.paper_width)
        p_layout.addRow(self.auto_print)
        p_layout.addRow(self.test_print_btn)
        layout.addWidget(printer_box)

        drawer_box = QtWidgets.QGroupBox("Cajón de dinero")
        d_layout = QtWidgets.QFormLayout(drawer_box)
        self.drawer_enabled = QtWidgets.QCheckBox("Abrir cajón al cobrar")
        self.drawer_enabled.setChecked(bool(self.cfg.get("cash_drawer_enabled", False)))
        self.drawer_sequence = QtWidgets.QLineEdit(self.cfg.get("cash_drawer_pulse_bytes", "\\x1B\\x70\\x00\\x19\\xFA"))
        self.test_drawer_btn = QtWidgets.QPushButton("Probar apertura")
        self.test_drawer_btn.clicked.connect(self._test_drawer)
        d_layout.addRow(self.drawer_enabled)
        d_layout.addRow("Secuencia ESC/POS", self.drawer_sequence)
        d_layout.addRow(self.test_drawer_btn)
        layout.addWidget(drawer_box)

        api_box = QtWidgets.QGroupBox("API Externa / Dashboard")
        api_layout = QtWidgets.QFormLayout(api_box)
        self.api_enabled = QtWidgets.QCheckBox("Permitir acceso API externo")
        self.api_enabled.setChecked(bool(self.cfg.get("api_external_enabled", False)))
        self.api_base_url = QtWidgets.QLineEdit(self.cfg.get("api_external_base_url", ""))
        self.api_token = QtWidgets.QLineEdit(self.cfg.get("api_dashboard_token", ""))
        self.api_token.setEchoMode(QtWidgets.QLineEdit.Password)
        self.generate_token_btn = QtWidgets.QPushButton("Generar token nuevo")
        self.generate_token_btn.clicked.connect(self._generate_token)
        self.api_warning = QtWidgets.QLabel("Se recomienda usar HTTPS y firewall al exponer la API.")
        self.api_warning.setStyleSheet("color:#e67e22; font-weight:600;")
        api_layout.addRow(self.api_enabled)
        api_layout.addRow("URL pública", self.api_base_url)
        api_layout.addRow("Token dashboard", self.api_token)
        api_layout.addRow(self.generate_token_btn)
        api_layout.addRow(self.api_warning)
        layout.addWidget(api_box)

        backup_box = QtWidgets.QGroupBox("Backups PRO")
        b_layout = QtWidgets.QFormLayout(backup_box)
        self.backup_auto = QtWidgets.QCheckBox("Hacer backup al cerrar turno")
        self.backup_auto.setChecked(bool(self.cfg.get("backup_auto_on_close", False)))
        self.backup_dir = QtWidgets.QLineEdit(self.cfg.get("backup_dir", str(DATA_DIR / "backups")))
        self.backup_encrypt = QtWidgets.QCheckBox("Cifrar con AES-256")
        self.backup_encrypt.setChecked(bool(self.cfg.get("backup_encrypt", False)))
        self.backup_key = QtWidgets.QLineEdit(self.cfg.get("backup_encrypt_key", ""))
        self.backup_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self.backup_nas_enabled = QtWidgets.QCheckBox("Enviar a NAS")
        self.backup_nas_enabled.setChecked(bool(self.cfg.get("backup_nas_enabled", False)))
        self.backup_nas_path = QtWidgets.QLineEdit(self.cfg.get("backup_nas_path", ""))
        self.test_nas_btn = QtWidgets.QPushButton("Probar NAS")
        self.test_nas_btn.clicked.connect(self._test_nas)
        self.backup_cloud_enabled = QtWidgets.QCheckBox("Enviar a nube S3")
        self.backup_cloud_enabled.setChecked(bool(self.cfg.get("backup_cloud_enabled", False)))
        self.s3_endpoint = QtWidgets.QLineEdit(self.cfg.get("backup_s3_endpoint", ""))
        self.s3_access = QtWidgets.QLineEdit(self.cfg.get("backup_s3_access_key", ""))
        self.s3_secret = QtWidgets.QLineEdit(self.cfg.get("backup_s3_secret_key", ""))
        self.s3_secret.setEchoMode(QtWidgets.QLineEdit.Password)
        self.s3_bucket = QtWidgets.QLineEdit(self.cfg.get("backup_s3_bucket", ""))
        self.s3_prefix = QtWidgets.QLineEdit(self.cfg.get("backup_s3_prefix", ""))
        self.test_s3_btn = QtWidgets.QPushButton("Probar nube")
        self.test_s3_btn.clicked.connect(self._test_s3)
        self.retention_enabled = QtWidgets.QCheckBox("Retención automática")
        self.retention_enabled.setChecked(bool(self.cfg.get("backup_retention_enabled", False)))
        self.retention_days = QtWidgets.QSpinBox()
        self.retention_days.setRange(1, 365)
        self.retention_days.setValue(int(self.cfg.get("backup_retention_days", 30)))
        self.restore_btn = QtWidgets.QPushButton("Restaurar backup…")
        self.restore_btn.clicked.connect(self._open_restore)
        b_layout.addRow(self.backup_auto)
        b_layout.addRow("Directorio local", self.backup_dir)
        b_layout.addRow(self.backup_encrypt)
        b_layout.addRow("Clave", self.backup_key)
        b_layout.addRow(self.backup_nas_enabled)
        b_layout.addRow("Ruta NAS", self.backup_nas_path)
        b_layout.addRow(self.test_nas_btn)
        b_layout.addRow(self.backup_cloud_enabled)
        b_layout.addRow("Endpoint", self.s3_endpoint)
        b_layout.addRow("Access key", self.s3_access)
        b_layout.addRow("Secret key", self.s3_secret)
        b_layout.addRow("Bucket", self.s3_bucket)
        b_layout.addRow("Prefix", self.s3_prefix)
        b_layout.addRow(self.test_s3_btn)
        b_layout.addRow(self.retention_enabled)
        b_layout.addRow("Días a conservar", self.retention_days)
        b_layout.addRow(self.restore_btn)
        layout.addWidget(backup_box)

        fiscal_box = QtWidgets.QGroupBox("Facturación CFDI 4.0")
        f_layout = QtWidgets.QFormLayout(fiscal_box)
        self.rfc_emisor = QtWidgets.QLineEdit(self.fiscal_cfg.get("rfc_emisor", ""))
        self.razon_emisor = QtWidgets.QLineEdit(self.fiscal_cfg.get("razon_social_emisor", ""))
        self.regimen_emisor = QtWidgets.QLineEdit(self.fiscal_cfg.get("regimen_fiscal", ""))
        self.lugar_expedicion = QtWidgets.QLineEdit(self.fiscal_cfg.get("lugar_expedicion", ""))
        self.csd_cert = QtWidgets.QLineEdit(self.fiscal_cfg.get("csd_cert_path", ""))
        self.csd_key = QtWidgets.QLineEdit(self.fiscal_cfg.get("csd_key_path", ""))
        self.csd_pass = QtWidgets.QLineEdit(self.fiscal_cfg.get("csd_key_password", ""))
        self.csd_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        self.pac_url = QtWidgets.QLineEdit(self.fiscal_cfg.get("pac_base_url", ""))
        self.pac_user = QtWidgets.QLineEdit(self.fiscal_cfg.get("pac_user", ""))
        self.pac_pass = QtWidgets.QLineEdit(self.fiscal_cfg.get("pac_password", ""))
        self.pac_pass.setEchoMode(QtWidgets.QLineEdit.Password)
        self.serie_factura = QtWidgets.QLineEdit(self.fiscal_cfg.get("serie_factura", "F"))
        self.folio_actual = QtWidgets.QSpinBox()
        self.folio_actual.setMaximum(999999)
        self.folio_actual.setValue(int(self.fiscal_cfg.get("folio_actual", 1)))
        self.test_fiscal_btn = QtWidgets.QPushButton("Probar configuración")
        self.test_fiscal_btn.clicked.connect(self._test_fiscal)
        f_layout.addRow("RFC Emisor", self.rfc_emisor)
        f_layout.addRow("Razón social", self.razon_emisor)
        f_layout.addRow("Régimen fiscal", self.regimen_emisor)
        f_layout.addRow("Lugar expedición (CP)", self.lugar_expedicion)
        f_layout.addRow("Certificado CSD (.cer)", self.csd_cert)
        f_layout.addRow("Llave CSD (.key)", self.csd_key)
        f_layout.addRow("Contraseña CSD", self.csd_pass)
        f_layout.addRow("PAC URL", self.pac_url)
        f_layout.addRow("PAC usuario", self.pac_user)
        f_layout.addRow("PAC password", self.pac_pass)
        f_layout.addRow("Serie", self.serie_factura)
        f_layout.addRow("Folio actual", self.folio_actual)
        f_layout.addRow(self.test_fiscal_btn)
        layout.addWidget(fiscal_box)

        save_btn = QtWidgets.QPushButton("Guardar configuración")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)
        layout.addStretch(1)

    # ------------------------------------------------------------------
    def _test_connection(self) -> None:
        url = f"http://{self.server_ip.text().strip()}:{self.server_port.value()}"
        client = NetworkClient(url)
        ok = client.ping()
        if ok:
            self.status_lbl.setText("Conectado")
            self.status_lbl.setStyleSheet("color: #2ecc71; font-weight: 700;")
        else:
            self.status_lbl.setText("Offline")
            self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: 700;")

    def _apply_theme(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        selected = self.theme_combo.currentText()
        theme_manager.apply_theme(app, selected)  # type: ignore[arg-type]
        cfg = self.core.read_config()
        cfg["theme"] = selected
        self.core.write_config(cfg)

    def _save(self) -> None:
        cfg = self.core.read_config()
        cfg.update(
            {
                "mode": self.mode_combo.currentText(),
                "server_ip": self.server_ip.text().strip(),
                "server_port": self.server_port.value(),
                "sync_interval_seconds": self.sync_interval.value(),
                "theme": self.theme_combo.currentText(),
                "scanner_prefix": self.prefix_input.text(),
                "scanner_suffix": self.suffix_input.text(),
                "camera_scanner_enabled": self.camera_enabled.isChecked(),
                "camera_scanner_index": self.camera_index.value(),
                "printer_name": self.printer_name.text().strip(),
                "ticket_paper_width": self.paper_width.currentText(),
                "auto_print_tickets": self.auto_print.isChecked(),
                "cash_drawer_enabled": self.drawer_enabled.isChecked(),
                "cash_drawer_pulse_bytes": self.drawer_sequence.text().strip() or "\\x1B\\x70\\x00\\x19\\xFA",
                "api_external_enabled": self.api_enabled.isChecked(),
                "api_external_base_url": self.api_base_url.text().strip(),
                "api_dashboard_token": self.api_token.text().strip(),
                "backup_auto_on_close": self.backup_auto.isChecked(),
                "backup_dir": self.backup_dir.text().strip() or str(DATA_DIR / "backups"),
                "backup_encrypt": self.backup_encrypt.isChecked(),
                "backup_encrypt_key": self.backup_key.text().strip(),
                "backup_nas_enabled": self.backup_nas_enabled.isChecked(),
                "backup_nas_path": self.backup_nas_path.text().strip(),
                "backup_cloud_enabled": self.backup_cloud_enabled.isChecked(),
                "backup_s3_endpoint": self.s3_endpoint.text().strip(),
                "backup_s3_access_key": self.s3_access.text().strip(),
                "backup_s3_secret_key": self.s3_secret.text().strip(),
                "backup_s3_bucket": self.s3_bucket.text().strip(),
                "backup_s3_prefix": self.s3_prefix.text().strip(),
                "backup_retention_enabled": self.retention_enabled.isChecked(),
                "backup_retention_days": self.retention_days.value(),
            }
        )
        self.core.write_config(cfg)
        self.core.update_fiscal_config(
            {
                "rfc_emisor": self.rfc_emisor.text().strip(),
                "razon_social_emisor": self.razon_emisor.text().strip(),
                "regimen_fiscal": self.regimen_emisor.text().strip(),
                "lugar_expedicion": self.lugar_expedicion.text().strip(),
                "csd_cert_path": self.csd_cert.text().strip(),
                "csd_key_path": self.csd_key.text().strip(),
                "csd_key_password": self.csd_pass.text().strip(),
                "pac_base_url": self.pac_url.text().strip(),
                "pac_user": self.pac_user.text().strip(),
                "pac_password": self.pac_pass.text().strip(),
                "serie_factura": self.serie_factura.text().strip() or "F",
                "folio_actual": self.folio_actual.value(),
            }
        )
        QtWidgets.QMessageBox.information(self, "Configuración", "Guardado")

    def _test_print(self) -> None:
        lines = ["PRUEBA DE IMPRESIÓN", datetime.now().strftime("%Y-%m-%d %H:%M")]
        ticket_engine.print_ticket("\n".join(lines), self.printer_name.text().strip() or None)
        QtWidgets.QMessageBox.information(self, "Impresión", "Ticket de prueba enviado")

    def _test_drawer(self) -> None:
        printer = self.printer_name.text().strip()
        if not printer:
            QtWidgets.QMessageBox.warning(self, "Cajón", "Define una impresora primero")
            return
        pulse_str = self.drawer_sequence.text().strip() or "\\x1B\\x70\\x00\\x19\\xFA"
        try:
            pulse_bytes = bytes(pulse_str, "utf-8").decode("unicode_escape").encode("latin1")
            ticket_engine.open_cash_drawer(printer, pulse_bytes)
            QtWidgets.QMessageBox.information(self, "Cajón", "Comando enviado")
        except Exception:  # noqa: BLE001
            logging.exception("No se pudo probar el cajón")
            QtWidgets.QMessageBox.critical(self, "Cajón", "Error al enviar pulso")

    def _generate_token(self) -> None:
        new_token = secrets.token_urlsafe(32)
        self.api_token.setText(new_token)

    def _test_nas(self) -> None:
        dlg = BackupSettingsTestDialog("nas", {"path": self.backup_nas_path.text().strip()}, self)
        dlg.exec()

    def _test_s3(self) -> None:
        dlg = BackupSettingsTestDialog(
            "s3",
            {
                "endpoint_url": self.s3_endpoint.text().strip(),
                "access_key": self.s3_access.text().strip(),
                "secret_key": self.s3_secret.text().strip(),
                "bucket": self.s3_bucket.text().strip(),
            },
            self,
        )
        dlg.exec()

    def _test_fiscal(self) -> None:
        missing = []
        if not Path(self.csd_cert.text().strip()).exists():
            missing.append("Certificado .cer")
        if not Path(self.csd_key.text().strip()).exists():
            missing.append("Llave .key")
        if not self.csd_pass.text().strip():
            missing.append("Contraseña CSD")
        if missing:
            QtWidgets.QMessageBox.warning(self, "Facturación", "Faltan datos: " + ", ".join(missing))
            return
        QtWidgets.QMessageBox.information(self, "Facturación", "Configuración fiscal validada")

    def _open_restore(self) -> None:
        dlg = BackupRestoreDialog(self.core, self)
        dlg.exec()

class POSWindow(QtWidgets.QMainWindow):
    def __init__(self, core: POSCore, *, mode: str = "server", network_client: NetworkClient | None = None):
        super().__init__()
        self.core = core
        self.mode = mode
        self.network_client = network_client
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1200, 720)
        self.current_turn_id: int | None = None
        self.connection_label = QtWidgets.QLabel()
        cfg = self.core.get_app_config()
        self.backup_engine = BackupEngine(self.core, cfg.get("backup_dir"))
        self._build_ui()
        self._ensure_turn()
        if self.mode == "server":
            self._start_embedded_server()
        if self.mode == "client":
            self._start_connectivity_monitor()

    def _build_ui(self) -> None:
        tabs = QtWidgets.QTabWidget()
        icon = QtGui.QIcon
        self.sales_tab = SalesTab(self.core, mode=self.mode, network_client=self.network_client)
        tabs.addTab(self.sales_tab, icon(str(ICON_DIR / "sales.png")), "Ventas")
        tabs.addTab(ProductsTab(self.core), icon(str(ICON_DIR / "inventory.png")), "Productos")
        tabs.addTab(InventoryTab(self.core), icon(str(ICON_DIR / "inventory.png")), "Inventario")
        self.customers_tab = CustomersTab(self.core)
        tabs.addTab(self.customers_tab, icon(str(ICON_DIR / "customers.png")), "Clientes")
        tabs.addTab(HistoryTab(self.core), icon(str(ICON_DIR / "reports.png")), "Historial")
        tabs.addTab(LayawaysTab(self.core), icon(str(ICON_DIR / "cash.png")), "Apartados")
        tabs.addTab(TurnTab(self.core, backup_engine=self.backup_engine), icon(str(ICON_DIR / "cash.png")), "Turno / Caja")
        tabs.addTab(ReportsTab(self.core), icon(str(ICON_DIR / "reports.png")), "Reportes")
        tabs.addTab(SettingsTab(self.core), icon(str(ICON_DIR / "settings.png")), "Configuración")
        self.tabs = tabs
        self.setCentralWidget(tabs)
        self.statusBar().showMessage(f"Sucursal activa: {STATE.branch_id}")
        self.statusBar().addPermanentWidget(self.connection_label)
        QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_F2), self, self._focus_customers_tab)

        toolbar = self.addToolBar("Turnos")
        cash_in_action = QtGui.QAction("Entrada (F7)", self)
        cash_in_action.triggered.connect(lambda: tabs.widget(0)._cash_in())
        cash_out_action = QtGui.QAction("Salida (F8)", self)
        cash_out_action.triggered.connect(lambda: tabs.widget(0)._cash_out())
        close_turn_action = QtGui.QAction("Cerrar turno", self)
        close_turn_action.triggered.connect(self._close_turn)
        toolbar.addAction(cash_in_action)
        toolbar.addAction(cash_out_action)
        toolbar.addAction(close_turn_action)

    def _focus_customers_tab(self) -> None:
        if hasattr(self, "sales_tab") and self.tabs.currentWidget() is self.sales_tab:
            return
        if hasattr(self, "customers_tab"):
            self.tabs.setCurrentWidget(self.customers_tab)
            self.customers_tab.table.setFocus()

    def _start_embedded_server(self) -> None:
        try:
            threading.Thread(target=lambda: __import__("server_main").run_api(), daemon=True).start()
            self.connection_label.setText("Servidor local")
            self.connection_label.setStyleSheet("color: #2ecc71; font-weight: 700;")
        except Exception:
            self.connection_label.setText("API no inició")
            self.connection_label.setStyleSheet("color: #e67e22; font-weight: 700;")

    def _start_connectivity_monitor(self) -> None:
        self._update_connection_label(False)
        self.sync_timer = QtCore.QTimer(self)
        self.sync_timer.timeout.connect(self._check_connectivity)
        self.sync_timer.start(8000)

    def _update_connection_label(self, ok: bool) -> None:
        if ok:
            self.connection_label.setText("Conectado")
            self.connection_label.setStyleSheet("color: #2ecc71; font-weight: 700;")
        else:
            self.connection_label.setText("Offline")
            self.connection_label.setStyleSheet("color: #e74c3c; font-weight: 700;")

    def _check_connectivity(self) -> None:
        if not self.network_client:
            return
        ok = self.network_client.ping()
        self._update_connection_label(ok)
        if hasattr(self, "sales_tab"):
            self.sales_tab._set_offline(not ok)
        if ok and hasattr(self, "sales_tab"):
            self.sales_tab.sync_offline_sales()

    def _ensure_turn(self) -> None:
        existing = self.core.get_current_turn(STATE.branch_id, STATE.user_id)
        if existing:
            self.current_turn_id = existing["id"]
            return
        if not permissions.can_open_turn():
            return
        dlg = TurnOpenDialog(STATE.username or "Usuario", self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.result_data:
            try:
                self.current_turn_id = self.core.open_turn(
                    STATE.branch_id, STATE.user_id, dlg.result_data["opening_amount"], dlg.result_data.get("notes")
                )
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.critical(self, "Turno", str(exc))

    def _close_turn(self) -> None:
        if not permissions.can_close_turn():
            QtWidgets.QMessageBox.warning(self, "Permisos", "No puedes cerrar turno")
            return
        turn = self.core.get_current_turn(STATE.branch_id, STATE.user_id)
        if not turn:
            QtWidgets.QMessageBox.information(self, "Turno", "No hay turno abierto")
            return
        summary = self.core.get_turn_summary(turn["id"])
        dlg = TurnCloseDialog(summary, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted and dlg.result_data:
            try:
                self.core.close_turn(turn["id"], dlg.result_data["closing_amount"], dlg.result_data.get("notes"))
                if self.backup_engine:
                    self.backup_engine.auto_backup_flow()
                QtWidgets.QMessageBox.information(self, "Turno", "Turno cerrado")
            except Exception as exc:  # noqa: BLE001
                QtWidgets.QMessageBox.critical(self, "Error", str(exc))


class WelcomeWizard(QtWidgets.QWizard):
    """Placeholder wizard to flip setup flag until the full flow arrives."""

    def __init__(self, core: POSCore):
        super().__init__()
        self.core = core
        self.setWindowTitle("Asistente de Bienvenida")
        self.addPage(self._intro())
        self.addPage(self._finish())

    def _intro(self) -> QtWidgets.QWizardPage:
        page = QtWidgets.QWizardPage()
        page.setTitle("Bienvenido")
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Configura el POS antes de comenzar."))
        return page

    def _finish(self) -> QtWidgets.QWizardPage:
        page = QtWidgets.QWizardPage()
        page.setTitle("Listo")
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel("Pulsa Finalizar para continuar"))
        return page

    def accept(self) -> None:  # type: ignore[override]
        cfg = self.core.read_config()
        cfg["setup_completed"] = True
        self.core.write_config(cfg)
        super().accept()


# ---------------------------------------------------------------------------
# Utilities

def run_app(
    core: POSCore,
    *,
    mode: str = "server",
    network_client: NetworkClient | None = None,
    theme_name: str = "Light",
) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    theme_manager.apply_theme(app, theme_name)  # type: ignore[arg-type]
    window = POSWindow(core, mode=mode, network_client=network_client)
    window.show()
    fade_in(window)
    sys.exit(app.exec())


def run_wizard(
    core: POSCore,
    *,
    mode: str = "server",
    network_client: NetworkClient | None = None,
    theme_name: str = "Light",
) -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create("Fusion"))
    theme_manager.apply_theme(app, theme_name)  # type: ignore[arg-type]
    wizard = WelcomeWizard(core)
    fade_in(wizard)
    if wizard.exec() == QtWidgets.QDialog.DialogCode.Accepted:
        run_app(core, mode=mode, network_client=network_client, theme_name=theme_name)


def main() -> None:
    initialize_pos_env.ensure_directories()
    initialize_pos_env.initialize_database()
    core = POSCore()
    cfg = core.read_config()
    mode = cfg.get("mode", "server")
    network_client = None
    if mode == "client":
        server_url = f"http://{cfg.get('server_ip', '127.0.0.1')}:{cfg.get('server_port', 8000)}"
        network_client = MultiCajaClient(server_url, token=cfg.get("sync_token"))
    if cfg.get("setup_completed"):
        run_app(core, mode=mode, network_client=network_client, theme_name=cfg.get("theme", "Light"))
    else:
        run_wizard(core, mode=mode, network_client=network_client, theme_name=cfg.get("theme", "Light"))


if __name__ == "__main__":
    main()
