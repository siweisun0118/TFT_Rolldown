"""GUI: resizability, single trait column, drag-to-sell, transient message."""

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt, QSize  # noqa: E402

from conftest import SET_DIR  # noqa: E402


@pytest.fixture
def window(qapp, game):
    from gui.user_interface import MainWindow

    win = MainWindow(str(SET_DIR), game=game, invert=False)
    yield win
    win.close()


def test_window_has_minimum_size_and_is_resizable(window, qapp):
    assert window.minimumSize() == QSize(1366, 973)
    # Not pinned to a fixed size (the old code called setFixedSize).
    assert window.maximumWidth() > 1366
    assert window.maximumHeight() > 973

    window.resize(1700, 1200)
    window.show()
    qapp.processEvents()
    assert window.width() >= 1366 and window.height() >= 973


def test_components_do_not_overlap_after_resize(window, qapp):
    window.resize(1800, 1250)
    window.show()
    qapp.processEvents()

    board = window.board_widget.geometry()
    bench = window.bench_widget.geometry()
    shop = window.shop_area.geometry()
    traits = window.trait_column.geometry()

    # Stacked vertically with no overlap and no gaps swallowing a component.
    assert board.bottom() <= bench.top() + 1
    assert bench.bottom() <= shop.top() + 1
    # Trait column sits to the left of the board (barely touching it).
    assert traits.right() <= board.left() + 1
    assert window.board_widget.width() > 0 and window.board_widget.height() > 0


def test_board_hexes_repositioned_within_widget(window, qapp):
    window.resize(1700, 1200)
    window.show()
    qapp.processEvents()

    cells = window.board_widget.cells
    w = window.board_widget.width()
    h = window.board_widget.height()
    for (row, col), cell in cells.items():
        g = cell.geometry()
        assert g.left() >= -1 and g.top() >= -1
        assert g.right() <= w + 1 and g.bottom() <= h + 1

    # Interlocking: odd rows are offset to the right of even rows.
    even = cells[(0, 0)].geometry().left()
    odd = cells[(1, 0)].geometry().left()
    assert odd > even


def test_single_trait_column_with_tier_background(window, qapp):
    name = next(iter(window.game.champions_dict))
    trait = window.game.champions_dict[name].traits[0]
    window.game.team.bench[0] = window.game.champions_dict[name].copy()
    window.game.team.move_bench_to_board(0, (0, 0))
    window.refresh_team()
    qapp.processEvents()

    # At least one trait row exists (count - 1 because of the stretch item).
    assert window.trait_column.vbox.count() - 1 >= 1
    row = window.trait_column.vbox.itemAt(0).widget()
    icon = row.findChildren(type(row))  # frame children
    assert window.game.team.traits.get(trait) == 1


def test_drag_unit_onto_shop_sells_it(window, qapp):
    name = next(n for n, u in window.game.champions_dict.items() if u.cost == 1)
    window.game.team.bench[0] = window.game.champions_dict[name].copy()
    window.refresh_team()
    gold_before = window.game.gold

    window.handle_drop("bench:0", "shop")
    qapp.processEvents()

    assert window.game.team.bench[0] is None
    assert window.game.gold > gold_before


def test_drag_between_bench_and_board(window, qapp):
    name = next(iter(window.game.champions_dict))
    window.game.team.bench[2] = window.game.champions_dict[name].copy()
    window.refresh_team()

    window.handle_drop("bench:2", "board:0,0")
    qapp.processEvents()
    assert (0, 0) in window.game.team.board
    assert window.game.team.bench[2] is None

    window.handle_drop("board:0,0", "bench:5")
    qapp.processEvents()
    assert window.game.team.bench[5].name == name
    assert (0, 0) not in window.game.team.board


def test_shop_trait_overlay_is_resize_safe(window, qapp):
    from shared.rolldown_enums import SHOP_SLOTS

    splashes = window.shop_area.splashes
    assert len(splashes) == SHOP_SLOTS

    # After a roll every non-blank slot carries its unit's traits, and the
    # overlay uses no fixed geometry (no setFixedSize / move()).
    found = False
    for idx, unit in enumerate(window.game.cur_shop):
        splash = splashes[idx]
        if unit.name == 'BLANK':
            continue
        found = True
        names = [n for n, _ in splash._traits]
        assert names == list(unit.traits)
        assert splash.maximumSize().width() >= 16777215  # not fixed-size
    assert found

    # Repaint at several sizes without error; trait data is size-independent.
    snapshot = list(splashes[0]._traits)
    for size in ((160, 120), (420, 300), (90, 70)):
        window.shop_area.splashes[0].resize(*size)
        window.shop_area.splashes[0].repaint()
        qapp.processEvents()
    assert splashes[0]._traits == snapshot


