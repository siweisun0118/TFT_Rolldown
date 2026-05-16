"""Layout-based UI for the rolldown.

This replaces the old fixed-geometry generated UI.  Everything is built with
Qt layouts and size policies so the window can be resized (never below its
original 1366x973 size) while keeping the relative size of every component.

Highlights:

* A single, narrow **trait column** on the left whose icons get a
  bronze/silver/gold/prismatic background based on the active breakpoint.
* A hexagonal **board** of 4 interlocking rows (A-D) x 7 columns (1-7).
* A square **bench** of 9 slots underneath the board.
* Drag-and-drop of units between board and bench, and dragging a unit onto the
  shop to sell it.
* A non-blocking, non-interactive transient message banner.
"""

# pylint: disable=no-name-in-module
import math

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QMimeData, QTimer
from PyQt5.QtGui import QDrag, QPainter, QPolygonF, QColor, QBrush, QPen

from shared.rolldown_enums import (
    BENCH_SLOTS, BOARD_COLS, BOARD_ROWS, GEN_ASSETS, SHOP_SLOTS,
)


def pathlib_path(root, ext):
    """Extend a Path and convert to string."""
    return str(root / ext)


# Minimum window size (the original hardcoded size).
MIN_WINDOW_W = 1366
MIN_WINDOW_H = 973

# Background tiers for trait icons.
TIER_COLORS = {
    'bronze': '#cd7f32',
    'silver': '#c0c0c0',
    'gold': '#ffd700',
    'prismatic': 'qlineargradient(x1:0, y1:0, x2:1, y2:1, '
                 'stop:0 #b9f2ff, stop:0.5 #f5c6ec, stop:1 #c1f7d5)',
    None: '#3a3a3a',
}


# Star-level border colours (bronze / silver / gold) so the current star
# level of a unit is obvious at a glance.
STAR_COLORS = {
    1: QColor(205, 127, 50),
    2: QColor(205, 214, 224),
    3: QColor(255, 210, 63),
}


def star_color(level):
    """Border colour for a unit of the given star ``level``."""
    return STAR_COLORS.get(level, STAR_COLORS[1])


def _row_letter(row):
    """Row index -> board letter (0 -> 'A')."""
    return chr(ord('A') + row)


def board_label(row, col):
    """Human readable label for a board cell, e.g. (0, 0) -> 'A1'."""
    return f'{_row_letter(row)}{col + 1}'


