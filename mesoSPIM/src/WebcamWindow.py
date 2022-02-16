import numpy as np
import pyqtgraph as pg
import sys

import logging
logger = logging.getLogger(__name__)

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.uic import loadUi
from PyQt5.QtMultimedia import QCameraInfo, QCamera, QCameraViewfinderSettings
from PyQt5.QtMultimediaWidgets import QCameraViewfinder


class WebcamWindow(QtWidgets.QWidget):
    sig_state_request = QtCore.pyqtSignal(dict)
    sig_move_absolute = QtCore.pyqtSignal(dict)

    def __init__(self, parent=None):
        '''Parent must be an mesoSPIM_MainWindow() object'''
        super().__init__()
        self.parent = parent # the mesoSPIM_MainWindow() object
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.WEBCAM_ID = 0
        loadUi('gui/WebcamWindow.ui', self)
        self.setWindowTitle(f'Webcam view, camera ID {self.WEBCAM_ID}')
        self.show()
        self.start_capture()

    def start_capture(self):
        webcams = QCameraInfo.availableCameras()
        print(f"Webcams found: {len(webcams)}")
        if len(webcams) > 0:
            self.webcam = QCamera(webcams[self.WEBCAM_ID])
            self.webcam.setCaptureMode(QCamera.CaptureViewfinder)
            self.vf_settings = QCameraViewfinderSettings()
            #self.vf_settings.setResolution(960, 720)
            self.webcam.setViewfinderSettings(self.vf_settings)
            self.webcam.setViewfinder(self.viewfinder)
            #self.viewfinder = QCameraViewfinder() # this object is defined inside the WebcamWindow.ui file
            self.webcam.start()
            #print(f"Supported webcam viewfinder resolutions {self.webcam.supportedViewfinderResolutions()}")
            self.viewfinder.show()
        else:
            print("Webcam not found")


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    window = WebcamWindow()
    sys.exit(app.exec_())