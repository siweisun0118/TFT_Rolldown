"""Custom Qt widgets used by the new TFT-Rolldown GUI.

The widgets here are deliberately self-contained so they can be unit-tested
without spinning up the full application window.

Highlights:

* :class:`HexBoard` lays its tiles out with proper pointy-top hex geometry so
  rows interlock (A1 shares its bottom-right edge with B1, etc.).
* :class:`UnitChip` carries the drag/drop machinery; on drag it sets a
  ``QPixmap()`` (empty) on the drag preview so the GUI does not show a
  lingering ghost icon after a drop.
* :class:`ShopSlot` overlays trait icons on the unit splash itself so the
  shop column has a fixed height regardless of how many traits a champion
  has.  A coloured rarity banner runs along the bottom of the slot.
* :class:`Toast` floats above the board for transient notifications.
"""

# Standard libraries
import math
from pathlib import Path

# pylint: disable=no-name-in-module
from PyQt5 import QtCore, QtGui, QtWidgets


# ---------------------------------------------------------------------------- helpers
TIER_COLORS = {
    'bronze': QtGui.QColor('#b08d57'),
    'silver': QtGui.QColor('#c0c0c0'),
    'gold': QtGui.QColor('#e0c245'),
    'prismatic': None,  # gradient – handled in paintEvent
    'inactive': QtGui.QColor('#5c5c5c'),
}

# RGB swatches mirroring the ``General Assets/rarities/*.png`` files so the
# shop banner colour stays consistent even if the PNG isn't available.
RARITY_COLORS = {
    1: QtGui.QColor(135, 135, 135),  # grey
    2: QtGui.QColor(26, 150, 0),     # green
    3: QtGui.QColor(70, 70, 255),    # blue
    4: QtGui.QColor(179, 0, 179),    # purple
    5: QtGui.QColor(255, 140, 0),    # orange
}


def make_prismatic_brush(rect):
    """Return a multi-stop linear gradient brush in *rect* for prismatic traits."""
    grad = QtGui.QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.00, QtGui.QColor('#ff5fb1'))
    grad.setColorAt(0.25, QtGui.QColor('#ffba4c'))
    grad.setColorAt(0.50, QtGui.QColor('#76e2ff'))
    grad.setColorAt(0.75, QtGui.QColor('#a47bff'))
    grad.setColorAt(1.00, QtGui.QColor('#ff8da8'))
    return QtGui.QBrush(grad)


def make_glow_effect():
    """Return a glow effect used to mark already-owned units in the shop.

    The glow is intentionally white and high-alpha so it reads clearly on
    the dark shop background.  A larger blur radius makes the halo more
    diffuse so the slot looks lit-from-within.
    """
    glow = QtWidgets.QGraphicsDropShadowEffect()
    glow.setOffset(0, 0)
    glow.setBlurRadius(70)
    glow.setColor(QtGui.QColor(255, 255, 255, 255))
    return glow