class UnitCell(QtWidgets.QWidget):
    """Base drag-and-drop cell that can hold a single unit.

    ``location`` is a string descriptor such as ``'bench:3'`` or
    ``'board:1,2'``.  ``drop_handler`` is called as
    ``drop_handler(source_location, target_location)``.
    """

    def __init__(self, location, drop_handler, parent=None):
        super().__init__(parent)
        self.location = location
        self.drop_handler = drop_handler
        self.right_click_handler = None
        self.refresh_hook = None
        self.unit = None
        self._pixmap = None
        self.setAcceptDrops(True)
        self.setMinimumSize(40, 40)

    def set_unit(self, unit, pixmap):
        """Place ``unit`` (with its ``pixmap``) into this cell, or clear it."""
        self.unit = unit
        self._pixmap = pixmap
        # repaint() (synchronous) rather than update() so a move is reflected
        # immediately - update() only schedules a repaint, which lags behind
        # the drag's nested event loop and looks like the icon "lingering".
        self.repaint()

    def is_occupied(self):
        """True when a unit currently sits in this cell."""
        return self.unit is not None

    # region drag source
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_occupied():
            self._drag_start = event.pos()
        else:
            self._drag_start = None
            if (event.button() == Qt.RightButton and self.is_occupied()
                    and self.right_click_handler is not None):
                self.right_click_handler(self)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (getattr(self, '_drag_start', None) is None
                or not (event.buttons() & Qt.LeftButton)
                or not self.is_occupied()):
            return
        if (event.pos() - self._drag_start).manhattanLength() < 8:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.location)
        drag.setMimeData(mime)
        if self._pixmap is not None:
            ghost = self._pixmap.scaled(
                48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            drag.setPixmap(ghost)
            drag.setHotSpot(ghost.rect().center())

        # Hide the unit from its source cell *immediately* and flush the paint
        # to the screen before the (blocking) drag takes over the event loop,
        # otherwise the unit appears to linger in its old slot.
        self.unit, self._pixmap = None, None
        self.repaint()
        QtWidgets.QApplication.processEvents(
            QtCore.QEventLoop.ExcludeUserInputEvents)

        drag.exec_(Qt.MoveAction)

        # Repaint every cell straight from the authoritative game state. On a
        # successful move the cells already reflect it; on a cancelled drag
        # the unit simply reappears in its source. No manual restore (that
        # caused a brief duplicate flash / linger).
        if self.refresh_hook is not None:
            self.refresh_hook()
    # endregion

    # region drop target
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        source = event.mimeData().text()
        if source and source != self.location:
            self.drop_handler(source, self.location)
        event.acceptProposedAction()
    # endregion


class HexCell(UnitCell):
    """A single hexagonal board cell with an unobtrusive A1-style label."""

    def __init__(self, row, col, drop_handler, parent=None):
        super().__init__(f'board:{row},{col}', drop_handler, parent)
        self.row = row
        self.col = col
        self.label = board_label(row, col)

    def _hex_polygon(self):
        """Pointy-top hexagon inscribed in the widget rectangle."""
        w = self.width()
        h = self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = min(w, h) / 2.0
        points = []
        for i in range(6):
            angle = math.pi / 180 * (60 * i - 90)
            points.append(QtCore.QPointF(cx + radius * math.cos(angle),
                                         cy + radius * math.sin(angle)))
        return QPolygonF(points)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        poly = self._hex_polygon()

        # Hex body - translucent so the board art shows through.
        fill = QColor(20, 20, 30, 150) if not self.is_occupied() \
            else QColor(40, 70, 110, 190)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(QColor(210, 210, 230), 2))
        painter.drawPolygon(poly)

        # Unit artwork - zoomed out (whole unit visible) and centred.
        if self._pixmap is not None:
            painter.setClipRegion(QtGui.QRegion(poly.toPolygon()))
            scaled = self._pixmap.scaled(
                self.width(), self.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.setClipping(False)

            # Star-level border (bronze / silver / gold).
            level = getattr(self.unit, 'level', 1)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(star_color(level), 2 + level))
            painter.drawPolygon(poly)

            # Star pips, unobtrusive, bottom-centre.
            painter.setPen(QPen(star_color(level)))
            sfont = painter.font()
            sfont.setPointSize(max(8, int(self.height() * 0.16)))
            sfont.setBold(True)
            painter.setFont(sfont)
            painter.drawText(
                QtCore.QRectF(0, self.height() * 0.62, self.width(),
                              self.height() * 0.3),
                Qt.AlignHCenter | Qt.AlignTop, '★' * level)

        # Coordinate label, kept *inside* the top of this hex so it can never
        # overlap a neighbouring cell. Bold + bright when a unit sits here.
        radius = min(self.width(), self.height()) / 2.0
        top_y = self.height() / 2.0 - radius
        occupied = self.is_occupied()

        font = painter.font()
        font.setPointSize(max(7, int(radius * 0.26)))
        font.setBold(occupied)
        painter.setFont(font)

        label_rect = QtCore.QRectF(0, top_y + radius * 0.12,
                                   self.width(), radius * 0.55)
        # Subtle shadow so it stays readable on top of artwork.
        painter.setPen(QPen(QColor(0, 0, 0, 150)))
        painter.drawText(label_rect.translated(1, 1),
                         Qt.AlignHCenter | Qt.AlignTop, self.label)
        painter.setPen(QPen(QColor(245, 245, 255) if occupied
                            else QColor(225, 225, 235, 185)))
        painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, self.label)


