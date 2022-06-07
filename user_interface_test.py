import sys


from PyQt5 import QtWidgets
from PyQt5.QtGui import QPixmap


from user_interface_v3 import Ui_MainWindow


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.ui = Ui_MainWindow()
        shop, traits, units, gold_and_level = self.ui.setupUi(self)

        for widget in shop[0].children():
            widget.setPixmap(QPixmap('rarities/blank.png'))

        for widget in traits[15].children():
            if isinstance(widget, QtWidgets.QLabel):
                widget.setPixmap(QPixmap('rarities/white.png').scaled(100, 100))

        for widget in units[15].children():
            if isinstance(widget, QtWidgets.QLabel):
                widget.setPixmap(QPixmap('rarities/white.png').scaled(100, 100))

        for widget in gold_and_level:
            if isinstance(widget, QtWidgets.QLabel):
                widget.setPixmap(QPixmap('rarities/white.png').scaled(100, 100))

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    window = MainWindow()
    window.setFixedSize(window.size())
    window.show()

    sys.exit(app.exec())
