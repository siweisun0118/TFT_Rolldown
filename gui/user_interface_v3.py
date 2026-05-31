"""Generate the UI for rolldown."""
# pylint: disable=all
from PyQt5 import QtCore, QtGui, QtWidgets

from gui.widgets import BenchSlot, HexBoard, ShopSlot, TraitBadge, Toast

from shared.rolldown_enums import GEN_ASSETS

# Minimum window size – matches the previous hardcoded geometry.
MIN_WINDOW_SIZE = (1366, 973)

# Board geometry
BOARD_ROWS = ('A', 'B', 'C', 'D')
BOARD_COLS = (1, 2, 3, 4, 5, 6, 7)
BENCH_SIZE = 9
SHOP_SIZE = 5

# Number of trait badges visible before scrolling.
MAX_VISIBLE_TRAITS = 14


def pathlib_path(root, ext):
    """Extend a Path and convert to string (kept for backwards compatibility)."""
    return str(root / ext)


class Ui_MainWindow:
    """Configure the main window's children using nothing but Qt layouts."""

    def setupUi(self, MainWindow):  # noqa: N802 -- match Qt naming
        MainWindow.setObjectName('MainWindow')
        MainWindow.setMinimumSize(*MIN_WINDOW_SIZE)
        MainWindow.resize(*MIN_WINDOW_SIZE)
        MainWindow.setWindowTitle('TFT Rolldown')

        central = QtWidgets.QWidget(MainWindow)
        central.setObjectName('centralwidget')
        central.setStyleSheet(
            '#centralwidget { background: #2c2620; }'
        )
        MainWindow.setCentralWidget(central)

        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ------------------------------------------------------------------ traits column
        self.traits_column = QtWidgets.QGroupBox('TRAITS')
        self.traits_column.setStyleSheet(
            'QGroupBox { background: #f7f1e4; color: #2c2620; '
            'border: 2px solid #4d3a1f; border-radius: 8px; padding-top: 18px;}'
            'QGroupBox::title { subcontrol-origin: margin; left: 12px; '
            'top: 0px; color: #2c2620; }'
        )
        self.traits_column.setMinimumWidth(220)
        self.traits_column.setMaximumWidth(320)
        traits_layout = QtWidgets.QVBoxLayout(self.traits_column)
        traits_layout.setContentsMargins(8, 24, 8, 8)
        traits_layout.setSpacing(6)

        self.trait_widgets = []
        for _ in range(MAX_VISIBLE_TRAITS):
            badge = TraitBadge(self.traits_column)
            traits_layout.addWidget(badge)
            self.trait_widgets.append(badge)
        traits_layout.addStretch(1)

        root.addWidget(self.traits_column, 0)

        # ------------------------------------------------------------------ centre column
        centre = QtWidgets.QVBoxLayout()
        centre.setSpacing(10)
        root.addLayout(centre, 1)

        # ----- top bar with gold and level controls
        top_bar = QtWidgets.QFrame()
        top_bar.setStyleSheet(
            'QFrame { background: #1f1a13; border-radius: 8px; }'
            'QLabel { color: #ffd76b; }'
        )
        top_bar.setFixedHeight(56)
        top_layout = QtWidgets.QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 8, 16, 8)
        top_layout.setSpacing(20)

        self.gold_label = QtWidgets.QLabel('Gold: 0')
        gold_font = QtGui.QFont()
        gold_font.setPointSize(18)
        gold_font.setBold(True)
        self.gold_label.setFont(gold_font)

        self.level_label = QtWidgets.QLabel('Level: 1   0 / 2')
        level_font = QtGui.QFont()
        level_font.setPointSize(14)
        self.level_label.setFont(level_font)
        self.level_label.setStyleSheet('color: #8fd0ff;')

        top_layout.addWidget(self.gold_label)
        top_layout.addWidget(self.level_label)
        top_layout.addStretch(1)
        centre.addWidget(top_bar, 0)

        # ----- board (4 rows × 7 hexes; absolute positioning, see HexBoard)
        self.board = HexBoard(BOARD_ROWS, BOARD_COLS)
        # The board's flat tile list is exposed for backwards compatibility
        # with the test suite (it used ``board_tiles[row][col]``).
        self.board_tiles = [
            [self.board.tiles[(r, c)] for c in BOARD_COLS] for r in BOARD_ROWS
        ]
        # board_tiles_by_position is a flat dict keyed by ``(row, col)``.
        self.board_tiles_by_position = dict(self.board.tiles)
        centre.addWidget(self.board, 6)

        # ----- bench
        bench_container = QtWidgets.QFrame()
        bench_container.setStyleSheet(
            'QFrame { background: #f4dfb6; border: 3px solid #4d3a1f; border-radius: 12px; }'
        )
        bench_container.setFixedHeight(90)
        bench_layout = QtWidgets.QHBoxLayout(bench_container)
        bench_layout.setContentsMargins(16, 8, 16, 8)
        bench_layout.setSpacing(8)
        self.bench_slots = []
        for i in range(BENCH_SIZE):
            slot = BenchSlot(i, parent=bench_container)
            bench_layout.addWidget(slot, 1)
            self.bench_slots.append(slot)
        centre.addWidget(bench_container, 0)

        # ----- bottom row: controls + shop side-by-side
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.setSpacing(10)

        # Buttons stack: Buy XP on top, Reroll on bottom.
        controls_box = QtWidgets.QFrame()
        controls_box.setStyleSheet(
            'QFrame { background: #1f1a13; border-radius: 8px; }'
        )
        controls_layout = QtWidgets.QVBoxLayout(controls_box)
        controls_layout.setContentsMargins(8, 8, 8, 8)
        controls_layout.setSpacing(8)

        self.level_up = QtWidgets.QPushButton('Buy XP\n(4g)')
        self.level_up.setStyleSheet(
            'QPushButton { background: #5566ff; color: white; padding: 12px;'
            ' border-radius: 6px; font-weight: bold; font-size: 14px;}'
            'QPushButton:hover { background: #6677ff; }'
        )
        self.level_up.setMinimumHeight(90)
        self.level_up.setMinimumWidth(120)

        self.reroll = QtWidgets.QPushButton('Reroll\n(2g)')
        self.reroll.setStyleSheet(
            'QPushButton { background: #cc6633; color: white; padding: 12px;'
            ' border-radius: 6px; font-weight: bold; font-size: 14px;}'
            'QPushButton:hover { background: #dd7744; }'
        )
        self.reroll.setMinimumHeight(90)
        self.reroll.setMinimumWidth(120)

        controls_layout.addWidget(self.level_up)
        controls_layout.addWidget(self.reroll)
        bottom_row.addWidget(controls_box, 0)

        # ----- shop slots
        shop_container = QtWidgets.QGroupBox('SHOP')
        shop_container.setStyleSheet(
            'QGroupBox { background: #1c1c1c; color: white; border: 2px solid #4d3a1f; '
            'border-radius: 8px; padding-top: 18px; }'
            'QGroupBox::title { subcontrol-origin: margin; left: 12px; color: gold; }'
        )
        shop_layout = QtWidgets.QHBoxLayout(shop_container)
        shop_layout.setContentsMargins(10, 24, 10, 10)
        shop_layout.setSpacing(8)
        self.shop_widgets = []
        for idx in range(SHOP_SIZE):
            slot = ShopSlot(idx, parent=shop_container)
            shop_layout.addWidget(slot, 1)
            self.shop_widgets.append(slot)
        bottom_row.addWidget(shop_container, 1)

        centre.addLayout(bottom_row, 2)

        # ------------------------------------------------------------------ controls dict
        controls = {
            'gold_label': self.gold_label,
            'level_label': self.level_label,
            'reroll': self.reroll,
            'level_up': self.level_up,
        }

        # Toast overlay
        self.toast = Toast(central)

        # Backwards-compat alias used by the older test suite.
        self.board_container = self.board

        return self.shop_widgets, self.trait_widgets, self.board_tiles, self.bench_slots, controls

    def retranslateUi(self, MainWindow):  # noqa: N802 -- match Qt naming
        """No-op kept for backwards compatibility."""
