from __future__ import annotations

from PySide6 import QtCore, QtWidgets


def fade_in(widget: QtWidgets.QWidget, duration: int = 180) -> None:
    effect = QtWidgets.QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QtCore.QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def fade_out(widget: QtWidgets.QWidget, duration: int = 180) -> None:
    effect = QtWidgets.QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    animation = QtCore.QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(1.0)
    animation.setEndValue(0.0)
    animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def slide_in_from_right(widget: QtWidgets.QWidget, distance: int = 30, duration: int = 200) -> None:
    start = widget.pos() + QtCore.QPoint(distance, 0)
    end = widget.pos()
    animation = QtCore.QPropertyAnimation(widget, b"pos", widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
    animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def slide_up(widget: QtWidgets.QWidget, distance: int = 24, duration: int = 200) -> None:
    start = widget.pos() + QtCore.QPoint(0, distance)
    end = widget.pos()
    animation = QtCore.QPropertyAnimation(widget, b"pos", widget)
    animation.setDuration(duration)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
    animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
