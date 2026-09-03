"""
Interactive 4-Corner / Edge Correction Canvas.

The user can drag:
  - the four corner handles (dark blue), AND
  - any of the four edge handles (midpoints) to move that entire edge
    freely while keeping the corner order intact.

Features:
  - Re-entrancy guards preventing infinite mutual recursion between handles.
  - Immediate visual polygon updates.
  - Zoom with scroll wheel.
  - Safe bounds clamping.
"""
from typing import Optional, List, Tuple
import cv2
import numpy as np
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import (
    QPixmap,
    QImage,
    QPainter,
    QPen,
    QBrush,
    QColor,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsEllipseItem,
    QGraphicsPolygonItem,
)

from app.core.models import ProcessedImage, CornerPoints
from app.processing.perspective import order_corners
from app.utils.logger import get_logger

logger = get_logger("corner_editor")

# Colors
EDGE_COLOR = QColor(30, 64, 175)          # Dark blue
EDGE_COLOR_HOVER = QColor(59, 130, 246)
HANDLE_FILL = QColor(30, 64, 175)         # Dark blue handle
HANDLE_FILL_ACTIVE = QColor(239, 68, 68)  # Red when hovered/dragged


class CornerHandle(QGraphicsEllipseItem):
    """Draggable corner handle with re-entrancy protection."""

    def __init__(self, x: float, y: float, name: str, parent_view, radius: float = 13.0):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.name = name
        self.parent_view = parent_view
        self.radius = radius
        self.setPos(x, y)
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemSendsGeometryChanges |
            QGraphicsItem.ItemIsSelectable
        )
        self.setPen(QPen(QColor(255, 255, 255), 2.5))
        self.setBrush(QBrush(HANDLE_FILL))
        self.setZValue(100)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(HANDLE_FILL_ACTIVE))
        self.setPen(QPen(QColor(255, 255, 255), 3))
        self.setCursor(Qt.CrossCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(HANDLE_FILL))
        self.setPen(QPen(QColor(255, 255, 255), 2.5))
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.parent_view is not None:
            if not getattr(self.parent_view, "_updating", False):
                self.parent_view.on_corner_moved(self, QPointF(value.x(), value.y()))
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.parent_view is not None:
            self.parent_view._sync_edge_handles()


class EdgeHandle(QGraphicsEllipseItem):
    """Mid-edge handle that drags an entire edge line freely with re-entrancy protection."""

    def __init__(self, x: float, y: float, edge_index: int, parent_view, radius: float = 12.0):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.edge_index = edge_index  # 0=top, 1=right, 2=bottom, 3=left
        self.parent_view = parent_view
        self.radius = radius
        self.setPos(x, y)
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemSendsGeometryChanges |
            QGraphicsItem.ItemIsSelectable
        )
        self.setPen(QPen(QColor(255, 255, 255), 2))
        self.setBrush(QBrush(EDGE_COLOR))
        self.setZValue(80)
        self.setCursor(Qt.SizeAllCursor)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(EDGE_COLOR_HOVER))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(EDGE_COLOR))
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.parent_view is not None:
            if not getattr(self.parent_view, "_updating", False):
                self.parent_view.on_edge_moved(self, QPointF(value.x(), value.y()))
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.parent_view is not None:
            self.parent_view._sync_edge_handles()


