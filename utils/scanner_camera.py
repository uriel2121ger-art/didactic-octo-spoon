"""Camera barcode scanner thread using OpenCV + pyzbar."""
from __future__ import annotations

import logging
from typing import Optional

import cv2
from PySide6 import QtCore
from pyzbar import pyzbar

logger = logging.getLogger(__name__)


class CameraScannerThread(QtCore.QThread):
    """Scan barcodes from a camera feed in a background thread."""

    code_detected = QtCore.Signal(str)

    def __init__(self, camera_index: int = 0, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = False

    def run(self) -> None:  # pragma: no cover - hardware dependent
        self._running = True
        try:
            cap = cv2.VideoCapture(self.camera_index)
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo abrir la cámara")
            return
        if not cap or not cap.isOpened():
            logger.error("Cámara no disponible en índice %s", self.camera_index)
            return
        while self._running:
            ret, frame = cap.read()
            if not ret:
                continue
            try:
                decoded = pyzbar.decode(frame)
            except Exception:  # noqa: BLE001
                logger.exception("Error decodificando código de barras")
                decoded = []
            for obj in decoded:
                data = obj.data.decode("utf-8", errors="ignore").strip()
                if data:
                    self.code_detected.emit(data)
                    self._running = False
                    break
        try:
            cap.release()
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo liberar la cámara")

    def stop(self) -> None:
        self._running = False
