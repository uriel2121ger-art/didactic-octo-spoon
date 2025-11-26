from __future__ import annotations

from PySide6 import QtWidgets

from utils.animations import fade_in

from utils import ticket_engine


class TurnCloseDialog(QtWidgets.QDialog):
    def __init__(self, summary: dict[str, float], parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Cerrar turno")
        self.summary = summary
        self.result_data: dict | None = None
        self._build_ui()
        fade_in(self)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Cierre de turno")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        self.expected_lbl = QtWidgets.QLabel(f"Total esperado: $ {self.summary.get('expected',0):.2f}")
        self.cash_sales_lbl = QtWidgets.QLabel(f"Ventas efectivo: $ {self.summary.get('cash_sales',0):.2f}")
        self.in_lbl = QtWidgets.QLabel(f"Entradas: $ {self.summary.get('ins',0):.2f}")
        self.out_lbl = QtWidgets.QLabel(f"Salidas: $ {self.summary.get('outs',0):.2f}")
        layout.addWidget(self.expected_lbl)
        layout.addWidget(self.cash_sales_lbl)
        layout.addWidget(self.in_lbl)
        layout.addWidget(self.out_lbl)

        form = QtWidgets.QFormLayout()
        self.count_spin = QtWidgets.QDoubleSpinBox()
        self.count_spin.setRange(0, 1_000_000)
        self.count_spin.setDecimals(2)
        self.count_spin.setPrefix("$ ")
        form.addRow("Conteo físico:", self.count_spin)
        self.notes = QtWidgets.QLineEdit()
        form.addRow("Notas:", self.notes)
        layout.addLayout(form)

        self.delta_lbl = QtWidgets.QLabel("Diferencia: $0.00")
        layout.addWidget(self.delta_lbl)
        self.count_spin.valueChanged.connect(self._update_delta)

        self.print_btn = QtWidgets.QPushButton("Imprimir corte")
        self.print_btn.clicked.connect(self._print_preview)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.print_btn)
        btn_layout.addWidget(btns)
        layout.addLayout(btn_layout)

    def _update_delta(self) -> None:
        diff = float(self.count_spin.value()) - float(self.summary.get("expected", 0))
        self.delta_lbl.setText(f"Diferencia: $ {diff:.2f}")

    def accept(self) -> None:  # type: ignore[override]
        self.result_data = {
            "closing_amount": float(self.count_spin.value()),
            "notes": self.notes.text().strip(),
        }
        super().accept()

    def _print_preview(self) -> None:
        ticket_engine.print_turn_close({**self.summary, "closing_amount": float(self.count_spin.value())})
        QtWidgets.QMessageBox.information(self, "Corte", "Corte final enviado a impresión")
