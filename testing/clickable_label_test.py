# pylint: skip-file

# importing libraries
from PyQt5.QtWidgets import * 
from PyQt5.QtGui import * 
from PyQt5.QtCore import * 
import sys
  
  
class Window(QMainWindow):
    def __init__(self):
        super().__init__()
  
        # setting title
        self.setWindowTitle("Python ")
  
        # setting geometry
        self.setGeometry(100, 100, 600, 400)
  
        # calling method
        self.UiComponents(0, 0)
        self.UiComponents(1006, 596)
  
        # showing all the widgets
        self.showMaximized()
  
    # method for widgets
    def UiComponents(self, x, y):
  
        # creating a push button
        button = QPushButton("", self)
  
        # setting geometry of button
        button.setGeometry(x, y, x + 1006, y + 596)
  
        # adding action to a button
        button.clicked.connect(self.clickme)

        # setting image to the button
        button.setStyleSheet("background-image : url(TFT_Set_6/champions/Akali.png);")

        # Add label for champion name
        label = QLabel(self)
        label.setText('Akali')
        label.resize(1006, 596)
        label.move(x + 1006, y + 596)

    # action method
    def clickme(self):
  
        # printing pressed
        print("pressed")
  
# create pyqt5 app
App = QApplication(sys.argv)
  
# create the instance of our Window
window = Window()
  
# start the app
sys.exit(App.exec())
