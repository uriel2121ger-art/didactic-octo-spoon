from __future__ import annotations

import logging
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from utils.backup_engine import BackupEngine

logger = logging.getLogger(__name__)


class BackupRestoreDialog(QtWidgets.QDialog):
    def __init__(self, core, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Restaurar respaldo")
        self.core = core
        self.engine = BackupEngine(core)
        self.resize(640, 420)
        layout = QtWidgets.QVBoxLayout(self)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Archivo", "Fecha", "SHA256", "Tamaño", "Ubicaciones"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        form = QtWidgets.QFormLayout()
        self.key_input = QtWidgets.QLineEdit()
        self.key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("Clave de cifrado (opcional)", self.key_input)
        layout.addLayout(form)

        confirm_layout = QtWidgets.QHBoxLayout()
        confirm_layout.addWidget(QtWidgets.QLabel('Escribe "RESTAURAR" para confirmar'))
        self.confirm_edit = QtWidgets.QLineEdit()
        confirm_layout.addWidget(self.confirm_edit)
        layout.addLayout(confirm_layout)

        btns = QtWidgets.QDialogButtonBox()
        self.restore_btn = btns.addButton("Restaurar", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton("Cancelar", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self._restore)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._load_backups()

    def _load_backups(self) -> None:
        backups = self.core.list_backups()
        self.table.setRowCount(0)
        for row_data in backups:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(row_data["id"])))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(row_data["filename"]))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(row_data["created_at"]))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(row_data.get("sha256") or ""))
            self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(f"{row_data.get('size_bytes',0)} bytes"))
            locations = []
            if row_data.get("storage_local"):
                locations.append("Local")
            if row_data.get("storage_nas"):
                locations.append("NAS")
            if row_data.get("storage_cloud"):
                locations.append("Nube")
            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(", ".join(locations)))

    def _restore(self) -> None:
        if self.confirm_edit.text().strip().upper() != "RESTAURAR":
            QtWidgets.QMessageBox.warning(self, "Confirmación", "Escribe RESTAURAR para continuar")
            return
        row = self.table.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "Backup", "Selecciona un respaldo")
            return
        filename = self.table.item(row, 1).text()
        filepath = Path(self.engine.base_dir) / filename
        key = self.key_input.text().strip() or None
        try:
            self.engine.restore_backup(filepath, key)
            QtWidgets.QMessageBox.information(self, "Backup", "Restaurado correctamente. Reinicia la app.")
            self.accept()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error al restaurar backup")
            QtWidgets.QMessageBox.critical(self, "Backup", str(exc))