# ---------------------------------------------------------------------------- unit chip
class UnitChip(QtWidgets.QLabel):
    """Draggable square that represents a unit on the board or bench."""

    BLANK_TEXT = ''

    def __init__(self, slot_kind, slot_index, parent=None):
        super().__init__(parent)
        self.slot_kind = slot_kind  # 'board' or 'bench'
        self.slot_index = slot_index
        self.unit = None
        self.setAcceptDrops(False)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMinimumSize(40, 40)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setText(self.BLANK_TEXT)
        self._press_pos = None

    def set_unit(self, unit, splash_path=None):
        """Place ``unit`` (or clear if ``None``) into the chip."""
        self.unit = unit
        if unit is None:
            self.setPixmap(QtGui.QPixmap())
            self.setText('')
            self.setStyleSheet('background: transparent;')
            return

        # Border coloured by rarity makes the chip readable on bench/board.
        rarity_color = RARITY_COLORS.get(unit.rarity, QtGui.QColor(0, 0, 0))
        self.setStyleSheet(
            'background: rgba(20, 20, 20, 220); '
            f'border: 2px solid {rarity_color.name()}; '
            'border-radius: 6px;'
        )

        pixmap = QtGui.QPixmap()
        if splash_path is not None and Path(splash_path).is_file():
            pixmap = QtGui.QPixmap(str(splash_path))
        if pixmap.isNull():
            self.setText(unit.name)
        else:
            # Scale lazily on the next paint pass; keep aspect ratio.
            self.setPixmap(pixmap.scaled(
                self.size().expandedTo(QtCore.QSize(40, 40)),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            ))
            self.setText('')

    def mousePressEvent(self, event):  # noqa: D401 -- Qt naming
        if event.button() == QtCore.Qt.LeftButton and self.unit is not None:
            self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: D401 -- Qt naming
        if self.unit is None or self._press_pos is None:
            return
        if not (event.buttons() & QtCore.Qt.LeftButton):
            return
        if (event.pos() - self._press_pos).manhattanLength() < \
                QtWidgets.QApplication.startDragDistance():
            return
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        if self.slot_kind == 'board':
            row, col = self.slot_index
            payload = f'board|{row}|{col}'
        else:
            payload = f'bench|{int(self.slot_index)}'
        mime.setText(payload)
        drag.setMimeData(mime)
        # Use a small fixed-size translucent ghost so it disappears the
        # instant Qt finishes the drop.  Using setPixmap(QPixmap()) would
        # leave the OS cursor without a hotspot which on some platforms
        # produces the lingering image; a 1×1 transparent pixmap is the
        # standard workaround.
        ghost = QtGui.QPixmap(1, 1)
        ghost.fill(QtCore.Qt.transparent)
        drag.setPixmap(ghost)
        drag.setHotSpot(QtCore.QPoint(0, 0))
        drag.exec_(QtCore.Qt.MoveAction)
        self._press_pos = None


