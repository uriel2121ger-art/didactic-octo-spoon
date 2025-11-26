from __future__ import annotations

from PySide6 import QtWidgets

from utils.backup_engine import test_nas_access, test_s3_access


class BackupSettingsTestDialog(QtWidgets.QDialog):
    def __init__(self, mode: str, params: dict, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Prueba de conexión de backup")
        layout = QtWidgets.QVBoxLayout(self)
        self.result_label = QtWidgets.QLabel("Ejecutando...")
        layout.addWidget(self.result_label)
        self.resize(420, 160)
        QtWidgets.QApplication.processEvents()
        self._run_test(mode, params)

    def _run_test(self, mode: str, params: dict) -> None:
        if mode == "nas":
            ok, msg = test_nas_access(params.get("path", ""))
        else:
            ok, msg = test_s3_access(
                params.get("endpoint_url", ""),
                params.get("access_key", ""),
                params.get("secret_key", ""),
                params.get("bucket", ""),
            )
        if ok:
            self.result_label.setText(f"✅ Conexión exitosa: {msg}")
            self.result_label.setStyleSheet("color:#27ae60; font-weight:700;")
        else:
            self.result_label.setText(f"❌ Error: {msg}")
            self.result_label.setStyleSheet("color:#e74c3c; font-weight:700;")