def test_star_level_border_colors_are_distinct(qapp):
    from gui.user_interface_v3 import star_color

    c1, c2, c3 = star_color(1), star_color(2), star_color(3)
    assert c1.name() != c2.name() != c3.name()
    assert c1.name() != c3.name()


def test_shop_highlights_owned_copies(window, qapp):
    # Force a known shop and own a copy of the first shop unit.
    name = next(u.name for u in window.game.cur_shop if u.name != 'BLANK')
    window.game.team.bench[0] = window.game.champions_dict[name].copy()
    window._render_shop()
    qapp.processEvents()

    owned_flags = {}
    for idx, unit in enumerate(window.game.cur_shop):
        if unit.name == 'BLANK':
            continue
        owned_flags[idx] = window.shop_area.splashes[idx]._owned

    highlighted = [i for i, u in enumerate(window.game.cur_shop)
                   if u.name == name]
    for i in highlighted:
        assert window.shop_area.splashes[i]._owned is True


def test_reroll_and_exp_are_left_of_shop_exp_on_top(window, qapp):
    window.resize(1500, 1050)
    window.show()
    qapp.processEvents()

    shop_left = window.shop_area.mapTo(window, window.shop_area.rect().topLeft()).x()
    lvl = window.level_up
    rer = window.reroll_label
    lvl_pt = lvl.mapTo(window, lvl.rect().topLeft())
    rer_pt = rer.mapTo(window, rer.rect().topLeft())

    # Both controls sit to the left of the shop strip.
    assert lvl_pt.x() < shop_left
    assert rer_pt.x() < shop_left
    # Buy-exp (level up) is above reroll.
    assert lvl_pt.y() < rer_pt.y()


def test_right_click_sells_unit(window, qapp):
    name = next(n for n, u in window.game.champions_dict.items() if u.cost == 1)
    window.game.team.bench[3] = window.game.champions_dict[name].copy()
    window.refresh_team()
    gold_before = window.game.gold

    cell = window.bench_widget.cells[3]
    window.sell_cell(cell)
    qapp.processEvents()

    assert window.game.team.bench[3] is None
    assert window.game.gold > gold_before


def test_sell_zone_hint_is_visible(window, qapp):
    assert 'SELL' in window.shop_area.sell_hint.text().upper()


def test_drag_move_leaves_no_ghost_in_source(window, qapp):
    name = next(iter(window.game.champions_dict))
    window.game.team.bench[2] = window.game.champions_dict[name].copy()
    window.refresh_team()

    window.handle_drop("bench:2", "board:0,0")
    qapp.processEvents()

    # Source bench cell must no longer show the unit (no frozen ghost).
    assert window.bench_widget.cells[2].unit is None
    assert window.bench_widget.cells[2]._pixmap is None
    assert (0, 0) in window.game.team.board


def test_trait_stylesheets_parse_cleanly(window, qapp):
    """No 'Could not parse stylesheet' Qt warnings for any trait tier."""
    from PyQt5.QtCore import qInstallMessageHandler

    messages = []
    old = qInstallMessageHandler(lambda mode, ctx, msg: messages.append(msg))
    try:
        # Put enough units on the board to activate several traits/tiers.
        names = list(window.game.champions_dict)[:8]
        for i, n in enumerate(names):
            window.game.team.bench[i] = window.game.champions_dict[n].copy()
        for i in range(8):
            window.game.team.move_bench_to_board(i, (i % 2, i // 2))
        window.refresh_team()
        qapp.processEvents()
    finally:
        qInstallMessageHandler(old)

    bad = [m for m in messages if 'Could not parse stylesheet' in m]
    assert not bad, bad

    # Every trait icon stylesheet must have balanced braces.
    from PyQt5.QtWidgets import QLabel

    col = window.trait_column
    for i in range(col.vbox.count() - 1):
        row = col.vbox.itemAt(i).widget()
        if row is None:
            continue
        for lab in row.findChildren(QLabel):
            ss = lab.styleSheet()
            assert ss.count('{') == ss.count('}'), ss


def test_controls_have_no_black_panel_background(window):
    # The reroll / buy-exp column must not paint an opaque black panel.
    box = window.level_up.parentWidget()
    assert 'black' not in box.styleSheet()


def test_loaded_dice_removed(window):
    # Loaded-dice functionality is gone from the controller and model.
    assert not hasattr(window, 'display_loaded_dice')
    assert not hasattr(window, 'cell_loaded_dice')
    assert not hasattr(window.game, 'loaded_dice')


def test_transient_message_is_non_blocking(window, qapp):
    window.show()
    window.message.flash("Bench is full!", msecs=500)
    qapp.processEvents()
    assert window.message.isVisible()
    assert window.message.text() == "Bench is full!"
    # Non-interactive: it ignores mouse events and is not a modal dialog.
    assert window.message.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert not window.message.isModal()
