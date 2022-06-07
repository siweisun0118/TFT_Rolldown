"""Implmentation of the PyQt UI for rolldown."""


# Standard libraries
from functools import partial
import sys
from pathlib import Path


# Qt libraries
from PyQt5.QtWidgets import QLabel, QMainWindow, QApplication, QInputDialog, QPushButton
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtCore import Qt, QProcess


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
    def __init__(self):
        super().__init__()

        # Define necessary attributes
        self.game = None
        self.displays = None
        self.shop = None
        self.gold_label = None
        self.level_label = None
        self.instructions = None

        # Display window
        self.setWindowTitle("Rolldown")
        self.resize(1006, 596 * 3)
        self.showMaximized()

        # Start button
        self.start_button = QPushButton('Start', self)
        self.start_button.resize(500, 100)
        self.start_button.move(700, 500)
        self.start_button.show()
        self.start_button.clicked.connect(self.take_inputs)

    def start_game(self):
        """Start the rolldown."""
        background = str(Path('Boards') / 'Pink_TFT.jpg')
        self.setStyleSheet(f'centralwidget {{border-image: url({background}); \
            background-position: center; \
            background-repeat: no-repeat;}}')

        # Remove start button
        self.start_button.deleteLater()

        # List of all displayed widgets
        self.displays = []
        self.shop = []

        # Instructions
        inst1 = "Press 'd' or 'Reroll' to see a new shop (costs 2 gold)\n"
        inst2 = "Click champions to buy them\n"
        inst3 = "Press 'm' to quit (Final team shown in terminal)\n"
        inst4 = "Press 'p' to restart"
        self.instructions = QLabel(self)
        self.instructions.resize(2 * SCALED_SPLASH_SIZE[0], 2 * SCALED_SPLASH_SIZE[1])
        self.instructions.setFont(QFont('Times', 20))
        self.instructions.setText(inst1 + inst2 + inst3 + inst4)
        self.instructions.move(900, 100)
        self.instructions.setStyleSheet('color: white')
        self.instructions.show()

        # Current gold
        self.gold_label = QLabel(self)
        self.gold_label.resize(*SCALED_SPLASH_SIZE)
        self.gold_label.setFont(QFont('Times', 20))
        self.gold_label.move(1000, 500)
        self.gold_label.show()

        # Current level
        self.level_label = QLabel(self)
        self.level_label.resize(*SCALED_SPLASH_SIZE)
        self.level_label.setFont(QFont('Times', 20))
        self.level_label.move(1000, 450)
        self.level_label.show()

        # Reroll button
        reroll_button = QLabel(self)
        reroll_button.resize(*SCALED_SPLASH_SIZE)
        reroll_button.setPixmap(QPixmap('rarities/reroll.png'))
        reroll_button.move(500, 200)
        reroll_button.mousePressEvent = self.reroll
        reroll_button.show()

        # Reroll label
        reroll = QLabel(self)
        reroll.resize(*SCALED_SPLASH_SIZE)
        reroll.setFont(QFont('Times', 20))
        reroll.setText('Reroll')
        reroll.move(500, 200)
        reroll.mousePressEvent = self.reroll
        reroll.show()

        # Shop
        self.display_shop(first_roll=True)

    def take_inputs(self):
        """Take in inputs from user."""
        gold, done1 = QInputDialog.getText(self, 'input dialog', 'Enter starting gold:')
        level, done2 = QInputDialog.getText(self, 'input dialog',
            'Enter starting level (1-11 inclusive):')
        if done1 and done2:
            # Start new game using inputs from user
            while int(level) not in range(1, 12):
                level, _ = QInputDialog.getText(self, 'input dialog',
                                                'Enter starting level (1-11 inclusive):')
            self.game = Game(sys.argv[1], int(gold), int(level))
            self.start_game()
        else:
            QApplication.quit()

    def display_gold(self):
        """Display the current gold and level."""
        self.gold_label.setText('Gold: ' + str(self.game.gold))
        self.level_label.setText('Level: ' + str(self.game.level))

    def display_unit(self, unit, col):
        """Display unit in the correct shop location."""
        # Image
        # Check naming scheme of image
        name = Path(sys.argv[1]) / 'champions' / f'{unit.name}.png'
        if not name.is_file():
            name = Path(sys.argv[1]) / 'champions' / f'{unit.id_name}.png'
        name = str(name)

        splash = QLabel(self)
        splash_map = QPixmap(name).scaled(SCALED_SPLASH_SIZE[0], \
            SCALED_SPLASH_SIZE[0], Qt.KeepAspectRatio)
        splash.setPixmap(splash_map)
        splash.resize(*SPLASH_SIZE)
        splash.move(col, SPLASH_LOCATION)
        splash.show()

        # Label background color (rarity)
        label_background = QLabel(self)
        label_map = QPixmap(str(Path('rarities') / f'{unit.cost}.png')).scaled(*LABEL_SIZE)
        label_background.setPixmap(label_map)
        label_background.resize(*LABEL_SIZE)
        label_background.move(col, LABEL_ROW)
        label_background.show()

        # Unit name
        label_name = QLabel(self)
        label_name.resize(*LABEL_SIZE)
        label_name.setText(f' {unit.name}')
        label_name.move(col, LABEL_ROW)
        label_name.show()

        # Unit rarity
        label_rarity = QLabel(self)
        label_rarity.resize(*LABEL_SIZE)
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
        initial_map = QPixmap(str(Path('rarities') / 'blank.png'))
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

        # Restart
        if event.key() == Qt.Key_P:
            QApplication.quit()
            QProcess.startDetached(sys.executable, sys.argv)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python user_interface.py {input_dir}')
        sys.exit()

    app = QApplication(sys.argv)

    # Start application
    ex = Menu()
    app.exec_()
