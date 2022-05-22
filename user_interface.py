"""Implmentation of the PyQt UI for rolldown."""


# Standard libraries
from functools import partial
import sys
from os.path import exists


# Qt libraries
from PyQt5.QtWidgets import QLabel, QMainWindow, QApplication
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import Qt


# Local files
from constants import SPLASH_SIZE
from rolldown import Game, Unit


# Scaled splash to fit window (X by Y)
SCALED_SPLASH_SIZE = (380, 100)
SPLASH_LOCATION = 500
LABEL_ROW = SPLASH_LOCATION + 370
LABEL_SIZE = (SCALED_SPLASH_SIZE[0], 60)
RIGHT_ALIGN = LABEL_SIZE[0] - 20


class Menu(QMainWindow):
    """Main rolldown window."""
    def __init__(self, cur_game):
        super().__init__()

        self.setStyleSheet('QMainWindow {border-image: url(boards/Pink_TFT.jpg); \
            background-position: center; \
            background-repeat: no-repeat;}')

        # Start new game
        self.game = cur_game

        # List of all displayed widgets
        self.displays = []
        self.shop = []

        # Current gold
        self.gold_label = QLabel(self)
        self.gold_label.resize(*SCALED_SPLASH_SIZE)
        self.gold_label.setFont(QFont('Times', 20))
        self.gold_label.move(1000, 500)

        # Reroll button
        reroll_button = QLabel(self)
        reroll_button.resize(*SCALED_SPLASH_SIZE)
        reroll_button.setPixmap(QPixmap('rarities/reroll.png'))
        reroll_button.move(SPLASH_LOCATION, 1000)
        reroll_button.mousePressEvent = self.reroll

        # Reroll label
        reroll = QLabel(self)
        reroll.resize(*SCALED_SPLASH_SIZE)
        reroll.setFont(QFont('Times', 20))
        reroll.setText('Reroll')
        reroll.move(SPLASH_LOCATION, 1000)
        reroll.mousePressEvent = self.reroll

        # Shop
        self.display_shop(first_roll=True)

        # Display window
        self.setWindowTitle("Rolldown")
        self.resize(1006, 596 * 3)
        self.showMaximized()


    def display_gold(self):
        """Display the current amount of gold owned by player."""
        self.gold_label.setText('Gold: ' + str(self.game.gold))

    def display_unit(self, unit, col):
        """Display unit in the correct shop location."""
        # Image
        # Check naming scheme of image
        name = f'{sys.argv[1]}champions/{unit.name}.png'
        if not exists(name):
            name = f'{sys.argv[1]}champions/{unit.id_name}.png'

        splash = QLabel(self)
        splash_map = QPixmap(name).scaled(SCALED_SPLASH_SIZE[0], \
            SCALED_SPLASH_SIZE[0], Qt.KeepAspectRatio)
        splash.setPixmap(splash_map)
        splash.resize(*SPLASH_SIZE)
        splash.move(col, SPLASH_LOCATION)
        splash.show()

        # Label background color (rarity)
        label_background = QLabel(self)
        label_map = QPixmap(f'rarities/{unit.cost}.png').scaled(*LABEL_SIZE)
        label_background.setPixmap(label_map)
        label_background.resize(*SCALED_SPLASH_SIZE)
        label_background.move(col, LABEL_ROW)
        label_background.show()

        # Unit name
        label_name = QLabel(self)
        label_name.resize(*SCALED_SPLASH_SIZE)
        label_name.setText(f' {unit.name}')
        label_name.move(col, LABEL_ROW)
        label_name.show()

        # Unit rarity
        label_rarity = QLabel(self)
        label_rarity.resize(*SCALED_SPLASH_SIZE)
        label_rarity.setText(f' {unit.cost}')
        label_rarity.move(col + RIGHT_ALIGN, LABEL_ROW)
        label_rarity.show()

        # Append to display and shop
        self.shop.append(unit)
        self.displays.append((splash, label_background, label_name, label_rarity))

        # Make label and splash clickable
        source = partial(self.buy_unit, source_object=(len(self.shop) - 1))
        label_background.mouseReleaseEvent = source
        label_name.mouseReleaseEvent = source
        label_rarity.mouseReleaseEvent = source
        splash.mouseReleaseEvent = source

    def display_shop(self, first_roll=False):
        """Display the current shop."""
        # Roll for units
        current_roll = self.game.roll(first_roll)

        # Update current gold
        self.display_gold()

        # Display shop
        for idx, unit in enumerate(current_roll):
            self.display_unit(unit, idx * (SCALED_SPLASH_SIZE[0] + 1))

    # pylint: disable=unused-argument
    def buy_unit(self, event, source_object=None):
        """Buy a unit."""
        index = int(source_object)

        # Cannot purchase empty slots
        if self.shop[index].name == 'BLANK':
            return

        # Check if enough gold is available to purchase the unit
        # REMEMBER THAT SHOP IS 1-INDEXED
        if self.game.gold < self.shop[index].cost:
            return

        # Add unit to team
        self.game.buy_unit(self.shop, index + 1)

        # Remove unit from shop
        self.shop[index] = Unit(None, 'BLANK', None, None)

        # Remove widgets from display
        initial_map = QPixmap('rarities/blank.png')
        for idx, widget in enumerate(self.displays[index]):
            # Rescale splash and label
            if idx == 0:
                first = initial_map.scaled(widget.width(), widget.height())
                final = first.scaled(SCALED_SPLASH_SIZE[0], \
                    SCALED_SPLASH_SIZE[0], Qt.KeepAspectRatio)
                widget.setPixmap(final)
            elif idx == 1:
                final = initial_map.scaled(*LABEL_SIZE)
                widget.setPixmap(final)
            # Replace name and cost with blank text
            else:
                widget.setText('')

        # Update current gold
        self.display_gold()

    # pylint: disable=unused-argument
    def reroll(self, event):
        """Reroll the shop."""
        # Check if roll is allowed
        if self.game.gold < 2:
            return

        # Delete old shop
        for disp in self.displays:
            for widget in disp:
                widget.deleteLater()

        # Display new shop
        self.displays = []
        self.shop = []
        self.display_shop()

    # pylint: disable=invalid-name
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


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python user_interface.py {input_dir}')
        sys.exit()

    # Set up rolldown
    game = Game(sys.argv[1], 10, 1)

    # Set background
    app = QApplication(sys.argv)
    ex = Menu(game)

    app.exec_()