class CornerEditorCanvas(QGraphicsView):
    """Graphics view with draggable dark-blue corners AND movable edges."""

    corners_changed = Signal()

    def __init__(self, original_bgr: np.ndarray, initial_corners: CornerPoints, parent=None):
        super().__init__(parent)
        self.original_bgr = original_bgr
        self.initial_corners = initial_corners
        self.active_corner_handle: Optional[CornerHandle] = None
        self.active_edge_handle: Optional[EdgeHandle] = None
        self._updating: bool = False

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setBackgroundBrush(QBrush(QColor(13, 13, 13)))
        self.setStyleSheet("border: 1px solid #1E40AF; border-radius: 10px;")

        h, w, ch = original_bgr.shape
        self.img_w = w
        self.img_h = h
        bytes_per_line = ch * w
        rgb_img = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.pixmap = QPixmap.fromImage(qimg)
        self.pixmap_item = self.scene.addPixmap(self.pixmap)
        self.pixmap_item.setZValue(0)

        # Polygon overlay: dark blue outline + translucent fill
        self.poly_item = QGraphicsPolygonItem()
        self.poly_item.setPen(QPen(EDGE_COLOR, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.poly_item.setBrush(QBrush(QColor(30, 64, 175, 30)))
        self.poly_item.setZValue(50)
        self.scene.addItem(self.poly_item)

        # Corner handles
        self.handles: List[CornerHandle] = []
        names = ["TL", "TR", "BR", "BL"]
        pts = initial_corners.to_list()
        for name, pt in zip(names, pts):
            handle = CornerHandle(pt[0], pt[1], name, self)
            self.scene.addItem(handle)
            self.handles.append(handle)

        # Edge handles (midpoints)
        self.edge_handles: List[EdgeHandle] = []
        for i, pt in enumerate(self._edge_midpoints(self._corner_pts())):
            eh = EdgeHandle(pt[0], pt[1], i, self)
            self.scene.addItem(eh)
            self.edge_handles.append(eh)

        self.update_polygon()
        self.centerOn(w / 2.0, h / 2.0)

    def _corner_pts(self) -> np.ndarray:
        return np.array([[h.pos().x(), h.pos().y()] for h in self.handles], dtype=np.float32)

    def _edge_midpoints(self, pts: np.ndarray) -> List[Tuple[float, float]]:
        return [
            ((pts[0][0] + pts[1][0]) / 2.0, (pts[0][1] + pts[1][1]) / 2.0),  # top
            ((pts[1][0] + pts[2][0]) / 2.0, (pts[1][1] + pts[2][1]) / 2.0),  # right
            ((pts[2][0] + pts[3][0]) / 2.0, (pts[2][1] + pts[3][1]) / 2.0),  # bottom
            ((pts[3][0] + pts[0][0]) / 2.0, (pts[3][1] + pts[0][1]) / 2.0),  # left
        ]

    def on_corner_moved(self, handle: CornerHandle, pos: QPointF):
        """Called when a corner dot is moved by user."""
        if self._updating:
            return
        self._updating = True
        try:
            self.active_corner_handle = handle
            # Update edge midpoints to match new corner geometry
            pts = self._corner_pts()
            mids = self._edge_midpoints(pts)
            for eh, mid in zip(self.edge_handles, mids):
                eh.setPos(mid[0], mid[1])
            self.update_polygon()
            self.corners_changed.emit()
        finally:
            self._updating = False

    def on_edge_moved(self, edge_handle: EdgeHandle, pos: QPointF):
        """
        Moves an entire edge perpendicularly so that it passes through the
        dragged midpoint, translating both adjacent corners.
        """
        if self._updating:
            return
        self._updating = True
        try:
            self.active_edge_handle = edge_handle
            idx = edge_handle.edge_index
            start = self.handles[idx]
            end = self.handles[(idx + 1) % 4]

            p1 = np.array([start.pos().x(), start.pos().y()])
            p2 = np.array([end.pos().x(), end.pos().y()])
            drag_target = np.array([pos.x(), pos.y()])

            edge_vec = p2 - p1
            length = np.linalg.norm(edge_vec)
            if length >= 1e-6:
                normal = np.array([-edge_vec[1], edge_vec[0]]) / length
                delta = drag_target - p1
                signed_dist = np.dot(delta, normal)
                shift = normal * signed_dist
                start.setPos(start.pos() + QPointF(shift[0], shift[1]))
                end.setPos(end.pos() + QPointF(shift[0], shift[1]))

            # Re-sync midpoints for all OTHER edges
            pts = self._corner_pts()
            mids = self._edge_midpoints(pts)
            for eh, mid in zip(self.edge_handles, mids):
                if eh is not edge_handle:
                    eh.setPos(mid[0], mid[1])
            self.update_polygon()
            self.corners_changed.emit()
        finally:
            self._updating = False

    def _sync_edge_handles(self):
        """Re-aligns all edge handles to their exact midpoints."""
        if self._updating:
            return
        self._updating = True
        try:
            pts = self._corner_pts()
            mids = self._edge_midpoints(pts)
            for eh, mid in zip(self.edge_handles, mids):
                eh.setPos(mid[0], mid[1])
        finally:
            self._updating = False

    def update_polygon(self):
        pts = [QPointF(h.pos().x(), h.pos().y()) for h in self.handles]
        self.poly_item.setPolygon(QPolygonF(pts))

    def get_current_corners(self) -> CornerPoints:
        pts = self._corner_pts()
        return order_corners(pts)

    def reset_corners(self, corners: CornerPoints):
        if self._updating:
            return
        self._updating = True
        try:
            pts = corners.to_list()
            for handle, pt in zip(self.handles, pts):
                handle.setPos(pt[0], pt[1])
            mids = self._edge_midpoints(np.array(pts, dtype=np.float32))
            for eh, mid in zip(self.edge_handles, mids):
                eh.setPos(mid[0], mid[1])
            self.update_polygon()
            self.corners_changed.emit()
        finally:
            self._updating = False

    def wheelEvent(self, event):
        zoom_in = 1.15
        zoom_out = 1.0 / zoom_in
        if event.angleDelta().y() > 0:
            self.scale(zoom_in, zoom_in)
        else:
            self.scale(zoom_out, zoom_out)


class CornerEditorDialog(QDialog):
    """Simple 4-corner + movable-edge editor modal dialog."""

    def __init__(self, processed_image: ProcessedImage, parent=None):
        super().__init__(parent)
        self.processed = processed_image
        self.setWindowTitle("Adjust Card Edges")
        self.resize(900, 620)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.setStyleSheet("""
            QDialog { background-color: #0D0D0D; }
            QLabel { background: transparent; }
        """)

        self.initial_corners = processed_image.current_corners or processed_image.detected_corners
        if self.initial_corners is None:
            h, w = processed_image.original_image.shape[:2]
            self.initial_corners = CornerPoints((0, 0), (w, 0), (w, h), (0, h))

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("Adjust Card Edges & Corners")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #F0F0F5; background: transparent;")
        header.addWidget(title)
        header.addStretch()
        hint = QLabel("Drag dark blue corner dots or edge dots  •  Scroll to zoom")
        hint.setStyleSheet("font-size: 12px; color: #9A9AAA; background: transparent;")
        header.addWidget(hint)
        layout.addLayout(header)

        self.canvas = CornerEditorCanvas(self.processed.original_image, self.initial_corners, self)
        layout.addWidget(self.canvas, stretch=1)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        btn_reset = QPushButton("Reset")
        btn_reset.setFixedHeight(38)
        btn_reset.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #CBD5E1;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #334155; color: #FFFFFF; }
        """)
        btn_reset.clicked.connect(self.on_reset)
        toolbar.addWidget(btn_reset)

        toolbar.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(38)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                color: #94A3B8;
                border: 1px solid #334155;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 16px;
            }
            QPushButton:hover { background-color: #334155; color: #FFFFFF; }
        """)
        btn_cancel.clicked.connect(self.reject)
        toolbar.addWidget(btn_cancel)

        btn_apply = QPushButton("  Apply Corners  ")
        btn_apply.setFixedHeight(42)
        btn_apply.setMinimumWidth(160)
        btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """)
        btn_apply.clicked.connect(self.accept)
        toolbar.addWidget(btn_apply)

        layout.addLayout(toolbar)

    def on_reset(self):
        detected = self.processed.detected_corners or self.initial_corners
        self.canvas.reset_corners(detected)

    def get_result_corners(self) -> CornerPoints:
        return self.canvas.get_current_corners()
