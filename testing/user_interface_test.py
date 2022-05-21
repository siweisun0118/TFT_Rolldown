"""Testing pyqt."""
import sys

# pylint: disable=no-name-in-module
from PyQt5.QtWidgets import QLabel, QMainWindow, QApplication
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt


# pylint: disable=wrong-import-position
from constants import SPLASH_SIZE

# Scaled splash to fit window (X by Y)
SCALED_SPLASH_SIZE = (300, 100)
SCALED_HEIGHT = 370


LABEL_SIZE = (300, 60)
RIGHT_ALIGN = LABEL_SIZE[0] - 20


class Menu(QMainWindow):
    """Main testing window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rolldown")

        # Display shop
        self.display_unit('Akali', 0, 5)
        self.display_unit('Braum', SCALED_SPLASH_SIZE[0] + 1, 4)
        self.display_unit('Blitzcrank', 2 * (SCALED_SPLASH_SIZE[0] + 1), 2)
        self.display_unit('Vi', 3 * (SCALED_SPLASH_SIZE[0] + 1), 2)
        self.display_unit('Heimerdinger', 4 * (SCALED_SPLASH_SIZE[0] + 1), 3)

        self.resize(1006, 596 * 3)
        self.showMaximized()

    def display_unit(self, unit, col, rarity):
        """Display unit in the correct shop location."""
        # Image
        splash = QLabel(self)
        splash_map = QPixmap(f'TFT_Set_6/champions/{unit}.png').scaled(300, 300, Qt.KeepAspectRatio)
        splash.setPixmap(splash_map)
        splash.resize(*SPLASH_SIZE)
        splash.move(col, 0)

        # Label background color (rarity)
        label_background = QLabel(self)
        label_map = QPixmap(f'rarities/{rarity}.png').scaled(*LABEL_SIZE)
        label_background.setPixmap(label_map)
        label_background.resize(*SCALED_SPLASH_SIZE)
        label_background.move(col, SCALED_HEIGHT)

        # Unit name
        label_name = QLabel(self)
        label_name.resize(*SCALED_SPLASH_SIZE)
        label_name.setText(f' {unit}')
        label_name.move(col, SCALED_HEIGHT)
        
        # Unit rarity
        label_rarity = QLabel(self)
        label_rarity.resize(*SCALED_SPLASH_SIZE)
        label_rarity.setText(f' {rarity}')
        label_rarity.move(col + RIGHT_ALIGN, SCALED_HEIGHT)

        # Make label and splash clickable
        label_background.mousePressEvent = self.buy_unit
        label_name.mousePressEvent = self.buy_unit
        label_rarity.mousePressEvent = self.buy_unit
        splash.mouseReleaseEvent = self.buy_unit

    def buy_unit(self, event):
        """Buy a unit."""
        print("CLICKED")
        print(event.globalX(), event.globalY())


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = Menu()
    sys.exit(app.exec_())
