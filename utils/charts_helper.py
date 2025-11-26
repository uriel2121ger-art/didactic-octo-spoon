"""Utility helpers to quickly build QtCharts charts for reports."""
from __future__ import annotations

from typing import Iterable, Sequence

from PySide6 import QtCharts, QtCore


def make_bar_chart(title: str, categories: Sequence[str], values: Sequence[float]) -> QtCharts.QChart:
    series = QtCharts.QBarSeries()
    bar_set = QtCharts.QBarSet(title)
    for v in values:
        bar_set.append(float(v or 0))
    series.append(bar_set)

    axis_x = QtCharts.QBarCategoryAxis()
    axis_x.append(list(categories))

    chart = QtCharts.QChart()
    chart.addSeries(series)
    chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(axis_x)
    chart.createDefaultAxes()
    chart.setTitle(title)
    chart.legend().setVisible(False)
    chart.setAnimationOptions(QtCharts.QChart.AnimationOption.SeriesAnimations)
    chart.setTheme(QtCharts.QChart.ChartTheme.ChartThemeLight)
    return chart


def make_line_chart(title: str, x_labels: Sequence[str], values: Sequence[float]) -> QtCharts.QChart:
    series = QtCharts.QLineSeries()
    for idx, value in enumerate(values):
        series.append(idx, float(value or 0))

    axis_x = QtCharts.QCategoryAxis()
    for idx, label in enumerate(x_labels):
        axis_x.append(label, idx)
    axis_x.setLabelsPosition(QtCharts.QCategoryAxis.AxisLabelsPosition.AxisLabelsPositionOnValue)

    chart = QtCharts.QChart()
    chart.addSeries(series)
    chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(axis_x)
    chart.createDefaultAxes()
    chart.setTitle(title)
    chart.legend().setVisible(False)
    chart.setAnimationOptions(QtCharts.QChart.AnimationOption.SeriesAnimations)
    chart.setTheme(QtCharts.QChart.ChartTheme.ChartThemeLight)
    return chart


def make_pie_chart(title: str, labels: Iterable[str], values: Iterable[float]) -> QtCharts.QChart:
    series = QtCharts.QPieSeries()
    for label, value in zip(labels, values):
        series.append(str(label), float(value or 0))

    chart = QtCharts.QChart()
    chart.addSeries(series)
    chart.setTitle(title)
    chart.legend().setVisible(True)
    chart.legend().setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
    chart.setAnimationOptions(QtCharts.QChart.AnimationOption.SeriesAnimations)
    chart.setTheme(QtCharts.QChart.ChartTheme.ChartThemeLight)
    return chart
