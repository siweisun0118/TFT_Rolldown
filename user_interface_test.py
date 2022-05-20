"""Testing pyqt."""
import sys

# pylint: disable=no-name-in-module
from PyQt5.QtWidgets import QLabel, QMainWindow, QApplication
from PyQt5.QtGui import QPixmap



class Menu(QMainWindow):
    """Main testing window."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rolldown")

        label = QLabel(self)
        pixmap = QPixmap('TFT_Set_6/champions/Akali.png').scaledToWidth(300)
        label.setPixmap(pixmap)
        label.resize(1006, 596)
        label.move(0, 0)

        label = QLabel(self)
        pixmap = QPixmap('TFT_Set_6/champions/Blitzcrank.png').scaledToWidth(300)
        label.setPixmap(pixmap)
        label.resize(1006, 596)
        label.move(1006, 0)

        label = QLabel(self)
        pixmap = QPixmap('TFT_Set_6/champions/Braum.png').scaledToWidth(300)
        label.setPixmap(pixmap)
        label.resize(1006, 596)
        label.move(503, 0)

        self.resize(1006, 596 * 3)
        self.showMaximized()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = Menu()
    sys.exit(app.exec_())
