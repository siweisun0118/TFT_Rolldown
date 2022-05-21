"""Implmentation of the PyQt UI for rolldown."""


# Standard libraries
import sys


# Qt libraries
from PyQt5.QtWidgets import QLabel, QMainWindow, QApplication
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt


# Local files
from constants import SPLASH_SIZE
from rolldown import Game


# Scaled splash to fit window (X by Y)
SCALED_SPLASH_SIZE = (380, 100)
SPLASH_LOCATION = 400
LABEL_ROW = SPLASH_LOCATION + 370
LABEL_SIZE = (SCALED_SPLASH_SIZE[0], 60)
RIGHT_ALIGN = LABEL_SIZE[0] - 20


class Menu(QMainWindow):
    """Main testing window."""
    def __init__(self):
        super().__init__()
        # List of all displayed widgets
        self.displays = []

        # Window
        self.setWindowTitle("Rolldown")

        self.display_shop()

        # Reroll button
        reroll = QLabel(self)
        reroll.resize(*SCALED_SPLASH_SIZE)
        reroll.setText('reroll')
        reroll.move(SPLASH_LOCATION, 1000)
        reroll.mousePressEvent = self.reroll

        self.resize(1006, 596 * 3)
        self.showMaximized()

    def display_unit(self, unit, col):
        """Display unit in the correct shop location."""
        # Image
        splash = QLabel(self)
        splash_map = QPixmap(f'{sys.argv[1]}champions/{unit.name}.png'\
            ).scaled(SCALED_SPLASH_SIZE[0], SCALED_SPLASH_SIZE[0], Qt.KeepAspectRatio)
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

        # Make label and splash clickable
        label_background.mousePressEvent = self.buy_unit
        label_name.mousePressEvent = self.buy_unit
        label_rarity.mousePressEvent = self.buy_unit
        splash.mouseReleaseEvent = self.buy_unit

        return label_background, label_name, label_rarity, splash

    def display_shop(self):
        """Display the current shop."""
        current_roll = Game(sys.argv[1], 200, 10).roll()

        # Display shop
        for idx, unit in enumerate(current_roll):
            self.displays.append(self.display_unit(unit, idx * (SCALED_SPLASH_SIZE[0] + 1)))

    def buy_unit(self, event):
        """Buy a unit."""
        print("CLICKED")
        print(event.globalX(), event.globalY())

    def reroll(self, event):
        """Reroll the shop."""
        # Delete old shop
        for disp in self.displays:
            for widget in disp:
                widget.deleteLater()

        # Display new shop
        self.displays = []
        self.display_shop()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python user_interface.py {input_dir}')
        sys.exit()

    app = QApplication(sys.argv)
    ex = Menu()

    sys.exit(app.exec_())