class BenchCell(UnitCell):
    """A single square bench slot."""

    def __init__(self, idx, drop_handler, parent=None):
        super().__init__(f'bench:{idx}', drop_handler, parent)
        self.idx = idx

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect().adjusted(2, 2, -2, -2)

        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), 6, 6)

        fill = QColor(25, 25, 35, 170) if not self.is_occupied() \
            else QColor(45, 75, 115, 200)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(QColor(200, 200, 220), 2))
        painter.drawPath(path)

        if self._pixmap is not None:
            # Fill the slot cleanly (clipped to the rounded rect) so a window
            # resize never leaves an odd letterboxed background behind.
            painter.save()
            painter.setClipPath(path)
            scaled = self._pixmap.scaled(
                rect.width(), rect.height(),
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = rect.x() + (rect.width() - scaled.width()) // 2
            y = rect.y() + (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.restore()

            # Star-level border + pips.
            level = getattr(self.unit, 'level', 1)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(star_color(level), 2 + level))
            painter.drawPath(path)

            painter.setPen(QPen(star_color(level)))
            sfont = painter.font()
            sfont.setPointSize(max(7, int(rect.height() * 0.16)))
            sfont.setBold(True)
            painter.setFont(sfont)
            painter.drawText(rect.adjusted(0, 0, -3, -2),
                             Qt.AlignRight | Qt.AlignBottom, '★' * level)


class BoardWidget(QtWidgets.QWidget):
    """Container that lays out 4 interlocking rows of 7 hexes.

    Rows A and C (0, 2) jut out on the left; rows B and D (1, 3) jut out on
    the right.  Hexes are repositioned proportionally on every resize so the
    relative layout is preserved and there is no wasted space.
    """

    def __init__(self, drop_handler, parent=None):
        super().__init__(parent)
        self.cells = {}
        for row in range(BOARD_ROWS):
            for col in range(BOARD_COLS):
                cell = HexCell(row, col, drop_handler, self)
                self.cells[(row, col)] = cell
        self.setMinimumSize(700, 360)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)

    def resizeEvent(self, _event):
        avail_w = self.width()
        avail_h = self.height()

        # Pointy-top hexagon geometry. With an inscribed-circle radius R the
        # cell box is (sqrt(3)*R) wide and (2*R) tall; rows step by 1.5*R and
        # odd rows are offset right by half a cell.
        # Horizontal extent: (cols + 0.5) cell widths.
        # Vertical extent: 2*R + (rows - 1) * 1.5 * R.
        radius_w = avail_w / ((BOARD_COLS + 0.5) * math.sqrt(3))
        radius_h = avail_h / (2 + (BOARD_ROWS - 1) * 1.5)
        radius = max(12.0, min(radius_w, radius_h))

        cell_w = math.sqrt(3) * radius
        cell_h = 2 * radius
        row_step = 1.5 * radius

        block_w = BOARD_COLS * cell_w + cell_w / 2
        block_h = cell_h + (BOARD_ROWS - 1) * row_step
        base_x = (avail_w - block_w) / 2
        base_y = (avail_h - block_h) / 2

        for (row, col), cell in self.cells.items():
            offset = cell_w / 2 if row % 2 == 1 else 0
            x = base_x + col * cell_w + offset
            y = base_y + row * row_step
            cell.setGeometry(int(x), int(y), int(cell_w), int(cell_h))


class BenchWidget(QtWidgets.QWidget):
    """A single row of 9 square bench slots."""

    def __init__(self, drop_handler, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        self.cells = []
        for idx in range(BENCH_SLOTS):
            cell = BenchCell(idx, drop_handler, self)
            cell.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                               QtWidgets.QSizePolicy.Expanding)
            layout.addWidget(cell)
            self.cells.append(cell)
        self.setMinimumHeight(90)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Maximum)

    def sizeHint(self):
        return QtCore.QSize(700, 110)


