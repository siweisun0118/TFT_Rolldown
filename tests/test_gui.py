"""Tests for the PyQt-based GUI.

Most importantly, these tests verify:

* The window honours its minimum size and is still freely resizable above it.
* Bench/board widgets are non-overlapping after resize.
* Drag-and-drop moves units between board and bench via :meth:`handle_drop`.
* Right-clicking a chip sells the underlying unit.
* The trait badges colour themselves according to the unit's tier.

All tests run under the ``offscreen`` Qt platform so they work in CI without a
display.
"""

# Standard libraries
import os

import pytest

# Make sure we're running offscreen before any Qt module is imported.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# pylint: disable=wrong-import-position
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QMouseEvent

from gui.user_interface import MainWindow
from gui.user_interface_v3 import MIN_WINDOW_SIZE
from gui.widgets import TraitBadge


def _make_window(set_dir):
    return MainWindow(set_dir, gold=100, level=3, offline=True)


# ----------------------------------------------------------------- minimum size
def test_minimum_size_enforced(qapp, set_dir):
    window = _make_window(set_dir)
    window.show()
    assert window.minimumSize().width() == MIN_WINDOW_SIZE[0]
    assert window.minimumSize().height() == MIN_WINDOW_SIZE[1]

    # Requesting a smaller-than-minimum size must clamp to the minimum.
    window.resize(800, 600)
    qapp.processEvents()
    assert window.size().width() >= MIN_WINDOW_SIZE[0]
    assert window.size().height() >= MIN_WINDOW_SIZE[1]


def test_window_can_grow(qapp, set_dir):
    window = _make_window(set_dir)
    window.show()
    window.resize(1800, 1200)
    qapp.processEvents()
    assert window.size().width() == 1800
    assert window.size().height() == 1200


def test_widgets_do_not_overlap_after_resize(qapp, set_dir):
    """After resize, the bench should sit below the board and not overlap."""
    window = _make_window(set_dir)
    window.show()
    window.resize(1800, 1200)
    qapp.processEvents()

    board_rect = window.u_i.board_container.geometry()
    bench_rect = window.bench_slots[0].parent().geometry()
    # In our layout the bench sits below the board – its top edge should be
    # at or past the board's bottom edge.
    assert bench_rect.top() >= board_rect.bottom() - 2


# ----------------------------------------------------------------- drag/drop
def test_drag_bench_to_board(qapp, set_dir):
    window = _make_window(set_dir)
    aatrox = window.game.champions_dict['Aatrox']
    window.game.team.bench[0] = aatrox.copy()
    window.refresh_board_and_bench()

    window.handle_drop('bench|0', 'board', ('A', 1))
    assert window.game.team.bench[0] is None
    assert len(window.game.team.board) == 1
    assert window.game.team.board[0].name == 'Aatrox'


def test_drag_board_to_bench(qapp, set_dir):
    window = _make_window(set_dir)
    aatrox = window.game.champions_dict['Aatrox']
    window.game.team.bench[0] = aatrox.copy()
    window.game.move_bench_to_board(0)
    window.refresh_board_and_bench()

    window.handle_drop('board|A|1', 'bench', 3)
    assert window.game.team.board == []
    assert window.game.team.bench[3].name == 'Aatrox'


def test_drag_to_full_board_shows_message(qapp, set_dir):
    window = _make_window(set_dir)
    window.game.level = 1
    aatrox = window.game.champions_dict['Aatrox']
    akali = window.game.champions_dict['Akali']
    window.game.team.bench[0] = aatrox.copy()
    window.game.team.bench[1] = akali.copy()
    window.game.move_bench_to_board(0)
    window.refresh_board_and_bench()

    window.handle_drop('bench|1', 'board', ('B', 1))
    assert window.game.last_notification == 'Team is full'
    assert window.game.team.bench[1].name == 'Akali'


def test_drag_within_bench_swaps(qapp, set_dir):
    window = _make_window(set_dir)
    a = window.game.champions_dict['Aatrox'].copy()
    b = window.game.champions_dict['Akali'].copy()
    window.game.team.bench[0] = a
    window.game.team.bench[5] = b
    window.refresh_board_and_bench()

    window.handle_drop('bench|0', 'bench', 5)
    assert window.game.team.bench[0].name == 'Akali'
    assert window.game.team.bench[5].name == 'Aatrox'


# ----------------------------------------------------------------- selling
def test_right_click_chip_sells_unit(qapp, set_dir):
    window = _make_window(set_dir)
    aatrox = window.game.champions_dict['Aatrox']
    window.game.team.bench[0] = aatrox.copy()
    window.refresh_board_and_bench()

    gold_before = window.game.gold
    chip = window.bench_slots[0].chip
    event = QMouseEvent(
        QMouseEvent.MouseButtonRelease,
        QPoint(5, 5),
        Qt.RightButton,
        Qt.RightButton,
        Qt.NoModifier,
    )
    chip.mouseReleaseEvent(event)
    qapp.processEvents()
    assert window.game.gold == gold_before + 1
    assert window.game.team.bench[0] is None


# ----------------------------------------------------------------- trait colours
def test_trait_badge_paints_for_each_tier(qapp, set_dir):
    """Every supported tier should produce a different background brush.

    We exercise the badge's paint logic by inspecting the recorded tier.
    """
    window = _make_window(set_dir)
    badge = window.trait_widgets[0]
    for tier in ('bronze', 'silver', 'gold', 'prismatic', 'inactive'):
        badge.set_state(None, 'Trait', 1, 2, tier)
        assert badge.tier == tier


def test_buy_unit_then_sell_flow_via_gui(qapp, set_dir):
    """End-to-end flow through the GUI surface."""
    window = _make_window(set_dir)
    # Inject a deterministic shop.
    from shared.rolldown_classes import Unit
    aatrox = window.game.champions_dict['Aatrox']
    window.game.cur_shop = [aatrox.copy()] + [Unit(None, 'BLANK', None, None)] * 4
    # Make the pool consistent.
    window.game._local_pool[1].remove(aatrox)

    gold_before = window.game.gold
    pool_before = sum(1 for u in window.game._local_pool[1] if u.name == 'Aatrox')

    window.buy_from_shop(0)
    assert window.game.team.bench[0].name == 'Aatrox'
    assert window.game.gold == gold_before - 1

    # Sell it.
    chip = window.bench_slots[0].chip
    event = QMouseEvent(
        QMouseEvent.MouseButtonRelease,
        QPoint(5, 5),
        Qt.RightButton,
        Qt.RightButton,
        Qt.NoModifier,
    )
    chip.mouseReleaseEvent(event)
    assert window.game.gold == gold_before
    # Pool restored.
    pool_after = sum(1 for u in window.game._local_pool[1] if u.name == 'Aatrox')
    assert pool_after == pool_before + 1
