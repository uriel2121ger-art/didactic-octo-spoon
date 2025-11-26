#!/usr/bin/env python3
"""Dialog to export report data to CSV, Excel, or PDF."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable, Iterable, List, Sequence

from PySide6 import QtWidgets
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

try:
    from openpyxl import Workbook
except Exception:  # noqa: BLE001
    Workbook = None


class ReportExportDialog(QtWidgets.QDialog):
    def __init__(
        self,
        title: str,
        headers: Sequence[str],
        rows: Iterable[Sequence],
        *,
        pdf_exporter: Callable[[str], None] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Exportar – {title}")
        self.headers = list(headers)
        self.rows = list(rows)
        self._pdf_exporter = pdf_exporter
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(["CSV", "Excel", "PDF"])
        form.addRow("Formato:", self.format_combo)

        path_layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        browse_btn = QtWidgets.QPushButton("Examinar…")
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_btn)
        form.addRow("Guardar como:", path_layout)
        layout.addLayout(form)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._export)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _browse(self) -> None:
        fmt = self.format_combo.currentText().lower()
        suffix = ".csv" if fmt == "csv" else ".xlsx" if fmt == "excel" else ".pdf"
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Selecciona archivo", str(Path.home()), f"*{suffix}")
        if filename:
            if not filename.lower().endswith(suffix):
                filename += suffix
            self.path_edit.setText(filename)

    def _export(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            QtWidgets.QMessageBox.warning(self, "Exportar", "Selecciona una ruta de destino")
            return
        fmt = self.format_combo.currentText().lower()
        try:
            if fmt == "csv":
                self._export_csv(path)
            elif fmt == "excel":
                self._export_excel(path)
            else:
                self._export_pdf(path)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Exportar", f"Error al exportar: {exc}")
            return
        QtWidgets.QMessageBox.information(self, "Exportar", "Exportación completada")
        self.accept()

    def _export_csv(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(self.headers)
            writer.writerows(self.rows)

    def _export_excel(self, path: str) -> None:
        if Workbook is None:
            raise RuntimeError("openpyxl no está disponible")
        wb = Workbook()
        ws = wb.active
        ws.append(list(self.headers))
        for row in self.rows:
            ws.append(list(row))
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)

    def _export_pdf(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if self._pdf_exporter:
            self._pdf_exporter(path)
            return
        doc = SimpleDocTemplate(path, pagesize=letter)
        data: List[List[str]] = [list(self.headers)] + [list(map(str, r)) for r in self.rows]
        table = Table(data)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        doc.build([table])
