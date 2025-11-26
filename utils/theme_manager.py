from __future__ import annotations

from pathlib import Path
from typing import Literal

from PySide6 import QtGui, QtWidgets

ThemeName = Literal["Light", "Dark", "AMOLED", "Pastel", "RosaLupita"]


class ThemeManager:
    """Apply KDE/Material-inspired themes with palette + QSS."""

    def __init__(self, assets_dir: Path | None = None) -> None:
        self.assets_dir = assets_dir or Path(__file__).resolve().parent.parent / "assets"
        self.qss_dir = self.assets_dir / "qss"
        self.current_theme: ThemeName = "Light"

    # ------------------------------------------------------------------
    def apply_theme(self, app: QtWidgets.QApplication, theme_name: ThemeName) -> None:
        palette = self._palette_for(theme_name)
        app.setPalette(palette)
        stylesheet = self.generate_global_qss(theme_name)
        app.setStyleSheet(stylesheet)
        self.current_theme = theme_name

    def generate_global_qss(self, theme_name: ThemeName) -> str:
        base = self._load_qss("base.qss")
        mapping = {
            "Light": "light.qss",
            "Dark": "dark.qss",
            "AMOLED": "amoled.qss",
            "Pastel": "pastel.qss",
            "RosaLupita": "rosa_lupita.qss",
        }
        themed = self._load_qss(mapping.get(theme_name, "light.qss"))
        return base + "\n" + themed

    def load_palette_light(self) -> QtGui.QPalette:
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#f6f8fb"))
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#1c2833"))
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#ffffff"))
        pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#f0f3f8"))
        pal.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#e7ecf3"))
        pal.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#1c2833"))
        pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#2b8be6"))
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
        return pal

    def load_palette_dark(self) -> QtGui.QPalette:
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#1f252b"))
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#ecf0f1"))
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#252b33"))
        pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#2c343c"))
        pal.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#2c343c"))
        pal.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#ecf0f1"))
        pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#3498db"))
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
        return pal

    def load_palette_amoled(self) -> QtGui.QPalette:
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#000000"))
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#e6e6e6"))
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#0b1118"))
        pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#121922"))
        pal.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#0f1720"))
        pal.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#e6e6e6"))
        pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#1f3a60"))
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
        return pal

    def load_palette_pastel(self) -> QtGui.QPalette:
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#fdf7ff"))
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#2d3436"))
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#ffffff"))
        pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#f6edff"))
        pal.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#f2e7ff"))
        pal.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#2d3436"))
        pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#8e44ad"))
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
        return pal

    def load_palette_rosa_lupita(self) -> QtGui.QPalette:
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#fff0f6"))
        pal.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#3b1f2b"))
        pal.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#ffffff"))
        pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#ffe4f2"))
        pal.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#ffcfe5"))
        pal.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#3b1f2b"))
        pal.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#ff5fa2"))
        pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#ffffff"))
        return pal

    # ------------------------------------------------------------------
    def _palette_for(self, theme: ThemeName) -> QtGui.QPalette:
        if theme == "Dark":
            return self.load_palette_dark()
        if theme == "AMOLED":
            return self.load_palette_amoled()
        if theme == "Pastel":
            return self.load_palette_pastel()
        if theme == "RosaLupita":
            return self.load_palette_rosa_lupita()
        return self.load_palette_light()

    def _load_qss(self, filename: str) -> str:
        path = self.qss_dir / filename
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""


theme_manager = ThemeManager()
