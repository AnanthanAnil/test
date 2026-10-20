from collections import deque
from PyQt6.QtWidgets import QWidget, QAbstractButton
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QPainterPath, QPen, QBrush

class LiveSmoothLineChart(QWidget):
    def __init__(self, parent=None, max_points=30, accent_color="#B2BEB5"):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.max_points = max_points
        self.data_history = deque([0.0] * max_points, maxlen=max_points)
        self.accent_color = QColor(accent_color)
        self.max_val = 100.0

    def add_data(self, value):
        self.data_history.append(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        if width == 0 or height == 0: return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0E0E10"))
        painter.drawRoundedRect(QRectF(0, 0, width, height), 8, 8)

        points = list(self.data_history)
        step_x = width / (self.max_points - 1) if self.max_points > 1 else width
        scaled_points = [QPointF(i * step_x, max(10, min(height - 10, height - ((val / self.max_val) * height)))) for i, val in enumerate(points)]
        if not scaled_points: return

        path = QPainterPath()
        path.moveTo(scaled_points[0])
        for i in range(len(scaled_points) - 1):
            p1, p2 = scaled_points[i], scaled_points[i+1]
            path.cubicTo(QPointF((p1.x() + p2.x())/2, p1.y()), QPointF((p1.x() + p2.x())/2, p2.y()), p2)

        pen = QPen(self.accent_color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPath(path)

class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None, on_color="#10b981", off_color="#374151"):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(40, 20)
        self.on_color, self.off_color = QColor(on_color), QColor(off_color)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.on_color if self.isChecked() else self.off_color)
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)
        knob = self.height() - 6
        x = self.width() - knob - 3 if self.isChecked() else 3
        painter.setBrush(QColor("#F3F4F6"))
        painter.drawEllipse(QRectF(x, 3, knob, knob))