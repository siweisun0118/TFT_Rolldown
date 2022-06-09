"""Simulate a Rolldown"""

import sys
from pathlib import Path
from functools import partial


from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QInputDialog
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QProcess
from numpy import isin


from user_interface_v3 import Ui_MainWindow, pathlib_path
from rolldown import Game, Unit
from constants import GEN_ASSETS


class MainWindow(QMainWindow):
    """Main UI Window."""
    def __init__(self, input_dir):
        super(MainWindow, self).__init__()
        self.game = None

        # Input directory
        self.input_dir = Path(input_dir)

        # Take in inputs
        self.take_inputs()

        # Start main UI window
        self.ui = Ui_MainWindow()

        # Access to UI widgets
        self.shop_widgets, self.traits, self.units, gold_level = self.ui.setupUi(self, input_dir)
        self.gold_label = gold_level[0]
        self.reroll_label = gold_level[1]

        # Current shop
        self.cur_shop = None

        # Start the rolldown
        self.start_game()

    def take_inputs(self):
        """Take in inputs from user."""
        user_in = QInputDialog()
        gold, done1 = user_in.getText(self, 'input dialog', 'Enter starting gold:')
        level, done2 = user_in.getText(self, 'input dialog',
            'Enter starting level (1-11 inclusive):')
        if done1 and done2:
            # Start new game using inputs from user
            while int(level) not in range(1, 12):
                level, _ = user_in.getText(self, 'input dialog',
                                                'Enter starting level (1-11 inclusive):')
            self.game = Game(sys.argv[1], int(gold), int(level))
        else:
            QApplication.quit()

    def start_game(self):
        """Start the rolldown."""
        # Attach buy function to units in shop
        for idx, slot in enumerate(self.shop_widgets):
            source = partial(self.buy_unit, idx=idx)
            slot.mouseReleaseEvent = source

        # Attach reroll function to reroll button
        # TODO: Implement leveling up
        self.reroll_label.mouseReleaseEvent = self.reroll

        # Display first shop
        self.display_new_shop(first_roll=True)

    def reroll(self, event):
        """Reroll the shop."""
        # Check if roll is allowed
        if self.game.gold < 2:
            return

        # Display new shop
        self.display_new_shop()

    def keyReleaseEvent(self, event):
        """Capture user input."""
        super().keyReleaseEvent(event)

        # Ensure that key is only registered once
        if event.isAutoRepeat():
            return

        # Quit
        if event.key() == Qt.Key_M:
            print(self.game)
            QApplication.quit()

        # Reroll
        if event.key() == Qt.Key_D:
            self.reroll(event)

        # Restart
        if event.key() == Qt.Key_P:
            QApplication.quit()
            QProcess.startDetached(sys.executable, sys.argv)

    def display_gold(self):
        """Display the current gold/exp the player has."""
        self.gold_label.setText(f'Gold: {self.game.gold}')

    def display_new_shop(self, first_roll=False):
        """Display the current shop."""
        # Assert that player has enough gold to roll
        assert first_roll or self.game.gold >= 2, 'ASSERTION ERROR: NOT ENOUGH GOLD TO ROLL'

        # Roll for units
        self.cur_shop = self.game.roll(first_roll)

        # Update gold
        self.display_gold()

        # Display rolled units
        for idx, unit in enumerate(self.cur_shop):
            # Display unit splash
            splash_label = self.shop_widgets[idx].findChild(QLabel, f'Shop_Icon_{idx + 1}')
            # Get name of file
            name = self.input_dir / 'champions' / f'{unit.name}.png'
            if not name.is_file():
                name = self.input_dir / 'champions' / f'{unit.id_name}.png'
            splash = QPixmap(str(name))
            splash_label.setPixmap(splash)

            # Display unit rarity
            rarity_label = self.shop_widgets[idx].findChild(QLabel, f'Shop_Rarity_{idx + 1}')
            rarity = QPixmap(str(GEN_ASSETS / 'rarities' / f'{unit.cost}.png'))
            rarity_label.setPixmap(rarity)

            # Display unit name
            name_label = self.shop_widgets[idx].findChild(QLabel, f'Shop_Name_{idx + 1}')
            name_label.setText(unit.name)

            # Display unit cost
            cost_label = self.shop_widgets[idx].findChild(QLabel, f'Shop_Cost_{idx + 1}')
            cost_label.setText(f'{unit.cost}G')

    def display_team(self):
        """Displays all the units currently bought."""
        # For every unit on the team
        for idx, unit in enumerate(self.game.team.team):
            # Can't display more than 18 units at once
            if idx > 17:
                return

            # Find the icon widget
            icon_widget = self.units[idx].findChild(QLabel, f'Unit_Icon_{idx + 1}')

            # Get the splash
            name = self.input_dir / 'champions' / f'{unit.name}.png'
            if not name.is_file():
                name = self.input_dir / 'champions' / f'{unit.id_name}.png'
            splash = QPixmap(str(name))

            # Set label to splash
            icon_widget.setPixmap(splash)

            # Find the star level text widget
            stats_widget = self.units[idx].findChild(QLabel, f'Unit_Stats_{idx + 1}')

            # Display correct information
            stats_widget.setText(f'{unit.level} Star')

            # Attach selling functionality
            source = partial(self.sell_unit, idx=idx)
            self.units[idx].mouseReleaseEvent = source

        # White out remaining slots
        for slot in range(len(self.game.team), 18):
            # White out icon
            icon_widget = self.units[slot].findChild(QLabel, f'Unit_Icon_{slot + 1}')
            icon_widget.setPixmap(QPixmap(pathlib_path(GEN_ASSETS, 'white.png')))

            # White out star level
            stats_widget = self.units[slot].findChild(QLabel, f'Unit_Stats_{slot + 1}')
            stats_widget.setText('')

            # Remove selling functionality
            self.units[slot].mouseReleaseEvent = None

    def display_traits(self):
        """Display the current traits on the team."""
        # For every trait on the team
        traits = self.game.team.get_traits()
        for idx, trait in enumerate(traits):
            # Can't display more than 18 traits at once
            if idx > 17:
                return

            # Find the icon widget
            icon_widget = self.traits[idx].findChild(QLabel, f'Trait_Icon_{idx + 1}')

            # Get the icon
            trait_name, trait_breakpoints = trait.split(' ', 1)
            name = self.input_dir / 'traits' / f'{trait_name}.png'
            splash = QPixmap(str(name))

            # Set label to splash
            icon_widget.setPixmap(splash)

            # Find the star level text widget
            stats_widget = self.traits[idx].findChild(QLabel, f'Trait_Amount_{idx + 1}')

            # Display correct information
            stats_widget.setText(trait_breakpoints)

        # White out remaining slots
        for slot in range(len(traits), 18):
            # White out icon
            icon_widget = self.traits[slot].findChild(QLabel, f'Trait_Icon_{slot + 1}')
            icon_widget.setPixmap(QPixmap(pathlib_path(GEN_ASSETS, 'white.png')))

            # White out star level
            stats_widget = self.traits[slot].findChild(QLabel, f'Trait_Amount_{slot + 1}')
            stats_widget.setText('   ')

    def buy_unit(self, event, idx):
        """Buy a unit from the shop."""
        assert isinstance(idx, int)

        # Add unit to team
        # Cannot purchase empty slots
        if self.cur_shop[idx].name == 'BLANK':
            return

        # Check if enough gold is available to purchase the unit
        if self.game.gold < self.cur_shop[idx].cost:
            return

        # Add unit to team (shop needs to be 1-indexed)
        self.game.buy_unit(self.cur_shop, idx + 1)

        # Replace unit with blank
        self.cur_shop[idx] = Unit(None, 'BLANK', None, None)

        # Replace labels
        for widget in self.shop_widgets[idx].children():
            if isinstance(widget, QLabel):
                widget.setPixmap(QPixmap(pathlib_path(GEN_ASSETS, 'blank.png')))

        # Update gold count
        self.display_gold()

        # Update units
        self.display_team()

        # Update traits
        self.display_traits()

    def sell_unit(self, event, idx):
        """Sell a unit from the team."""
        self.game.sell_unit(idx)

        # Update gold count
        self.display_gold()

        # Update units
        self.display_team()

        # Update traits
        self.display_traits()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python user_interface_test.py {input_dir}')
        sys.exit()

    app = QApplication(sys.argv)

    window = MainWindow(sys.argv[1])
    window.setFixedSize(window.size())
    window.showMaximized()

    sys.exit(app.exec())
