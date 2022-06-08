"""Simulate a Rolldown"""

import sys
from pathlib import Path


from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QInputDialog
from PyQt5.QtGui import QPixmap


from user_interface_v3 import Ui_MainWindow, GEN_ASSETS
from rolldown import Game


class MainWindow(QMainWindow):
    """Main UI Window."""
    def __init__(self, input_dir):
        super(MainWindow, self).__init__()

        # Input director
        self.input_dir = Path(input_dir)

        # Take in inputs
        self.take_inputs()

        # Start main UI window
        self.ui = Ui_MainWindow()

        # Access to UI widgets
        self.shop, self.traits, self.units, self.gold_and_level = self.ui.setupUi(self, input_dir)

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
        self.display_shop(first_roll=True)

    def display_shop(self, first_roll=False):
        """Display the current shop."""
        # Roll for units
        current_roll = self.game.roll(first_roll)

        # Display rolled units
        for idx, unit in enumerate(current_roll):
            # Display unit splash
            splash_label = self.shop[idx].findChild(QLabel, f'Shop_Icon_{idx + 1}')
            # Get name of file
            name = self.input_dir / 'champions' / f'{unit.name}.png'
            if not name.is_file():
                name = self.input_dir / 'champions' / f'{unit.id_name}.png'
            splash = QPixmap(str(name))
            splash_label.setPixmap(splash)

            # Display unit rarity
            rarity_label = self.shop[idx].findChild(QLabel, f'Shop_Rarity_{idx + 1}')
            rarity = QPixmap(str(GEN_ASSETS / 'rarities' / f'{unit.cost}.png'))
            rarity_label.setPixmap(rarity)

            # Display unit name
            name_label = self.shop[idx].findChild(QLabel, f'Shop_Name_{idx + 1}')
            name_label.setText(unit.name)

            # Display unit cost
            cost_label = self.shop[idx].findChild(QLabel, f'Shop_Cost_{idx + 1}')
            cost_label.setText(f'{unit.cost}G')
            cost_label.setStyleSheet('color: gold')


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: python user_interface_test.py {input_dir}')
        sys.exit()

    app = QApplication(sys.argv)

    window = MainWindow(sys.argv[1])
    window.setFixedSize(window.size())
    window.showMaximized()

    sys.exit(app.exec())
