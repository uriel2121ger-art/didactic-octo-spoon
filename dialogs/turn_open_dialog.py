from __future__ import annotations

from PySide6 import QtWidgets

from utils.animations import fade_in


class TurnOpenDialog(QtWidgets.QDialog):
    def __init__(self, user_name: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Abrir turno")
        self.result_data: dict | None = None
        self.user_name = user_name
        self._build_ui()
        fade_in(self)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Abrir turno")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        form = QtWidgets.QFormLayout()
        form.addRow("Usuario:", QtWidgets.QLabel(self.user_name))
        self.opening = QtWidgets.QDoubleSpinBox()
        self.opening.setRange(0, 1_000_000)
        self.opening.setDecimals(2)
        self.opening.setPrefix("$ ")
        form.addRow("Fondo inicial:", self.opening)
        self.notes = QtWidgets.QLineEdit()
        form.addRow("Notas:", self.notes)
        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:  # type: ignore[override]
        if self.opening.value() < 0:
            QtWidgets.QMessageBox.warning(self, "Cantidad inválida", "El fondo inicial no puede ser negativo")
            return
        self.result_data = {"opening_amount": float(self.opening.value()), "notes": self.notes.text().strip()}
        super().accept()