class TraitColumn(QtWidgets.QScrollArea):
    """Narrow, single-column list of activated traits."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMinimumWidth(210)
        self.setMaximumWidth(280)
        self.setStyleSheet('QScrollArea{background: rgba(255,255,255,210);'
                           'border: 1px solid #888;}')

        container = QtWidgets.QWidget()
        self.vbox = QtWidgets.QVBoxLayout(container)
        self.vbox.setContentsMargins(6, 6, 6, 6)
        self.vbox.setSpacing(6)
        self.vbox.addStretch(1)
        self.setWidget(container)

    def clear(self):
        """Remove every trait row."""
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_trait(self, icon_pixmap, name, amount_text, tier):
        """Add one trait row with a tier-coloured icon background."""
        row = QtWidgets.QFrame()
        row.setStyleSheet('QFrame{background: transparent;}')
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        icon = QtWidgets.QLabel()
        icon.setFixedSize(44, 44)
        icon.setScaledContents(True)
        icon.setAlignment(Qt.AlignCenter)
        if icon_pixmap is not None and not icon_pixmap.isNull():
            icon.setPixmap(icon_pixmap)
        bg = TIER_COLORS.get(tier, TIER_COLORS[None])
        icon.setStyleSheet(
            'QLabel { background: %s; border-radius: 6px; padding: 3px; }' % bg)
        layout.addWidget(icon)

        text = QtWidgets.QLabel(f'{name}\n{amount_text}')
        text.setStyleSheet('QLabel{color: #111; font-weight: bold;'
                           'background: transparent;}')
        layout.addWidget(text, 1)

        self.vbox.insertWidget(self.vbox.count() - 1, row)


class ShopSplash(QtWidgets.QWidget):
    """Champion splash for a shop slot with a resize-safe trait overlay.

    The artwork and the per-unit trait icons/names are recomputed in
    ``paintEvent`` from the *current* widget size, so they always scale
    correctly with the window (no fixed ``move()``/``setFixedSize``).  Mouse
    events fall through to the parent slot so buying / loaded-dice still work.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._traits = []          # list of (trait_name, QPixmap)
        self._owned = False
        self.setMinimumSize(150, 110)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)
        # Let clicks/drags reach the slot (buy).
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_unit(self, pixmap, traits, owned=False):
        """Set the splash ``pixmap``/``traits``; ``owned`` adds a white glow."""
        self._pixmap = pixmap
        self._traits = traits or []
        self._owned = owned
        self.update()

    def clear(self):
        """Empty the slot."""
        self.set_unit(None, [], False)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self.rect()

        if self._pixmap is not None and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                rect.size(), Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation)
            x = rect.x() + (rect.width() - scaled.width()) // 2
            y = rect.y() + (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        # Subtle white highlight when a copy of this unit is already owned.
        if self._owned and self._pixmap is not None:
            painter.setPen(QPen(QColor(255, 255, 255, 170), 2))
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.drawRect(rect.adjusted(2, 2, -2, -2))

        if not self._traits:
            return

        # Trait overlay: sizes are all proportional to the slot dimensions.
        icon_sz = max(14, int(min(rect.width(), rect.height()) * 0.17))
        gap = max(4, int(icon_sz * 0.35))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(7, int(icon_sz * 0.5)))
        painter.setFont(font)
        metrics = painter.fontMetrics()

        margin = int(rect.width() * 0.04)
        x0 = rect.x() + margin
        y = rect.y() + int(rect.height() * 0.06)

        for name, icon in self._traits:
            text_w = metrics.horizontalAdvance(name)
            chip_w = icon_sz + 6 + text_w + 10
            chip_h = icon_sz + 6

            # Translucent chip so the (dark, inverted) icon stays readable
            # on top of any artwork.
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 150))
            painter.drawRoundedRect(x0 - 3, y - 3, chip_w, chip_h, 5, 5)

            if icon is not None and not icon.isNull():
                # Light disc behind the (dark, inverted) icon so the tiny
                # trait icon is actually visible on the card.
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(235, 235, 240))
                painter.drawEllipse(x0 - 1, y - 1, icon_sz + 2, icon_sz + 2)
                painter.drawPixmap(x0, y, icon_sz, icon_sz, icon)

            painter.setPen(QColor(0, 255, 0))
            painter.drawText(
                QtCore.QRect(x0 + icon_sz + 6, y, text_w + 8, icon_sz),
                Qt.AlignLeft | Qt.AlignVCenter, name)

            y += chip_h + gap


