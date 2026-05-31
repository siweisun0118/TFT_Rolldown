"""Main controller for the TFT-Rolldown PyQt GUI."""

# Standard libraries
from functools import partial
from pathlib import Path
import sys

# pylint: disable=no-name-in-module
from PyQt5.QtWidgets import QApplication, QMainWindow, QInputDialog
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QProcess, QTimer

# Local files
from shared.game import Game
from shared.image_utils import ensure_inverted_traits
from shared.rolldown_enums import LEVEL_EXP
from gui.user_interface_v3 import Ui_MainWindow


class MainWindow(QMainWindow):
    """Main UI Window."""

    def __init__(self, input_dir, gold=None, level=None, offline=False):
        super().__init__()
        self.input_dir = Path(input_dir)

        # Make sure trait icons are dark-on-transparent so they contrast
        # with the light board background.  Sentinel-guarded; no-op on
        # subsequent launches.
        ensure_inverted_traits(self.input_dir / 'traits')

        # Game state (may be None if the user cancels the prompt).
        self.game = None
        if gold is not None and level is not None:
            self.game = Game(str(self.input_dir), int(gold), int(level), offline=offline)
        else:
            self.take_inputs()

        # Build the UI.
        self.u_i = Ui_MainWindow()
        (
            self.shop_widgets,
            self.trait_widgets,
            self.board_tiles,
            self.bench_slots,
            self.controls,
        ) = self.u_i.setupUi(self)
        self.gold_label = self.controls['gold_label']
        self.level_label = self.controls['level_label']
        self.reroll_button = self.controls['reroll']
        self.level_up_button = self.controls['level_up']

        # Perf §1.4: cache trait pixmaps so we don't hit disk per redraw.
        self._trait_pix_cache = {}

        # Wire everything up.
        self.start_game()

    # ----------------------------------------------------------------- inputs
    def take_inputs(self):
        """Prompt the user for starting gold/level via QInputDialog."""
        gold, ok_gold = QInputDialog.getInt(self, 'Starting Gold', 'Enter starting gold:', 0, 0)
        level, ok_level = QInputDialog.getInt(
            self, 'Starting Level', 'Enter starting level (1-11 inclusive):', 1, 1, 11
        )
        if ok_gold and ok_level:
            self.game = Game(str(self.input_dir), int(gold), int(level))
        else:
            QApplication.quit()

    def start_game(self):
        """Bind UI signals to game actions and display the initial state."""
        for slot in self.shop_widgets:
            slot.leftClicked.connect(self.buy_from_shop)
            slot.rightClicked.connect(self.use_loaded_dice)

        self.reroll_button.clicked.connect(self.do_reroll)
        self.level_up_button.clicked.connect(self.do_buy_exp)

        # Click-to-sell wiring: clicking a chip with the right mouse button
        # sells the unit, mirroring the legacy behaviour.
        for tiles_row in self.board_tiles:
            for tile in tiles_row:
                chip = tile.chip
                chip.mouseReleaseEvent = partial(self._chip_clicked, chip)
        for slot in self.bench_slots:
            chip = slot.chip
            chip.mouseReleaseEvent = partial(self._chip_clicked, chip)

        # Display first shop and team.
        self.display_gold()
        self.display_exp()
        self.display_new_shop(first_roll=True)
        self.refresh_board_and_bench()
        self.refresh_traits()

        # The board's hex layout depends on the parent widget's size.  Qt
        # finalises layout after :meth:`show()`, so schedule a deferred
        # refresh once the window is fully laid out so the initial paint
        # uses the correct hex sizes.  Without this the very first frame
        # shows the board at its sizeHint() instead of the real geometry.
        QTimer.singleShot(0, self._post_show_layout)

    def _post_show_layout(self):
        """Re-run layout after the window has been shown so the board sizes
        the way it would after a reroll.
        """
        if hasattr(self.u_i, 'board') and self.u_i.board is not None:
            self.u_i.board.updateGeometry()
            self.u_i.board.adjustSize()
        # Trigger one more refresh in case the board chips needed real sizes
        # to render their splashes correctly.
        self.refresh_board_and_bench()

    # ---------------------------------------------------------------- helpers
    def _flash(self, message):
        """Display a transient non-blocking notification."""
        if hasattr(self.u_i, 'toast') and self.u_i.toast is not None:
            self.u_i.toast.show_message(message)
        else:
            self.statusBar().showMessage(message, 2000)

    def _pixmap_for_unit(self, unit):
        if unit is None or getattr(unit, 'name', '') == 'BLANK':
            return QPixmap()
        path = self.game.splash_path(unit) if self.game is not None else None
        if path is not None:
            return QPixmap(str(path))
        # Fallback: search the data directory directly.
        candidate = self.input_dir / 'champions' / f'{unit.name}.png'
        if not candidate.is_file():
            candidate = self.input_dir / 'champions' / f'{getattr(unit, "id_name", "") or ""}.png'
        if candidate.is_file():
            return QPixmap(str(candidate))
        return QPixmap()

    def _pixmap_for_trait(self, trait_name, size=32):
        """Return a cached scaled trait pixmap (perf §1.4)."""
        cached = self._trait_pix_cache.get((trait_name, size))
        if cached is not None:
            return cached
        candidate = self.input_dir / 'traits' / f'{trait_name}.png'
        if not candidate.is_file():
            pix = QPixmap()
        else:
            pix = QPixmap(str(candidate))
            if not pix.isNull():
                pix = pix.scaled(
                    size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
        self._trait_pix_cache[(trait_name, size)] = pix
        return pix

    # ------------------------------------------------------------- gold / exp
    def display_gold(self):
        self.gold_label.setText(f'Gold: {self.game.gold}')

    def display_exp(self):
        exp_max = LEVEL_EXP[self.game.level] if self.game.level in LEVEL_EXP else 0
        self.level_label.setText(
            f'Level: {self.game.level}   {self.game.exp} / {exp_max}'
        )

    # ----------------------------------------------------------------- shop
    def _shop_trait_pixmaps(self, unit):
        """Return a dict of small (18px) trait pixmaps for the shop overlay."""
        result = {}
        for trait in getattr(unit, 'traits', []):
            result[trait] = self._pixmap_for_trait(trait, size=18)
        return result

    def display_new_shop(self, first_roll=False, loaded_shop=None):
        if not first_roll:
            for unit in self.game.cur_shop or []:
                if unit.name != 'BLANK':
                    try:
                        self.game._send_sell_message(unit)
                    except Exception:  # noqa: BLE001 -- non-fatal during reroll
                        pass

        if loaded_shop is None:
            self.game.cur_shop = self.game.roll(first_roll)
        else:
            self.game.cur_shop = loaded_shop

        for idx, unit in enumerate(self.game.cur_shop):
            slot = self.shop_widgets[idx]
            slot.display(
                unit,
                self._pixmap_for_unit(unit),
                self._shop_trait_pixmaps(unit),
            )
        self._refresh_shop_glow()
        self.display_gold()

    def _refresh_shop_glow(self):
        """Re-add the "already owned" glow to shop slots for units already on the team."""
        owned_names = {u.name for u in self.game.team.all_units()}
        for slot in self.shop_widgets:
            unit = slot.unit
            slot.set_owned(unit is not None and unit.name in owned_names)

    def buy_from_shop(self, idx):
        success = self.game.buy_unit(idx + 1)
        if success:
            self.shop_widgets[idx].display(None)
            self.display_gold()
            self.refresh_board_and_bench()
            self.refresh_traits()
            self._refresh_shop_glow()
        elif self.game.last_notification:
            self._flash(self.game.last_notification)

    def use_loaded_dice(self, idx):
        unit = self.game.cur_shop[idx]
        if getattr(unit, 'name', 'BLANK') == 'BLANK':
            return
        loaded = self.game.loaded_dice(unit)
        self.display_new_shop(first_roll=True, loaded_shop=loaded)

    # ---------------------------------------------------------------- reroll
    def do_reroll(self):
        if self.game.gold < 2:
            return
        self.display_new_shop()

    def do_buy_exp(self):
        if self.game.gold < 4:
            return
        self.game.buy_exp()
        self.display_exp()
        self.display_gold()

    # ------------------------------------------------------------- board / bench display
    def refresh_board_and_bench(self):
        """Repaint every board hex and bench slot from ``self.game.team``."""
        positions = self.game.team.board_positions
        # Each board tile shows the unit at its (row, col) – may be None.
        for (row, col), tile in self.u_i.board_tiles_by_position.items():
            unit = positions.get((row, col))
            splash = self.game.splash_path(unit) if unit is not None else None
            tile.chip.set_unit(unit, splash_path=splash)

        for idx, slot in enumerate(self.bench_slots):
            unit = self.game.team.bench[idx] if idx < len(self.game.team.bench) else None
            splash = self.game.splash_path(unit) if unit is not None else None
            slot.chip.set_unit(unit, splash_path=splash)

    # --------------------------------------------------------------------- traits
    def refresh_traits(self):
        active = self.game.team.active_traits()
        for idx, badge in enumerate(self.trait_widgets):
            if idx < len(active):
                name, amount, target, tier = active[idx]
                pix = self._pixmap_for_trait(name, size=32)
                badge.set_state(pix if not pix.isNull() else None, name, amount, target, tier)
                badge.setVisible(True)
            else:
                badge.clear_state()
                badge.setVisible(False)

    # ------------------------------------------------------------------ DnD
    def handle_drop(self, payload, destination_kind, destination_idx):
        """Move a unit in response to a drop emitted by a chip.

        Source coordinates come from the payload set in
        :meth:`UnitChip.mouseMoveEvent`.  Destination coordinates come
        directly from the drop target (``destination_idx`` for the bench
        is an int; for the board it's the ``(row, col)`` tuple).
        """
        parts = payload.split('|')
        if not parts:
            return
        src_kind = parts[0]

        if src_kind == 'bench' and len(parts) == 2:
            try:
                src_index = int(parts[1])
            except ValueError:
                return
        elif src_kind == 'board' and len(parts) == 3:
            row, col = parts[1], parts[2]
            try:
                col_int = int(col)
            except ValueError:
                return
            src_index = (row, col_int)
            if src_index not in self.game.team.board_positions:
                return
        else:
            return

        result = False
        if src_kind == 'bench' and destination_kind == 'bench':
            result = self.game.team.move_within_bench(src_index, destination_idx)
        elif src_kind == 'bench' and destination_kind == 'board':
            result = self.game.move_bench_to_board(src_index, target_position=destination_idx)
        elif src_kind == 'board' and destination_kind == 'bench':
            result = self.game.move_board_to_bench(src_index, destination_idx)
        elif src_kind == 'board' and destination_kind == 'board':
            result = self.game.move_board_to_board(src_index, destination_idx)

        if not result and self.game.last_notification:
            self._flash(self.game.last_notification)

        self.refresh_board_and_bench()
        self.refresh_traits()
        self._refresh_shop_glow()

    # ------------------------------------------------------------------ clicks
    def _chip_clicked(self, chip, event):
        """Right-click chips to sell the underlying unit."""
        if chip.unit is None:
            return
        if event.button() == Qt.RightButton:
            if chip.slot_kind == 'board':
                self.game.sell_board_unit(chip.slot_index)
            else:
                self.game.sell_bench_unit(chip.slot_index)
            self.display_gold()
            self.refresh_board_and_bench()
            self.refresh_traits()
            self._refresh_shop_glow()

    # ----------------------------------------------------- keyboard shortcuts
    def keyReleaseEvent(self, event):  # noqa: N802 -- match Qt naming
        super().keyReleaseEvent(event)
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key_M:
            self.game.quit()
            QApplication.quit()
        elif event.key() == Qt.Key_D:
            self.do_reroll()
        elif event.key() == Qt.Key_F:
            self.do_buy_exp()
        elif event.key() == Qt.Key_P:
            QApplication.quit()
            QProcess.startDetached(sys.executable, sys.argv)


def main(input_dir):
    """Start the rolldown."""
    app = QApplication([input_dir])
    window = MainWindow(input_dir)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python -m gui.user_interface {input_dir}')
        sys.exit()
    main(sys.argv[1])
