"""Simulate a Rolldown (graphical interface)."""


# Standard libraries
from functools import partial
from pathlib import Path
import sys


# pylint: disable=no-name-in-module
# Third party libraries
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QInputDialog
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QProcess


# Local files
from shared.networking_client import send_bulk
from shared.rolldown_enums import GEN_ASSETS, LEVEL_EXP
from shared.game import Game
from shared.image_utils import invert_trait_icons
from gui.user_interface_v3 import Ui_MainWindow


class MainWindow(QMainWindow):
    """Main UI Window."""
    def __init__(self, input_dir, game=None, invert=True):
        super().__init__()
        self.game = game

        # Input directory
        self.input_dir = Path(input_dir)

        # Make the (white-on-transparent) trait icons visible. Safe to call on
        # every startup and works for current and future sets.
        if invert:
            invert_trait_icons(self.input_dir)

        # Take in inputs (skipped when a game is injected, e.g. by tests).
        if self.game is None:
            self.take_inputs()

        # Start main UI window
        self.u_i = Ui_MainWindow()
        handles = self.u_i.setupUi(self, self.handle_drop)

        self.shop_widgets = handles['shop']
        self.shop_area = handles['shop_area']
        self.board_widget = handles['board']
        self.bench_widget = handles['bench']
        self.trait_column = handles['traits']
        self.gold_label = handles['gold_label']
        self.level_label = handles['level_label']
        self.level_up = handles['level_up']
        self.reroll_label = handles['reroll']
        self.message = handles['message']

        # Right-click an owned unit to sell it; refresh after every drag so a
        # cancelled drag never leaves a unit looking stuck.
        for cell in self.board_widget.cells.values():
            cell.right_click_handler = self.sell_cell
            cell.refresh_hook = self.refresh_team
        for cell in self.bench_widget.cells:
            cell.right_click_handler = self.sell_cell
            cell.refresh_hook = self.refresh_team

        # Cache pixmaps so they are not re-read from disk every redraw (1.6).
        self._pixmap_cache = {}

        # Start the rolldown
        self.start_game()

    def take_inputs(self):
        """Take in inputs from user."""
        user_in = QInputDialog()
        user_in.setWindowState(Qt.WindowActive)
        gold, done1 = user_in.getText(self, 'input dialog', 'Enter starting gold:')
        level, done2 = user_in.getText(self, 'input dialog',
            'Enter starting level (1-11 inclusive):')
        if done1 and done2:
            while int(level) not in range(1, 12):
                level, _ = user_in.getText(self, 'input dialog',
                                           'Enter starting level (1-11 inclusive):')
            self.game = Game(self.input_dir, int(gold), int(level))
        else:
            QApplication.quit()

    def start_game(self):
        """Start the rolldown."""
        for idx, slot in enumerate(self.shop_widgets):
            slot.mouseReleaseEvent = partial(self.shop_clicked, idx=idx)

        self.reroll_label.mouseReleaseEvent = self.reroll
        self.level_up.mouseReleaseEvent = self.buy_exp

        self.display_exp()
        self.display_new_shop(first_roll=True)
        self.refresh_team()

    # region shop
    # pylint: disable=unused-argument
    def reroll(self, event):
        """Reroll the shop."""
        if self.game.gold < 2:
            return
        self.display_new_shop()

    # pylint: disable=unused-argument
    def buy_exp(self, event):
        """Buy exp."""
        if self.game.gold < 4:
            return
        self.game.buy_exp()
        self.display_exp()
        self.display_gold()

    # pylint: disable=unused-argument, invalid-name
    def keyReleaseEvent(self, event):
        """Capture user input."""
        super().keyReleaseEvent(event)
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key_M:
            self.game.quit()
            QApplication.quit()
        if event.key() == Qt.Key_D:
            self.reroll(event)
        if event.key() == Qt.Key_F:
            self.buy_exp(event)
        if event.key() == Qt.Key_P:
            QApplication.quit()
            QProcess.startDetached(sys.executable, sys.argv)

    def display_gold(self):
        """Display the current gold the player has."""
        self.gold_label.setText(f'Gold: {self.game.gold}')

    def display_exp(self):
        """Display the current level and exp the player has."""
        exp = f'Level: {self.game.level}  {self.game.exp} / {LEVEL_EXP[self.game.level]}'
        self.level_label.setText(exp)

    def _cached_pixmap(self, key, path):
        """Load ``path`` once and reuse the QPixmap (1.6)."""
        pix = self._pixmap_cache.get(key)
        if pix is None:
            pix = QPixmap(str(path))
            self._pixmap_cache[key] = pix
        return pix

    def _unit_pixmap(self, unit):
        """Return the (cached) splash pixmap for ``unit``."""
        name = self.input_dir / 'champions' / f'{unit.name}.png'
        if not name.is_file():
            name = self.input_dir / 'champions' / f'{unit.id_name}.png'
        return self._cached_pixmap(f'champ:{unit.name}', name)

    def _trait_pixmap(self, trait_name):
        """Return the (cached, inverted) icon pixmap for a trait."""
        return self._cached_pixmap(
            f'trait:{trait_name}', self.input_dir / 'traits' / f'{trait_name}.png')

    def display_new_shop(self, first_roll=False, loaded_shop=None):
        """Display the current shop."""
        assert first_roll or self.game.gold >= 2, 'ERROR: NOT ENOUGH GOLD TO ROLL'

        if not first_roll:
            # Return the previous shop to the pool in one batched round-trip.
            back = [{'op': 'sell', 'name': u.name, 'level': 1}
                    for u in self.game.cur_shop if u.name != 'BLANK']
            if back:
                send_bulk(self.game.client_socket, back)

        if not loaded_shop:
            self.game.cur_shop = self.game.roll(first_roll)
        else:
            self.game.cur_shop = loaded_shop

        self.display_gold()
        self._render_shop()

    def _render_shop(self):
        """Repaint shop slots, highlighting units a copy of which is owned."""
        owned_names = {u.name for u in self.game.team.all_units()}
        for idx, unit in enumerate(self.game.cur_shop):
            slot = self.shop_widgets[idx]
            splash = self.shop_area.splashes[idx]
            rarity = slot.findChild(QLabel, f'Shop_Rarity_{idx + 1}')
            name_label = slot.findChild(QLabel, f'Shop_Name_{idx + 1}')
            cost_label = slot.findChild(QLabel, f'Shop_Cost_{idx + 1}')

            if unit.name == 'BLANK':
                splash.clear()
                rarity.setPixmap(QPixmap())
                name_label.setText('')
                cost_label.setText('')
                continue

            # Resize-safe per-unit trait sub-icons (name + inverted icon).
            traits = [(trait, self._trait_pixmap(trait)) for trait in unit.traits]
            splash.set_unit(self._unit_pixmap(unit), traits,
                            owned=unit.name in owned_names)
            rarity.setPixmap(
                QPixmap(str(GEN_ASSETS / 'rarities' / f'{unit.rarity}.png')))
            name_label.setText(unit.name)
            cost_label.setText(f'{unit.cost}G')

    def shop_clicked(self, event, idx):
        """Left-click buys a unit (right-click does nothing in the shop)."""
        if event.button() == Qt.LeftButton:
            self.buy_unit(idx)

    def buy_unit(self, idx):
        """Buy the unit in shop slot ``idx`` (0-indexed)."""
        result = self.game.buy_unit(idx + 1)
        if result == 'bench_full':
            self.message.flash('Bench is full!')
            return
        if result != 'ok':
            return

        # An auto-buy+upgrade can blank several slots, so repaint them all.
        self._render_shop()
        self.display_gold()
        self.refresh_team()

    def sell_cell(self, cell):
        """Sell the unit in a board/bench cell (right-click)."""
        kind, value = self._parse_location(cell.location)
        if kind == 'bench':
            self.game.sell_bench(value)
        else:
            self.game.sell_board(value)
        self.display_gold()
        self.refresh_team()
    # endregion

    # region board / bench / traits rendering
    def refresh_team(self):
        """Redraw the board, bench and traits from the game state."""
        team = self.game.team

        for (row, col), cell in self.board_widget.cells.items():
            unit = team.board.get((row, col))
            cell.set_unit(unit, self._unit_pixmap(unit) if unit else None)

        for idx, cell in enumerate(self.bench_widget.cells):
            unit = team.bench[idx]
            cell.set_unit(unit, self._unit_pixmap(unit) if unit else None)

        self.display_traits()

    def display_traits(self):
        """Render the trait column, ordered by closeness to next breakpoint."""
        self.trait_column.clear()
        team = self.game.team
        # Team.sorted_traits already orders by closeness and uses the "show
        # the next breakpoint once a breakpoint is hit" target rule.
        for trait_name, amount, target in team.sorted_traits():
            trait = self.game.traits_dict.get(trait_name)
            if trait is None:
                continue
            tier = trait.style_tier(amount)
            icon = self._trait_pixmap(trait_name)
            self.trait_column.add_trait(icon, trait_name,
                                        f'{amount} / {target}', tier)
    # endregion

    # region drag and drop
    @staticmethod
    def _parse_location(text):
        """Parse 'bench:3' / 'board:1,2' / 'shop' into a tuple."""
        if text == 'shop':
            return ('shop', None)
        kind, value = text.split(':', 1)
        if kind == 'bench':
            return ('bench', int(value))
        row, col = value.split(',')
        return ('board', (int(row), int(col)))

    def handle_drop(self, source_text, target_text):
        """Move or sell a unit in response to a drag-and-drop."""
        source = self._parse_location(source_text)
        target = self._parse_location(target_text)
        team = self.game.team

        # Dropping a unit on the shop sells it.
        if target[0] == 'shop':
            if source[0] == 'bench':
                self.game.sell_bench(source[1])
            else:
                self.game.sell_board(source[1])
            self.display_gold()
            self.refresh_team()
            return

        ok = True
        if source[0] == 'bench' and target[0] == 'bench':
            team.move_within_bench(source[1], target[1])
        elif source[0] == 'bench' and target[0] == 'board':
            ok = team.move_bench_to_board(source[1], target[1])
        elif source[0] == 'board' and target[0] == 'bench':
            ok = team.move_board_to_bench(source[1], target[1])
        elif source[0] == 'board' and target[0] == 'board':
            ok = team.move_within_board(source[1], target[1])

        if not ok:
            self.message.flash('Team is full!')

        self.refresh_team()
    # endregion


def main(input_dir):
    """Start the rolldown."""
    app = QApplication([input_dir])

    window = MainWindow(input_dir)
    window.move(0, 0)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python user_interface.py {input_dir}')
        sys.exit()

    main(sys.argv[1])