class ShopArea(QtWidgets.QGroupBox):
    """Shop strip of SHOP_SLOTS slots; also a drop target that sells units."""

    def __init__(self, drop_handler, parent=None):
        super().__init__(parent)
        self.drop_handler = drop_handler
        self.setTitle('')
        self.setAcceptDrops(True)
        self._base_style = 'QGroupBox{background: black; color: white;}'
        self._sell_style = ('QGroupBox{background: #2a1414; color: white;'
                            'border: 3px solid #e23b3b;}')
        self.setStyleSheet(self._base_style)
        self.setMaximumHeight(340)
        self.setMinimumHeight(240)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 6)
        outer.setSpacing(4)

        # Persistent hint so it is obvious that the shop strip is the sell zone.
        self.sell_hint = QtWidgets.QLabel('⬇  DRAG A UNIT HERE TO SELL  ⬇')
        self.sell_hint.setAlignment(Qt.AlignCenter)
        self.sell_hint.setStyleSheet(
            'QLabel{color: #ff8a8a; font-weight: bold; letter-spacing: 2px;}')
        outer.addWidget(self.sell_hint, 0)

        slot_row = QtWidgets.QHBoxLayout()
        outer.addLayout(slot_row, 1)
        self.layout = slot_row
        self.slots = []
        self.splashes = []
        for i in range(SHOP_SLOTS):
            slot = QtWidgets.QGroupBox(self)
            slot.setObjectName(f'Slot_{i + 1}')
            slot.setTitle('')
            # Width comes purely from the equal stretch below, never from the
            # slot's contents - so the shop never resizes as units change.
            slot.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                               QtWidgets.QSizePolicy.Preferred)
            vbox = QtWidgets.QVBoxLayout(slot)
            vbox.setContentsMargins(4, 4, 4, 4)

            icon = ShopSplash(slot)
            icon.setObjectName(f'Shop_Icon_{i + 1}')
            vbox.addWidget(icon, 1)
            self.splashes.append(icon)

            rarity = QtWidgets.QLabel(slot)
            rarity.setObjectName(f'Shop_Rarity_{i + 1}')
            rarity.setScaledContents(True)
            rarity.setFixedHeight(8)
            vbox.addWidget(rarity)

            # Fixed-height info row so the splash area never changes size as
            # the shop contents change (units being bought/rolled).
            info = QtWidgets.QHBoxLayout()
            name = QtWidgets.QLabel(slot)
            name.setObjectName(f'Shop_Name_{i + 1}')
            name.setStyleSheet('color: white;')
            name.setFixedHeight(24)
            name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            # A long champion name must not widen the slot.
            name.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                               QtWidgets.QSizePolicy.Fixed)
            cost = QtWidgets.QLabel(slot)
            cost.setObjectName(f'Shop_Cost_{i + 1}')
            cost.setStyleSheet('color: gold;')
            cost.setFixedHeight(24)
            cost.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            info.addWidget(name)
            info.addWidget(cost)
            vbox.addLayout(info)

            self.layout.addWidget(slot, 1)   # equal stretch -> equal widths
            self.slots.append(slot)

    def _set_sell_highlight(self, on):
        self.setStyleSheet(self._sell_style if on else self._base_style)
        self.sell_hint.setText('⬇  RELEASE TO SELL  ⬇' if on
                               else '⬇  DRAG A UNIT HERE TO SELL  ⬇')

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            self._set_sell_highlight(True)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragLeaveEvent(self, _event):
        self._set_sell_highlight(False)

    def dropEvent(self, event):
        self._set_sell_highlight(False)
        source = event.mimeData().text()
        if source:
            self.drop_handler(source, 'shop')
        event.acceptProposedAction()