# ---------------------------------------------------------------------------- hex tile
class HexTile(QtWidgets.QWidget):
    """A single hexagonal slot.  Renders a pointy-top hex outline."""

    BORDER_COLOR = QtGui.QColor('#4d3a1f')
    FILL_COLOR = QtGui.QColor('#f2e0b8')

    def __init__(self, row_label, column_label, parent=None):
        super().__init__(parent)
        self.row_label = row_label
        self.column_label = column_label
        self.setAcceptDrops(True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        self.chip = UnitChip(slot_kind='board', slot_index=(row_label, column_label), parent=self)
        self.chip.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        self.label = QtWidgets.QLabel(f'{row_label}{column_label}', self)
        self.label.setStyleSheet(
            'color: rgba(40, 25, 5, 220); '
            'background: rgba(255, 255, 255, 160); '
            'border-radius: 4px; '
            'padding: 0 4px; '
            'font-weight: bold;'
        )
        self.label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

    def label_text(self):
        return f'{self.row_label}{self.column_label}'

    def resizeEvent(self, event):  # noqa: D401 -- Qt naming
        super().resizeEvent(event)
        # The chip occupies a square inscribed inside the hex's inner radius.
        side = min(self.width(), self.height())
        inscribed = int(side * 0.62)
        x = (self.width() - inscribed) // 2
        y = (self.height() - inscribed) // 2
        self.chip.setGeometry(x, y, inscribed, inscribed)
        self.label.adjustSize()
        # Place label in the top-left corner, hovering above the hex border.
        self.label.move(max(4, x - 4), max(2, y - 16))

    def paintEvent(self, event):  # noqa: D401 -- Qt naming
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        polygon = self._hexagon()
        painter.setBrush(self.FILL_COLOR)
        painter.setPen(QtGui.QPen(self.BORDER_COLOR, 2))
        painter.drawPolygon(polygon)
        painter.end()
        super().paintEvent(event)

    def _hexagon(self):
        """Return the pointy-top hexagon polygon for this widget."""
        w = self.width()
        h = self.height()
        cx, cy = w / 2.0, h / 2.0
        # Make the hex as large as possible within the widget; pointy-top
        # means width = sqrt(3)*size, height = 2*size.
        size = min(w / math.sqrt(3), h / 2)
        pts = []
        for i in range(6):
            # Pointy-top: vertex angle starts at 30deg (top vertex).
            angle = math.radians(60 * i - 30)
            pts.append(QtCore.QPointF(cx + size * math.cos(angle),
                                      cy + size * math.sin(angle)))
        # Ordering: vertices need to wind correctly.  For pointy-top start
        # at the top-right vertex.  ``i=0`` already gives the top-right, so
        # we just shift to start at the top.
        return QtGui.QPolygonF(pts)

    # ------------------------------------------------------------------ DnD
    def dragEnterEvent(self, event):  # noqa: D401 -- Qt naming
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: D401 -- Qt naming
        payload = event.mimeData().text()
        window = self.window()
        handler = getattr(window, 'handle_drop', None)
        if handler is not None:
            handler(payload, 'board', self.chip.slot_index)
        event.acceptProposedAction()


class HexBoard(QtWidgets.QFrame):
    """Container that positions :class:`HexTile` instances in a honeycomb.

    Uses absolute positioning in :meth:`resizeEvent` because Qt's standard
    layout managers cannot express the half-hex column offset that makes
    rows interlock.
    """

    def __init__(self, rows, cols, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.cols = cols
        self.tiles = {}
        for row_label in rows:
            for col_label in cols:
                tile = HexTile(row_label, col_label, parent=self)
                self.tiles[(row_label, col_label)] = tile
        self.setStyleSheet(
            'HexBoard { background: #d4ad6a; border: 3px solid #4d3a1f; '
            'border-radius: 12px; }'
        )
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

    def sizeHint(self):  # noqa: D401 -- Qt naming
        return QtCore.QSize(900, 480)

    def minimumSizeHint(self):  # noqa: D401 -- Qt naming
        return QtCore.QSize(600, 320)

    def resizeEvent(self, event):  # noqa: D401 -- Qt naming
        super().resizeEvent(event)
        pad = 16
        avail_w = max(self.width() - 2 * pad, 1)
        avail_h = max(self.height() - 2 * pad, 1)
        n_cols = len(self.cols)
        n_rows = len(self.rows)

        # Pointy-top hex of width W (flat-to-flat) and height H (vertex-to-vertex):
        #   W = sqrt(3) * size, H = 2 * size, so H = 2/sqrt(3) * W
        # Horizontal step between centres in a row = W
        # Vertical step between centres in adjacent rows = 0.75 * H
        # Odd rows shifted right by W/2.
        # Total horizontal extent = n_cols * W + W/2 (for offset) = (n_cols + 0.5) * W
        # Total vertical extent = (n_rows - 1) * 0.75 * H + H = (0.75*(n_rows-1) + 1) * H
        # Solve for the largest hex size that fits both dimensions.

        # Try fitting by width.
        w_from_width = avail_w / (n_cols + 0.5)
        h_from_width = w_from_width * 2 / math.sqrt(3)

        # Try fitting by height.
        h_from_height = avail_h / (0.75 * (n_rows - 1) + 1)
        w_from_height = h_from_height * math.sqrt(3) / 2

        if h_from_width <= h_from_height:
            hex_w, hex_h = w_from_width, h_from_width
        else:
            hex_w, hex_h = w_from_height, h_from_height

        # Each hex widget needs to be slightly larger than the hex polygon
        # to give the label some breathing room above the tile.
        widget_w = hex_w
        widget_h = hex_h

        # Total content area used.
        used_w = (n_cols + 0.5) * hex_w
        used_h = (0.75 * (n_rows - 1) + 1) * hex_h
        x_origin = pad + (avail_w - used_w) / 2
        y_origin = pad + (avail_h - used_h) / 2

        for r_idx, row_label in enumerate(self.rows):
            y_centre = y_origin + (0.75 * r_idx * hex_h) + hex_h / 2
            # Rows A (r_idx=0) and C (r_idx=2) jut left → no x offset.
            # Rows B (r_idx=1) and D (r_idx=3) jut right → shifted by hex_w/2.
            offset = (hex_w / 2) if r_idx % 2 == 1 else 0
            for c_idx, col_label in enumerate(self.cols):
                x_centre = x_origin + offset + c_idx * hex_w + hex_w / 2
                tile = self.tiles[(row_label, col_label)]
                tile.setGeometry(
                    int(x_centre - widget_w / 2),
                    int(y_centre - widget_h / 2),
                    int(widget_w),
                    int(widget_h),
                )


# ----------------------------------------------------------------------- bench slot
class BenchSlot(QtWidgets.QFrame):
    """Square bench slot that wraps a :class:`UnitChip`."""

    def __init__(self, slot_index, parent=None):
        super().__init__(parent)
        self.setObjectName(f'BenchSlot_{slot_index}')
        self.setStyleSheet(
            '#BenchSlot_%d { background: #f4e6c6; border: 2px solid #4d3a1f; '
            'border-radius: 6px; }' % slot_index
        )
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMinimumSize(60, 60)
        self.setAcceptDrops(True)
        self.chip = UnitChip(slot_kind='bench', slot_index=slot_index, parent=self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.chip)

    def dragEnterEvent(self, event):  # noqa: D401 -- Qt naming
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: D401 -- Qt naming
        payload = event.mimeData().text()
        window = self.window()
        handler = getattr(window, 'handle_drop', None)
        if handler is not None:
            handler(payload, 'bench', self.chip.slot_index)
        event.acceptProposedAction()


# ---------------------------------------------------------------------------- trait badge
class TraitBadge(QtWidgets.QFrame):
    """Single-row trait widget: icon, name, ``amount/breakpoint``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tier = 'inactive'
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.setMinimumHeight(40)
        self.setAutoFillBackground(False)

        self.icon = QtWidgets.QLabel(self)
        self.icon.setFixedSize(32, 32)
        self.icon.setScaledContents(True)

        self.text = QtWidgets.QLabel(self)
        self.text.setStyleSheet('color: white; font-weight: bold;')
        self.text.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)
        layout.addWidget(self.icon)
        layout.addWidget(self.text, 1)

    def set_state(self, icon_pixmap, name, amount, target, tier):
        self.tier = tier
        if icon_pixmap is None or icon_pixmap.isNull():
            self.icon.clear()
            self.icon.setText('?')
            self.icon.setStyleSheet('color: white; background: rgba(0, 0, 0, 0.2);')
        else:
            self.icon.setStyleSheet('')
            self.icon.setPixmap(icon_pixmap)
        self.text.setText(f'{name}   {amount} / {target}')
        if tier == 'prismatic':
            self.text.setStyleSheet('color: #1a1a1a; font-weight: bold;')
        elif tier == 'inactive':
            self.text.setStyleSheet('color: #d0d0d0; font-weight: bold;')
        else:
            self.text.setStyleSheet('color: white; font-weight: bold;')
        self.update()

    def clear_state(self):
        self.tier = 'inactive'
        self.icon.clear()
        self.text.clear()
        self.update()

    def paintEvent(self, event):  # noqa: D401 -- Qt naming
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        if self.tier == 'prismatic':
            painter.setBrush(make_prismatic_brush(rect))
            painter.setPen(QtCore.Qt.NoPen)
        else:
            color = TIER_COLORS.get(self.tier, TIER_COLORS['inactive'])
            painter.setBrush(color)
            painter.setPen(QtGui.QPen(color.darker(150), 1))
        painter.drawRoundedRect(rect, 6, 6)
        painter.end()
        super().paintEvent(event)


class SplashLabel(QtWidgets.QLabel):
    """A QLabel that re-scales its source pixmap on every resize.

    Storing the pixmap unscaled and rescaling on resize keeps the splash
    sharp regardless of when the label is first painted (Qt's default
    label size is 640×480 before layout runs, which is what made the
    shop icons look "zoomed in" on the first frame).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None  # original, unscaled QPixmap
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

    def set_source(self, pixmap):
        """Set the source pixmap and trigger an immediate rescale."""
        if pixmap is None or pixmap.isNull():
            self._source = None
            self.clear()
            return
        self._source = pixmap
        self._apply_scale()

    def clear_source(self):
        self._source = None
        self.clear()

    def has_source(self):
        return self._source is not None

    def resizeEvent(self, event):  # noqa: D401 -- Qt naming
        super().resizeEvent(event)
        self._apply_scale()

    def _apply_scale(self):
        if self._source is None:
            return
        target = self.size()
        if target.width() <= 1 or target.height() <= 1:
            target = QtCore.QSize(180, 140)
        super().setPixmap(
            self._source.scaled(
                target,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )


# ---------------------------------------------------------------------------- shop slot
class ShopSlot(QtWidgets.QFrame):
    """A single shop slot.  Click-to-buy, right-click to use loaded dice."""

    leftClicked = QtCore.pyqtSignal(int)
    rightClicked = QtCore.pyqtSignal(int)

    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.unit = None
        self._owned_glow = False
        # Cache the *unscaled* splash so we can re-render at the correct
        # size on every resize.  Without this the first paint scales the
        # pixmap to ``QLabel.size()`` (which is Qt's default 640×480
        # before the layout has run), which made splashes look zoomed in
        # / cropped on the first frame.
        self._splash_source = None
        self.setStyleSheet(
            'ShopSlot { background: #2b2b2b; border: 2px solid #444; border-radius: 6px;}'
            'ShopSlot:hover { border-color: gold; }'
        )
        # Reserve a fixed minimum size so the slot does not jump around when
        # a champion with three traits replaces one with one trait.
        self.setMinimumSize(150, 220)
        self.setMaximumHeight(260)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        # ------------------------------------------------------------------ icon
        self.icon = SplashLabel()
        self.icon.setMinimumHeight(120)
        layout.addWidget(self.icon, 1)

        # ------------------------------------------------------------------ traits column overlaid on icon
        self.trait_column = QtWidgets.QWidget(self.icon)
        self.trait_column.setStyleSheet('background: transparent;')
        self.trait_column.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.trait_rows = []
        trait_layout = QtWidgets.QVBoxLayout(self.trait_column)
        trait_layout.setContentsMargins(0, 0, 0, 0)
        trait_layout.setSpacing(2)
        for _ in range(3):
            row_widget = QtWidgets.QWidget(self.trait_column)
            row_widget.setStyleSheet('background: rgba(0, 0, 0, 140); border-radius: 6px;')
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(2, 2, 6, 2)
            row_layout.setSpacing(4)
            icon = QtWidgets.QLabel(row_widget)
            icon.setFixedSize(18, 18)
            icon.setScaledContents(True)
            name_label = QtWidgets.QLabel(row_widget)
            name_label.setStyleSheet('color: white; font-weight: bold;')
            row_layout.addWidget(icon)
            row_layout.addWidget(name_label, 1)
            trait_layout.addWidget(row_widget)
            self.trait_rows.append((row_widget, icon, name_label))
        trait_layout.addStretch(1)

        # ------------------------------------------------------------------ bottom bar with name/cost
        info_bar = QtWidgets.QFrame()
        info_bar.setStyleSheet(
            'QFrame { background: rgba(0, 0, 0, 200); border-radius: 4px; }'
            'QLabel { color: white; font-weight: bold; }'
        )
        info_layout = QtWidgets.QHBoxLayout(info_bar)
        info_layout.setContentsMargins(6, 2, 6, 2)
        info_layout.setSpacing(4)
        self.name_label = QtWidgets.QLabel('-')
        self.cost_label = QtWidgets.QLabel('-')
        self.cost_label.setStyleSheet('color: gold; font-weight: bold;')
        self.cost_label.setAlignment(QtCore.Qt.AlignRight)
        info_layout.addWidget(self.name_label, 1)
        info_layout.addWidget(self.cost_label, 0)
        layout.addWidget(info_bar, 0)

        # ------------------------------------------------------------------ rarity banner (fixed height)
        self.rarity_banner = QtWidgets.QFrame()
        self.rarity_banner.setFixedHeight(8)
        self.rarity_banner.setStyleSheet(
            'background: #555; border-bottom-left-radius: 4px; '
            'border-bottom-right-radius: 4px;'
        )
        layout.addWidget(self.rarity_banner, 0)

    def resizeEvent(self, event):  # noqa: D401 -- Qt naming
        super().resizeEvent(event)
        # Position the trait overlay column in the top-left of the icon
        # area so it always sits over the splash regardless of size.
        margin = 4
        width = max(self.icon.width() // 2, 100)
        self.trait_column.setGeometry(margin, margin, width, self.icon.height() - 2 * margin)
        # SplashLabel handles its own re-scale; nothing else to do here.

    def mouseReleaseEvent(self, event):  # noqa: D401 -- Qt naming
        if event.button() == QtCore.Qt.LeftButton:
            self.leftClicked.emit(self.index)
        elif event.button() == QtCore.Qt.RightButton:
            self.rightClicked.emit(self.index)
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ display
    def display(self, unit, splash_pixmap=None, trait_pixmaps=None):
        """Update the slot to show *unit*.

        Perf §1.7: if the slot is already showing the same unit (same name
        and cost), we skip the work entirely.
        """
        previous = self.unit
        if unit is None or unit.name == 'BLANK':
            if previous is None:
                return
            self.unit = None
            self._splash_source = None
            self.icon.clear_source()
            self.icon.setText('')
            self.name_label.setText('')
            self.cost_label.setText('')
            for row_widget, icon, name_label in self.trait_rows:
                row_widget.setVisible(False)
                icon.clear()
                name_label.setText('')
            self.rarity_banner.setStyleSheet('background: #555;')
            self.set_owned(False)
            return

        same_unit = previous is not None and previous.name == unit.name
        self.unit = unit
        if splash_pixmap is not None and not splash_pixmap.isNull():
            # SplashLabel stashes the unscaled source and re-scales on
            # every resize, so the icon stays sharp whether or not the
            # layout has run yet.  This is the fix for "icons are zoomed
            # in on first launch".
            self._splash_source = splash_pixmap
            self.icon.set_source(splash_pixmap)
        else:
            self._splash_source = None
            self.icon.clear_source()
            self.icon.setText(unit.name)

        self.name_label.setText(unit.name)
        self.cost_label.setText(f'{unit.cost}G')

        # Traits.  Cap at 3 rows.
        traits = list(unit.traits)[:3]
        trait_pixmaps = trait_pixmaps or {}
        for idx, (row_widget, icon, name_label) in enumerate(self.trait_rows):
            if idx < len(traits):
                trait_name = traits[idx]
                row_widget.setVisible(True)
                pix = trait_pixmaps.get(trait_name)
                if pix is not None and not pix.isNull():
                    icon.setPixmap(pix)
                else:
                    icon.clear()
                name_label.setText(trait_name)
            else:
                row_widget.setVisible(False)
                icon.clear()
                name_label.setText('')

        # Rarity banner.
        rarity_color = RARITY_COLORS.get(unit.rarity, QtGui.QColor('#555'))
        self.rarity_banner.setStyleSheet(
            f'background: {rarity_color.name()}; '
            'border-bottom-left-radius: 4px; '
            'border-bottom-right-radius: 4px;'
        )

    def set_owned(self, owned):
        """Toggle the "already-owned" glow effect."""
        if owned == self._owned_glow:
            return
        self._owned_glow = owned
        if owned:
            self.setGraphicsEffect(make_glow_effect())
        else:
            self.setGraphicsEffect(None)


# ---------------------------------------------------------------------------- transient toast
class Toast(QtWidgets.QLabel):
    """Non-interactive transient overlay used for "Bench is full" messages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            'background: rgba(0, 0, 0, 180); color: white; padding: 12px 18px;'
            'border-radius: 12px; font-weight: bold;'
        )
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setVisible(False)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide)

    def show_message(self, text, duration_ms=2000):
        self.setText(text)
        self.adjustSize()
        parent = self.parent()
        if parent is not None:
            geometry = parent.geometry()
            self.move(
                (geometry.width() - self.width()) // 2,
                (geometry.height() - self.height()) - 80,
            )
        self.setVisible(True)
        self.raise_()
        self._timer.start(duration_ms)

    def _hide(self):
        self.setVisible(False)
