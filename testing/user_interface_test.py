"""Testing pyqt."""
import sys

# pylint: disable=no-name-in-module
from PyQt5.QtWidgets import QLabel, QMainWindow, QApplication
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt


# pylint: disable=wrong-import-position
from constants import SPLASH_SIZE


class Menu(QMainWindow):
    """Main testing window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rolldown")

        # Display shop
        self.display_unit('Akali', 0, 0, 5)

        self.resize(1006, 596 * 3)
        self.showMaximized()


    def display_unit(self, unit, row, col, rare):
        """Display unit in the correct shop location."""
        # Image
        label = QLabel(self)
        pixmap = QPixmap(f'TFT_Set_6/champions/{unit}.png').scaled(300, 300, Qt.KeepAspectRatio)
        label.setPixmap(pixmap)
        label.resize(*SPLASH_SIZE)
        label.move(row, col)
        # Cost
        label = QLabel(self)
        pixmap = QPixmap(f'rarities/{rare}.png').scaled(300, 60)
        label.setPixmap(pixmap)
        label.resize(300, 100)
        label.move(row, 370)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = Menu()
    sys.exit(app.exec_())