class TransientMessage(QtWidgets.QLabel):
    """Non-blocking, non-interactive banner that auto-hides."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            'QLabel{background: rgba(180, 30, 30, 220); color: white;'
            'font-size: 16px; font-weight: bold; border-radius: 8px;'
            'padding: 10px;}')
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def flash(self, text, msecs=2200):
        """Show ``text`` for ``msecs`` milliseconds without blocking."""
        self.setText(text)
        self.adjustSize()
        if self.parent() is not None:
            par = self.parent()
            self.move((par.width() - self.width()) // 2, 30)
        self.show()
        self.raise_()
        self._timer.start(msecs)


class ScaledIcon(QtWidgets.QLabel):
    """A clickable icon that scales with the widget but keeps aspect ratio.

    Unlike ``QLabel.setScaledContents(True)`` (which stretches and squishes the
    image), the pixmap is recomputed every paint to fit the current size while
    preserving its aspect ratio and staying centred.
    """

    def __init__(self, pixmap_path, parent=None):
        super().__init__(parent)
        self._src = QtGui.QPixmap(pixmap_path)
        self.setMinimumSize(120, 70)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)

    def paintEvent(self, _event):
        if self._src.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        scaled = self._src.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)


class Ui_MainWindow:
    """Builds the resizable, layout-based main window."""

    def setupUi(self, MainWindow, drop_handler):
        MainWindow.setObjectName("MainWindow")
        MainWindow.setMinimumSize(MIN_WINDOW_W, MIN_WINDOW_H)
        MainWindow.resize(MIN_WINDOW_W, MIN_WINDOW_H)

        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.centralwidget.setStyleSheet(
            '#centralwidget {'
            'border-image: url("General Assets/Boards/Pink_TFT.jpg") '
            '0 0 0 0 stretch stretch;}')
        root = QtWidgets.QHBoxLayout(self.centralwidget)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Left: narrow trait column (barely touches the board).
        self.trait_column = TraitColumn(self.centralwidget)
        root.addWidget(self.trait_column, 0)

        # Center: top info bar, board, bench, shop.
        center = QtWidgets.QVBoxLayout()
        center.setSpacing(6)

        # Info / controls bar.
        bar = QtWidgets.QHBoxLayout()
        self.Gold_Label = QtWidgets.QLabel('Gold: 0')
        gfont = QtGui.QFont()
        gfont.setPointSize(18)
        self.Gold_Label.setFont(gfont)
        self.Gold_Label.setStyleSheet('color: gold; font-weight: bold;')

        self.Level_Label = QtWidgets.QLabel('Level: 1  0 / 0')
        lfont = QtGui.QFont()
        lfont.setPointSize(14)
        self.Level_Label.setFont(lfont)
        self.Level_Label.setStyleSheet('color: #6cf; font-weight: bold;')

        # Buy-exp (top) and reroll (bottom) live in a column left of the shop.
        # ScaledIcon keeps the artwork's aspect ratio (no squishing).
        self.Level_Up = ScaledIcon("General Assets/Level.png")
        self.Level_Up.setToolTip('Buy EXP')

        self.Reroll = ScaledIcon("General Assets/Reroll.png")
        self.Reroll.setToolTip('Reroll')

        bar.addWidget(self.Gold_Label)
        bar.addSpacing(20)
        bar.addWidget(self.Level_Label)
        bar.addStretch(1)
        center.addLayout(bar, 0)

        # Board (expands to fill).
        self.board_widget = BoardWidget(drop_handler, self.centralwidget)
        center.addWidget(self.board_widget, 1)

        # Bench.
        self.bench_widget = BenchWidget(drop_handler, self.centralwidget)
        center.addWidget(self.bench_widget, 0)

        # Shop, with the reroll / buy-exp controls column on its left.
        shop_row = QtWidgets.QHBoxLayout()
        shop_row.setSpacing(6)

        controls = QtWidgets.QVBoxLayout()
        # Stack the two icons directly on top of each other (no gap/margins).
        controls.setSpacing(0)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self.Level_Up, 1)   # buy-exp on top
        controls.addWidget(self.Reroll, 1)     # reroll directly below
        controls_box = QtWidgets.QWidget()
        # Transparent so the icons sit on the board background instead of an
        # out-of-place black panel.
        controls_box.setAttribute(Qt.WA_StyledBackground, True)
        controls_box.setStyleSheet('background: transparent;')
        controls_box.setLayout(controls)
        controls_box.setFixedWidth(190)

        shop_row.addWidget(controls_box, 0)
        self.shop_area = ShopArea(drop_handler, self.centralwidget)
        shop_row.addWidget(self.shop_area, 1)
        center.addLayout(shop_row, 0)

        root.addLayout(center, 1)

        MainWindow.setCentralWidget(self.centralwidget)

        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        MainWindow.setStatusBar(self.statusbar)

        # Transient (non-blocking) message banner.
        self.message = TransientMessage(self.centralwidget)

        QtCore.QMetaObject.connectSlotsByName(MainWindow)

        return {
            'shop': self.shop_area.slots,
            'shop_area': self.shop_area,
            'board': self.board_widget,
            'bench': self.bench_widget,
            'traits': self.trait_column,
            'gold_label': self.Gold_Label,
            'level_label': self.Level_Label,
            'level_up': self.Level_Up,
            'reroll': self.Reroll,
            'message': self.message,
        }
