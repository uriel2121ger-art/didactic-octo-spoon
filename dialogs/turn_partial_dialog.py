from __future__ import annotations

from PySide6 import QtWidgets

from utils.animations import fade_in

from utils import ticket_engine


class TurnPartialDialog(QtWidgets.QDialog):
    def __init__(self, summary: dict[str, float], parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.summary = summary
        self.setWindowTitle("Corte parcial")
        self._build_ui()
        fade_in(self)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Corte parcial del turno")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        layout.addWidget(QtWidgets.QLabel(f"Fondo inicial: $ {self.summary.get('opening',0):.2f}"))
        layout.addWidget(QtWidgets.QLabel(f"Ventas efectivo: $ {self.summary.get('cash_sales',0):.2f}"))
        layout.addWidget(QtWidgets.QLabel(f"Ventas crédito: $ {self.summary.get('credit_sales',0):.2f}"))
        layout.addWidget(QtWidgets.QLabel(f"Abonos crédito: $ {self.summary.get('credit_payments',0):.2f}"))
        layout.addWidget(QtWidgets.QLabel(f"Abonos apartados: $ {self.summary.get('layaway_payments',0):.2f}"))
        layout.addWidget(QtWidgets.QLabel(f"Entradas: $ {self.summary.get('ins',0):.2f}"))
        layout.addWidget(QtWidgets.QLabel(f"Salidas: $ {self.summary.get('outs',0):.2f}"))
        layout.addWidget(QtWidgets.QLabel(f"Efectivo esperado: $ {self.summary.get('expected_cash',0):.2f}"))

        self.print_btn = QtWidgets.QPushButton("Imprimir corte parcial")
        self.print_btn.clicked.connect(self._print)
        close_btn = QtWidgets.QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.print_btn)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _print(self) -> None:
        ticket_engine.print_turn_partial(self.summary)
        QtWidgets.QMessageBox.information(self, "Corte", "Corte parcial enviado a impresión")
