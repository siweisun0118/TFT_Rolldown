"""Simulate a Rolldown"""


# Standard libraries
from functools import partial
from pathlib import Path
import sys


# pylint: disable=no-name-in-module
# Third party libraries
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QInputDialog
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtGui import QPixmap, QColor
from PyQt5.QtCore import Qt, QProcess


# Local files
from resources import GEN_ASSETS, LEVEL_EXP, Game, Unit, send_message
from user_interface_v3 import Ui_MainWindow, pathlib_path


class MainWindow(QMainWindow):
    """Main UI Window."""
    def __init__(self, input_dir):
        super().__init__()
        self.game = None

        # Input directory
        self.input_dir = Path(input_dir)

        # Take in inputs
        self.take_inputs()

        # Start main UI window
        self.u_i = Ui_MainWindow()

        # Access to UI widgets
        self.shop_widgets, self.traits, self.units, gold_level = self.u_i.setupUi(self)
        self.gold_label = gold_level[0]
        self.reroll_label = gold_level[1]
        self.level_label = gold_level[2]
        self.level_up = gold_level[3]

        # Attach trait labels to shop_widgets
        for idx, widget in enumerate(self.shop_widgets):
            # Unit can have up to 3 traits
            for i in range(3):
                splash_label = widget.findChild(QLabel, f'Shop_Icon_{idx + 1}')

                # Display trait icon
                trait_icon = QLabel(splash_label)
                trait_icon.setObjectName(f'Shop_Trait_Icon_{idx}_{i}')
                trait_icon.setFixedSize(20, 20)
                trait_icon.move(8, 25 + i * 40)
                trait_icon.setScaledContents(True)

                # Display trait name
                trait_label = QLabel(splash_label)
                trait_label.setStyleSheet('color: rgb(0, 255, 0); font-weight: bold')
                trait_label.setText('')
                trait_label.setObjectName(f'Shop_Trait_{idx}_{i}')
                trait_label.setFixedSize(80, 30)
                trait_label.move(30, 20 + i * 40)

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
            # Start new game using inputs from user
            while int(level) not in range(1, 12):
                level, _ = user_in.getText(self, 'input dialog',
                                                'Enter starting level (1-11 inclusive):')
            self.game = Game(self.input_dir, int(gold), int(level))
        else:
            QApplication.quit()

    def start_game(self):
        """Start the rolldown."""
        # Attach functionality to units in shop
        for idx, slot in enumerate(self.shop_widgets):
            # Buying and loaded dice functionality
            source = partial(self.shop_clicked, idx=idx)
            slot.mouseReleaseEvent = source

        # Attach reroll function to reroll button
        self.reroll_label.mouseReleaseEvent = self.reroll

        # Attach buying exp function to level-up button
        self.level_up.mouseReleaseEvent = self.buy_exp

        # Display first shop
        self.display_exp()
        self.display_new_shop(first_roll=True)

    # pylint: disable=unused-argument
    def reroll(self, event):
        """Reroll the shop."""
        # Check if roll is allowed
        if self.game.gold < 2:
            return

        # Display new shop
        self.display_new_shop()

    # pylint: disable=unused-argument
    def buy_exp(self, event):
        """Buy exp."""
        # Check if enough gold
        if self.game.gold < 4:
            return

        # Buy exp
        self.game.buy_exp()
        self.display_exp()
        self.display_gold()

    # pylint: disable=unused-argument, invalid-name
    def keyReleaseEvent(self, event):
        """Capture user input."""
        super().keyReleaseEvent(event)

        # Ensure that key is only registered once
        if event.isAutoRepeat():
            return

        # Quit
        if event.key() == Qt.Key_M:
            self.game.quit()
            QApplication.quit()

        # Reroll
        if event.key() == Qt.Key_D:
            self.reroll(event)

        # Level
        if event.key() == Qt.Key_F:
            self.buy_exp(event)

        # Restart
        if event.key() == Qt.Key_P:
            QApplication.quit()
            QProcess.startDetached(sys.executable, sys.argv)

    def display_gold(self):
        """Display the current gold/exp the player has."""
        self.gold_label.setText(f'Gold: {self.game.gold}')

    def display_exp(self):
        """Display the current level and exp the player has."""
        exp = f'Level: {self.game.level}  {self.game.exp} / {LEVEL_EXP[self.game.level]}'
        self.level_label.setText(exp)

    def display_new_shop(self, first_roll=False, loaded_shop=None):
        """Display the current shop."""
        # Assert that player has enough gold to roll
        assert first_roll or self.game.gold >= 2, 'ERROR: NOT ENOUGH GOLD TO ROLL'

        # Add previously rolled units back to the shop
        if not first_roll:
            for unit in self.game.cur_shop:
                if unit.name != 'BLANK':
                    send_message(self.game.client_socket, f'sell: {unit.name}: 1')

        # Roll for units
        if not loaded_shop:
            self.game.cur_shop = self.game.roll(first_roll)
        else:
            self.game.cur_shop = loaded_shop

        # Update gold
        self.display_gold()

        # Display rolled units
        for idx, unit in enumerate(self.game.cur_shop):
            # Display unit splash
            splash_label = self.shop_widgets[idx].findChild(QLabel, f'Shop_Icon_{idx + 1}')
            # Get name of file
            name = self.input_dir / 'champions' / f'{unit.name}.png'
            if not name.is_file():
                name = self.input_dir / 'champions' / f'{unit.id_name}.png'
            splash_label.setPixmap(QPixmap(str(name)))

            # Display unit rarity
            rarity_label = self.shop_widgets[idx].findChild(QLabel, f'Shop_Rarity_{idx + 1}')
            rarity = QPixmap(str(GEN_ASSETS / 'rarities' / f'{unit.rarity}.png'))
            rarity_label.setPixmap(rarity)

            # Display unit name
            name_label = self.shop_widgets[idx].findChild(QLabel, f'Shop_Name_{idx + 1}')
            name_label.setText(unit.name)

            # Display unit cost
            cost_label = self.shop_widgets[idx].findChild(QLabel, f'Shop_Cost_{idx + 1}')
            cost_label.setText(f'{unit.cost}G')

            # Display unit traits
            for i, trait in enumerate(unit.traits):
                # Display trait icon
                trait_icon = splash_label.findChild(QLabel, f'Shop_Trait_Icon_{idx}_{i}')
                icon = QPixmap(str(self.input_dir / 'traits' / f'{trait}.png'))
                trait_icon.setPixmap(icon)

                # Display trait name
                trait_label = splash_label.findChild(QLabel, f'Shop_Trait_{idx}_{i}')
                trait_label.setText(trait)

            # Only display as many traits as needed
            for i in range(len(unit.traits), 3):
                # Clear trait icon
                trait_icon = splash_label.findChild(QLabel, f'Shop_Trait_Icon_{idx}_{i}')
                trait_icon.setPixmap(QPixmap())

                # Clear trait name
                trait_label = splash_label.findChild(QLabel, f'Shop_Trait_{idx}_{i}')
                trait_label.setText('')

            # Add glow effect if a copy of the unit is already owned
            if unit in self.game.team:
                glow1 = get_glow_effect()
                glow2 = get_glow_effect()
                splash_label.setGraphicsEffect(glow1)
                rarity_label.setGraphicsEffect(glow2)
            else:
                no_glow1 = get_no_glow_effect()
                no_glow2 = get_no_glow_effect()
                splash_label.setGraphicsEffect(no_glow1)
                rarity_label.setGraphicsEffect(no_glow2)

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
            source = partial(self.unit_clicked, idx=idx)
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
            stats_widget.setText(f'{trait_name[:7]} {trait_breakpoints}')

        # White out remaining slots
        for slot in range(len(traits), 18):
            # White out icon
            icon_widget = self.traits[slot].findChild(QLabel, f'Trait_Icon_{slot + 1}')
            icon_widget.setPixmap(QPixmap(pathlib_path(GEN_ASSETS, 'white.png')))

            # White out star level
            stats_widget = self.traits[slot].findChild(QLabel, f'Trait_Amount_{slot + 1}')
            stats_widget.setText('   ')

    def display_loaded_dice(self, unit):
        """Replace shop with loaded dice rolls (idx is 0-indexed)."""
        assert isinstance(unit, Unit)
        result = self.game.loaded_dice(unit)
        self.display_new_shop(first_roll=True, loaded_shop=result)

    def shop_clicked(self, event, idx):
        """Determine whether to buy unit or use loaded dice."""
        if event.button() == Qt.LeftButton:
            self.buy_unit(event, idx)
        elif event.button() == Qt.RightButton:
            self.display_loaded_dice(self.game.cur_shop[idx])

    def unit_clicked(self, event, idx):
        """Determine whether to sell unit or use loaded dice."""
        if event.button() == Qt.LeftButton:
            self.sell_unit(event, idx)
        elif event.button() == Qt.RightButton:
            self.display_loaded_dice(self.game.team.team[idx])

    def buy_unit(self, event, idx):
        """Buy a unit from the shop (idx is 0-indexed)."""
        assert isinstance(idx, int)
        # Add unit to team
        # Cannot purchase empty slots
        if self.game.cur_shop[idx].name == 'BLANK':
            return

        # Check if enough gold is available to purchase the unit
        if self.game.gold < self.game.cur_shop[idx].cost:
            return

        # Add unit to team (shop needs to be 1-indexed)
        bought_unit = self.game.cur_shop[idx].copy()
        self.game.buy_unit(idx + 1)

        # Add glowing effect to other copies of the unit in shop
        for i, unit in enumerate(self.game.cur_shop):
            if unit == bought_unit:
                # Glow effect
                glow1 = get_glow_effect()
                glow2 = get_glow_effect()

                # Add glow effect to slot
                splash = self.shop_widgets[i].findChild(QLabel, f'Shop_Icon_{i + 1}')
                rarity = self.shop_widgets[i].findChild(QLabel, f'Shop_Rarity_{i + 1}')
                splash.setGraphicsEffect(glow1)
                rarity.setGraphicsEffect(glow2)

        # Replace labels
        for widget in self.shop_widgets[idx].children():
            if isinstance(widget, QLabel):
                # Clear out 'glow' effect from splash art
                if widget.pixmap():
                    no_glow = get_no_glow_effect()
                    widget.setGraphicsEffect(no_glow)

                # Replace slot with blank
                widget.setPixmap(QPixmap(pathlib_path(GEN_ASSETS, 'blank.png')))

                # Clear out trait information
                for child in widget.children():
                    child.setPixmap(QPixmap())

        # Update gold count
        self.display_gold()

        # Update units
        self.display_team()

        # Update traits
        self.display_traits()

    def sell_unit(self, event, idx):
        """Sell a unit from the team."""
        # Remove glow effect from shop, if applicable
        sold_unit = self.game.team.team[idx]
        for i, unit in enumerate(self.game.cur_shop):
            if unit == sold_unit:
                # Glow effect
                glow1 = get_no_glow_effect()
                glow2 = get_no_glow_effect()

                # Add glow effect to slot
                splash = self.shop_widgets[i].findChild(QLabel, f'Shop_Icon_{i + 1}')
                rarity = self.shop_widgets[i].findChild(QLabel, f'Shop_Rarity_{i + 1}')
                splash.setGraphicsEffect(glow1)
                rarity.setGraphicsEffect(glow2)

        # Sell unit
        self.game.sell_unit(idx)

        # Update gold count
        self.display_gold()

        # Update units
        self.display_team()

        # Update traits
        self.display_traits()


def get_glow_effect():
    """Generate an instance of the 'glow' effect."""
    glow = QGraphicsDropShadowEffect()
    glow.setOffset(15, 10)
    glow.setBlurRadius(60)
    glow.setColor(QColor(230, 230, 230, 255))

    return glow


def get_no_glow_effect():
    """Generate an instance of the 'no glow' effect."""
    no_glow = QGraphicsDropShadowEffect()
    no_glow.setColor(QColor(0, 0, 0, 255))

    return no_glow


def main(input_dir):
    """Start the rolldown."""
    app = QApplication([input_dir])

    window = MainWindow(input_dir)
    window.setFixedSize(window.size())
    window.move(0, 0)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python user_interface_test.py {input_dir}')
        sys.exit()

    main(sys.argv[1])
