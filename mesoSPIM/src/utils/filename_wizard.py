'''
Contains Filename Wizard Class: autogenerates Filenames

'''

from PyQt5 import QtWidgets, QtGui, QtCore

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtProperty

# from .config import config as cfg
# from .acquisition_builder import TilingAcquisitionListBuilder

from ..mesoSPIM_State import mesoSPIM_StateSingleton

class FilenameWizard(QtWidgets.QWizard):
    '''
    Wizard to run

    The parent is the Window class of the microscope
    '''
    wizard_done = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        ''' By an instance variable, callbacks to window signals can be handed
        through '''
        self.parent = parent
        self.state = mesoSPIM_StateSingleton()

        self.setWindowTitle('Filename Wizard')

        self.addPage(FilenameWizardWelcomePage(self))
        self.addPage(FilenameWizardCheckResultsPage(self))
        
        self.show()

    def done(self, r):
        ''' Reimplementation of the done function

        if r == 0: canceled
        if r == 1: finished properly
        '''
        if r == 0:
            print("Wizard was canceled")
        if r == 1:
            print('Wizard was closed properly')
            print('Laser selected: ', self.field('Laser'))
            print('Filter selected: ', self.field('Filter'))
            print('Zoom selected: ', self.field('Zoom'))
            print('Shutter selected: ', self.field('Shutter'))
        else:
            print('Wizard provided return code: ', r)

        super().done(r)

    def generate_filenames(self):
        '''
        Go through the model, entry for entry
        '''
        pass



class FilenameWizardWelcomePage(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("Autogenerate filenames")
        self.setSubTitle("Which properties would you like to use?")

        self.LaserRadioButton = QtWidgets.QCheckBox('Laser', self)
        self.FilterRadioButton = QtWidgets.QCheckBox('Filter', self)
        self.ZoomRadioButton = QtWidgets.QCheckBox('Zoom', self)
        self.ShutterRadioButton = QtWidgets.QCheckBox('Shutter', self)

        self.registerField('Laser',self.LaserRadioButton)
        self.registerField('Filter', self.FilterRadioButton)
        self.registerField('Zoom', self.ZoomRadioButton)
        self.registerField('Shutter', self.ShutterRadioButton)

        self.layout = QtWidgets.QGridLayout()
        self.layout.addWidget(self.LaserRadioButton, 0, 0)
        self.layout.addWidget(self.FilterRadioButton, 1, 0)
        self.layout.addWidget(self.ZoomRadioButton, 2, 0)
        self.layout.addWidget(self.ShutterRadioButton, 3, 0)
        self.setLayout(self.layout)

class FilenameWizardCheckResultsPage(QtWidgets.QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle('Check results')
        self.setSubTitle('Please check if the following filenames are ok:')

        self.TextEdit = QtWidgets.QPlainTextEdit(self)
        self.TextEdit.setReadOnly(True)
        self.TextEdit.setPlainText('Hello1 Hello2 \n Hello3')

        self.layout = QtWidgets.QGridLayout()
        self.layout.addWidget(self.TextEdit, 0, 0, 1, 1)
        self.setLayout(self.layout)
