#! python
# Mandala.py - Copies a set number of random files from a single directory to a new directory

import timeit
import cProfile

import re
import os
import sys
import shutil
import random
import inspect
import datetime
import send2trash
import collections
import soundfile
import mutagen
from mutagen.mp3 import MP3
from distutils.util import strtobool
from pathlib import Path
from time import perf_counter, time
from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *

class WorkerSignals(QObject):
    countSignal = Signal()
    logSignal = Signal(object)
    timeSignal = Signal()
    finishedSignal = Signal()

class RunMandalaWorker(QRunnable):
    def run(self):
        window.runMandala()

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.randomIcon = QIcon('icons/dices.svg')
        self.browseIcon = QIcon('icons/browse.svg')
        self.openIcon = QIcon('icons/open.svg')
        self.noWrap = '<p style="white-space:pre">'
        self.wasEnabled = {}
        self.listOfPaths = collections.defaultdict(bool)

        self.threadpool = QThreadPool()
        self.mandala = RunMandalaWorker()
        self.mandala.setAutoDelete(False)

        self.setupUi()
        self.setupSignals()

        self.settings = QSettings('Jang', 'Mandala')
        self.globalSettingsRestore()
        self.guiRestore(self.settings)
        
    def setupSignals(self):
        self.signals = WorkerSignals()
        self.signals.countSignal.connect(lambda: self.progressBar.setValue(self.count))
        self.signals.timeSignal.connect(lambda: self.stallTimeProgressBar.setValue(self.stallTimeProgressBar.maximum()))
        self.signals.timeSignal.connect(lambda: self.stallTimeCounter.setText(f'{self.stallTimeProgressBar.value()/100} s'))
        self.signals.logSignal.connect(lambda s: self.logBlock.append(s))
        self.signals.finishedSignal.connect(lambda: self.timer.stop())

    def makeSpin(self, lo, hi, enabled):
        name = QSpinBox()
        name.setRange(lo, hi)
        name.setMaximumWidth(60)
        name.setEnabled(enabled)
        return name
 
    def createGroupButton(self, name):
        button = QPushButton(name)
        button.setFlat(True)
        button.setCheckable(True)
        button.setChecked(True)
        button.setObjectName('groupButton')
        return button
    
    def createGroupLabel(self, name):
        label = QLabel(name)
        label.setObjectName('groupLabel')
        return label

    def disableGroup(self, button, group):
        r = button.isChecked()
        [child.setEnabled(r) for child in group.children() if child != button]

    # SETUP TAB

    def setupFileCountUi(self): # self.fileCountG
        self.fileCountLabel = QLabel('Count')
        self.fileLoLabel = QLabel('Min')
        self.fileLoLabel.setDisabled(True)

        self.fileHiLabel = QLabel('Max')
        self.fileHiLabel.setDisabled(True)

        self.numFilesCount = self.makeSpin(1, 1000000000, True)
        self.numFilesLo = self.makeSpin(1, 1000000000, False)
        self.numFilesHi = self.makeSpin(2, 1000000000, False)

        self.countCheck = QRadioButton('Set Number')

        countL = QHBoxLayout()
        countL.addWidget(self.fileCountLabel)
        countL.addWidget(self.numFilesCount)
        self.countFileG = QGroupBox('Set Number')
        self.countFileG.setLayout(countL)
        self.countFileG.setCheckable(True)

        minRow = QHBoxLayout()
        minRow.addWidget(self.fileLoLabel)
        minRow.addWidget(self.numFilesLo)
        maxRow = QHBoxLayout()
        maxRow.addWidget(self.fileHiLabel)
        maxRow.addWidget(self.numFilesHi)

        randomL = QVBoxLayout()
        randomL.addLayout(minRow)
        randomL.addLayout(maxRow)
        self.randomFileG = QGroupBox('Randomize')
        self.randomFileG.setLayout(randomL)
        self.randomFileG.setCheckable(True)
        self.randomFileG.setChecked(False)

        fileCountL = QHBoxLayout()
        fileCountL.addWidget(self.countFileG)
        fileCountL.addWidget(self.randomFileG)
        
        self.fileCountG = QGroupBox('File count')
        self.fileCountG.setLayout(fileCountL)

        self.numFilesLo.editingFinished.connect(self.switchFileCount)
        self.numFilesHi.editingFinished.connect(self.switchFileCount)
        self.randomFileG.toggled.connect(self.switchFileCount)
        self.randomFileG.toggled.connect(self.changeFileLabelRand)
        self.countFileG.toggled.connect(self.changeFileLabelCount)

    def setupRootUi(self): # self.rootG
        self.rootLabel = self.createGroupLabel('Root')

        self.root = QDir.rootPath()
        self.rootDirectory = self.root

        self.rootCombo = QComboBox()
        self.rootCombo.addItem(self.root)

        self.browseRootButton = QPushButton(' Browse')
        self.browseRootButton.setIcon(self.browseIcon)

        self.deleteRoot = QPushButton('Delete')

        self.deleteRoot.clicked.connect(self.deleteRootItem)
        self.rootCombo.currentTextChanged.connect(self.changeRoot)
        self.browseRootButton.clicked.connect(self.browseRoot)

        rootControls = QHBoxLayout()
        rootControls.addWidget(self.rootCombo)
        rootControls.addWidget(self.browseRootButton)
        rootControls.addWidget(self.deleteRoot)

        rootL = QVBoxLayout()
        rootL.addWidget(self.rootLabel)
        rootL.addLayout(rootControls)

        self.rootG = QGroupBox()
        self.rootG.setLayout(rootL)

    def setupDestUi(self): # self.destG
        self.destLabel = self.createGroupLabel('Destination')

        self.dest = QDir.homePath()
        self.destDirectory = self.dest

        self.destCombo = QComboBox()
        self.destCombo.addItem(self.dest)

        self.browseDestButton = QPushButton(' Browse')
        self.browseDestButton.setIcon(self.browseIcon)

        self.deleteDest = QPushButton('Delete')

        self.deleteDest.clicked.connect(self.deleteDestItem)
        self.destCombo.currentTextChanged.connect(self.changeDestination)
        self.browseDestButton.clicked.connect(self.browseDestination)

        destLabelL = QHBoxLayout()
        destLabelL.addWidget(self.destLabel)
        destLabelL.addStretch()

        destControls = QHBoxLayout()
        destControls.addWidget(self.destCombo)
        destControls.addWidget(self.browseDestButton)
        destControls.addWidget(self.deleteDest)

        destL = QVBoxLayout()
        destL.addLayout(destLabelL)
        destL.addLayout(destControls)

        self.destG = QGroupBox()
        self.destG.setLayout(destL)

    def setupCreateFoldersUi(self): # self.foldersG
        self.folderButton = self.createGroupButton('Folders')

        self.folderCountLabel = QLabel('Count')
        foldersNameLabel = QLabel('Name')

        self.numFoldersCount = QSpinBox()
        self.numFoldersCount.setRange(1, 100000)
        
        self.nameOfFoldersEntry = QLineEdit('Folder Name')
    
        self.makeFoldersUniqueCheck = QCheckBox('Make Unique')
        self.makeFoldersUniqueCheck.setChecked(True)

        labelRow = QHBoxLayout()
        labelRow.addWidget(self.folderButton)
        labelRow.addStretch()

        row1 = QHBoxLayout()
        row1.addWidget(self.folderCountLabel)
        row1.addWidget(self.numFoldersCount)

        row2 = QHBoxLayout()
        row2.addWidget(foldersNameLabel)
        row2.addWidget(self.nameOfFoldersEntry)

        foldersL = QVBoxLayout()
        foldersL.addLayout(labelRow)        
        foldersL.addLayout(row1)
        foldersL.addLayout(row2)
        foldersL.addWidget(self.makeFoldersUniqueCheck)

        self.foldersG = QGroupBox()
        self.foldersG.setLayout(foldersL)

        self.folderButton.toggled.connect(lambda: self.disableGroup(self.folderButton, self.foldersG))

    def setupFileNameUi(self): # self.fileNameG
        self.fileNameButton = self.createGroupButton('Filenames')

        self.keepFilesRadio = QRadioButton('Keep')
        self.keepFilesRadio.setChecked(True)
        self.indexFilesRadio = QRadioButton('Index')
        self.renameFilesRadio = QRadioButton('Rename')
        self.renameNameEntry = QLineEdit('New Name')
        self.renameNameEntry.setEnabled(False)

        self.renameFilesRadio.toggled.connect(lambda: self.renameNameEntry.setEnabled(self.renameFilesRadio.isChecked()))
        
        labelRow = QHBoxLayout()
        labelRow.addWidget(self.fileNameButton)
        labelRow.addStretch()

        renameRow = QHBoxLayout()
        renameRow.addWidget(self.renameFilesRadio)
        renameRow.addWidget(self.renameNameEntry)

        fileNameL = QVBoxLayout()
        fileNameL.addLayout(labelRow)
        fileNameL.addWidget(self.keepFilesRadio)
        fileNameL.addWidget(self.indexFilesRadio)
        fileNameL.addLayout(renameRow)
        
        self.fileNameG = QGroupBox()
        self.fileNameG.setLayout(fileNameL)

        self.fileNameButton.toggled.connect(lambda: self.disableGroup(self.fileNameButton, self.fileNameG))

    def setupTrashUi(self): # self.trashG
        self.trashButton = self.createGroupButton('Trash')

        self.isTrashEmpty = QCheckBox('Empty Folders')
        self.isTrashSource = QCheckBox('Valid Files')
        self.isTrashInvalid = QCheckBox('Invalid Files') 
        
        labelRow = QHBoxLayout()
        labelRow.addWidget(self.trashButton)
        labelRow.addStretch()

        trashL = QVBoxLayout()
        trashL.addLayout(labelRow)
        trashL.addWidget(self.isTrashEmpty)
        trashL.addWidget(self.isTrashSource)
        trashL.addWidget(self.isTrashInvalid)

        self.trashG = QGroupBox()
        self.trashG.setLayout(trashL)

        self.trashButton.toggled.connect(lambda: self.disableGroup(self.trashButton, self.trashG))
    
    def setupSetupTab(self): # self.setupTab
        self.setupFileCountUi()
        self.setupRootUi()
        self.setupDestUi()
        self.setupCreateFoldersUi()
        self.setupFileNameUi()
        self.setupTrashUi()

        outputRow = QHBoxLayout()
        outputRow.addWidget(self.foldersG)
        outputRow.addWidget(self.fileNameG)
        outputRow.addWidget(self.trashG)

        setupL = QVBoxLayout()
        setupL.addWidget(self.fileCountG)
        setupL.addWidget(self.rootG)
        setupL.addWidget(self.destG)
        setupL.addLayout(outputRow)
        
        self.setupTab = QWidget()
        self.setupTab.setLayout(setupL)


    # CUSTOMIZE TAB

    def setupKeywordsUi(self): # self.keywordsG
        self.incKeysEdit = QLineEdit()
        self.excKeysEdit = QLineEdit()

        self.toSwitchKeys = QPushButton('Switch')

        incKeysL = QHBoxLayout()
        incKeysL.addWidget(self.incKeysEdit)
        self.incKeysG = QGroupBox('Include')
        self.incKeysG.setLayout(incKeysL)
        self.incKeysG.setCheckable(True)

        excKeysL = QHBoxLayout()
        excKeysL.addWidget(self.excKeysEdit)
        self.excKeysG = QGroupBox('Exclude')
        self.excKeysG.setLayout(excKeysL)
        self.excKeysG.setCheckable(True)

        keywordsL = QHBoxLayout()
        keywordsL.addWidget(self.incKeysG)
        keywordsL.addWidget(self.toSwitchKeys)
        keywordsL.addWidget(self.excKeysG)

        self.keywordsG = QGroupBox('Keywords')
        self.keywordsG.setLayout(keywordsL)

        self.toSwitchKeys.clicked.connect(self.switchKeys)
        self.incKeysG.toggled.connect(lambda: self.disableGroup(self.incKeysG))
        self.excKeysG.toggled.connect(lambda: self.disableGroup(self.excKeysG))

    def setupExtensionsUi(self): # self.extensionsG
        self.incExtsEdit = QLineEdit()
        self.excExtsEdit = QLineEdit()

        self.toSwitchExts = QPushButton('Switch')

        incExtsL = QHBoxLayout()
        incExtsL.addWidget(self.incExtsEdit)
        self.incExtsG = QGroupBox('Include')
        self.incExtsG.setLayout(incExtsL)
        self.incExtsG.setCheckable(True)

        excExtsL = QHBoxLayout()
        excExtsL.addWidget(self.excExtsEdit)
        self.excExtsG = QGroupBox('Exclude')
        self.excExtsG.setLayout(excExtsL)
        self.excExtsG.setCheckable(True)

        extensionsL = QHBoxLayout()
        extensionsL.addWidget(self.incExtsG)
        extensionsL.addWidget(self.toSwitchExts)
        extensionsL.addWidget(self.excExtsG)

        self.extensionsG = QGroupBox('Extensions')
        self.extensionsG.setLayout(extensionsL)

        self.toSwitchExts.clicked.connect(self.switchExts)
        self.incExtsG.toggled.connect(lambda: self.disableGroup(self.incExtsG))
        self.excExtsG.toggled.connect(lambda: self.disableGroup(self.excExtsG))

    def setupSizeUi(self): # self.sizeG
        self.sizeButton = self.createGroupButton('File Size')

        sizeLoLabel = QLabel('Min')
        sizeHiLabel = QLabel('Max')

        self.sizeLo = QDoubleSpinBox()
        self.sizeLo.setRange(0, 100000)

        self.sizeHi = QDoubleSpinBox()
        self.sizeHi.setRange(1, 100000)
        self.sizeHi.setValue(50)

        self.sizeType = QComboBox() 
        self.sizeType.addItems(['B', 'KB', 'MB', 'GB'])
        self.sizeType.setCurrentIndex(2)

        labelRow = QHBoxLayout()
        labelRow.addWidget(self.sizeButton)
        labelRow.addStretch()

        row1 = QHBoxLayout()
        row1.addWidget(sizeLoLabel)
        row1.addWidget(self.sizeLo)

        row2 = QHBoxLayout()
        row2.addWidget(sizeHiLabel)
        row2.addWidget(self.sizeHi)
        row2.addWidget(self.sizeType)

        fileSizeL = QVBoxLayout()
        fileSizeL.addLayout(labelRow)
        fileSizeL.addLayout(row1)
        fileSizeL.addLayout(row2)
        
        self.sizeG = QGroupBox()
        self.sizeG.setLayout(fileSizeL)

        self.sizeLo.editingFinished.connect(self.switchSize)
        self.sizeHi.editingFinished.connect(self.switchSize)
        self.sizeButton.toggled.connect(lambda: self.disableGroup(self.sizeButton, self.sizeG))

    def setupDurationUi(self): # self.durationG
        self.lengthButton = self.createGroupButton('File Length')

        lengthLoLabel = QLabel('Min')
        lengthHiLabel = QLabel('Max')

        self.durationLo = QDoubleSpinBox()
        self.durationLo.setRange(0, 100000)
        self.durationLo.setAccelerated(True)
        self.durationLo.setGroupSeparatorShown(True)
        self.durationLo.setFrame(True)

        self.durationHi = QDoubleSpinBox()
        self.durationHi.setRange(1, 100000)
        self.durationHi.setAccelerated(True)
        self.durationHi.setGroupSeparatorShown(True)
        self.durationHi.setValue(100)
        
        self.durationType = QComboBox()
        self.durationType.addItems(['s', 'm'])
        self.durationType.setCurrentIndex(0)

        labelRow = QHBoxLayout()
        labelRow.addWidget(self.lengthButton)
        labelRow.addStretch()

        row1 = QHBoxLayout()
        row1.addWidget(lengthLoLabel)
        row1.addWidget(self.durationLo)

        row2 = QHBoxLayout()
        row2.addWidget(lengthHiLabel)
        row2.addWidget(self.durationHi)
        row2.addWidget(self.durationType)

        durationL = QVBoxLayout()
        durationL.addLayout(labelRow)
        durationL.addLayout(row1)
        durationL.addLayout(row2)

        self.durationG = QGroupBox()
        self.durationG.setLayout(durationL)

        self.durationLo.editingFinished.connect(self.switchDuration)
        self.durationHi.editingFinished.connect(self.switchDuration)
        self.lengthButton.toggled.connect(lambda: self.disableGroup(self.lengthButton, self.durationG))

    def setupWeightUi(self): # self.weightG
        self.weightButton = self.createGroupButton('Weight')

        topWeightLabel = QLabel('Top')
        self.topWeightSpinBox = QSpinBox()
        self.topWeightSpinBox.setRange(0, 100000)
        self.topWeightSpinBox.setSpecialValueText('None')
        
        bottomWeightLabel = QLabel('Bottom')
        self.bottomWeightSpinBox = QSpinBox()
        self.bottomWeightSpinBox.setRange(0, 100000)
        self.bottomWeightSpinBox.setSpecialValueText('None')

        labelRow = QHBoxLayout()
        labelRow.addWidget(self.weightButton)
        labelRow.addStretch()

        row1 = QHBoxLayout()
        row1.addWidget(topWeightLabel)
        row1.addWidget(self.topWeightSpinBox)

        row2 = QHBoxLayout()
        row2.addWidget(bottomWeightLabel)
        row2.addWidget(self.bottomWeightSpinBox)

        weightL = QVBoxLayout()
        weightL.addLayout(labelRow)
        weightL.addLayout(row1)
        weightL.addLayout(row2)
        
        self.weightG = QGroupBox()
        self.weightG.setLayout(weightL)

        self.weightButton.toggled.connect(lambda: self.disableGroup(self.weightButton, self.weightG))
     
    def setupCustomizeTab(self): # self.custTab
        self.setupKeywordsUi()
        self.setupExtensionsUi()
        self.setupSizeUi()
        self.setupWeightUi()
        self.setupDurationUi()

        rowL = QHBoxLayout()
        rowL.addWidget(self.sizeG)
        rowL.addWidget(self.durationG)
        rowL.addWidget(self.weightG)

        custL = QVBoxLayout()
        custL.addWidget(self.keywordsG)
        custL.addWidget(self.extensionsG)
        custL.addLayout(rowL)
        
        self.custTab = QWidget()
        self.custTab.setLayout(custL)

    # RUN SECTION

    def setupRunSection(self): # self.runSection
        # PROGRESS BAR
        self.runLabel = QLabel('Run')
        self.stallLabel = QLabel('Timer')

        self.progressBar = QProgressBar()
        self.progressBar.setValue(0)
        self.progressBar.setFormat('%v')
        self.progressBar.setTextVisible(True)
        self.progressBar.setAlignment(Qt.AlignCenter)

        # RUN BUTTON
        self.runButton = QPushButton('Start')
        self.runButton.clicked.connect(self.runMandalaPush)

        # STOP BUTTON
        self.stopButton = QPushButton('Stop')
        self.stopButton.clicked.connect(self.stopMandalaPush)
        self.stopButton.setVisible(False)
        self.stopTracker = False

        # STALL TIMER BAR DISPLAY
        self.stallTimeSpinBox = QDoubleSpinBox()
        self.stallTimeSpinBox.setRange(1, 600000)
        self.stallTimeSpinBox.setValue(10)
        self.stallTimeSpinBox.setDecimals(1)
        self.stallTimeSpinBox.setSuffix(' s')
        self.stallTimeSpinBox.valueChanged.connect(self.changeStallTimeSpinBox)
        self.stallLimit = self.stallTimeSpinBox.value()

        self.stallTimeProgressBar = QProgressBar()
        self.stallTimeProgressBar.setMaximumHeight(8)
        self.stallTimeProgressBar.setTextVisible(False)

        self.stallTimeCounter = QLabel()
        self.stallTimeCounter.setText(f'{self.stallLimit}0 s')
        self.stallTimeCounter.setVisible(False)

        self.logLabel = QLabel('Log')

        self.logBlock = QTextBrowser()
        self.logBlock.setMinimumHeight(175)
        self.logBlock.setMaximumHeight(175)
        self.logBlock.setLineWrapMode(QTextEdit.NoWrap)

        self.timer = QTimer()
        self.timer.setSingleShot(False)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.updateTimer)

        stallRow = QHBoxLayout()
        stallRow.addWidget(self.stallTimeProgressBar)
        stallRow.addWidget(self.stallTimeSpinBox)
        stallRow.addWidget(self.stallTimeCounter)

        runRow = QHBoxLayout()
        runRow.addWidget(self.progressBar)
        runRow.addWidget(self.runButton)
        runRow.addWidget(self.stopButton) 

        self.runSection = QVBoxLayout()
        self.runSection.addWidget(self.logBlock)
        self.runSection.addLayout(stallRow)
        self.runSection.addLayout(runRow)

    # SIDEBAR SECTION
    
    def setupSideBarSection(self): # self.sideBar
        self.showInvalid = QCheckBox('Log Invalid')

        self.showHelp = QCheckBox('Show Help')
        self.showHelp.setChecked(True)

        self.showHelp.stateChanged.connect(self.setFileCountToolTip)
        self.showHelp.stateChanged.connect(self.setRandomizeFileToolTip)

        self.openRoot = QPushButton('Root')
        self.openRoot.clicked.connect(lambda: os.startfile(self.root))
        
        self.openDest = QPushButton('Destination')
        self.openDest.clicked.connect(lambda: os.startfile(self.dest))
        
        self.openButton = QPushButton('Load')
        self.saveButton = QPushButton('Save')
        self.saveButton.clicked.connect(self.saveConfiguration)
        self.openButton.clicked.connect(self.loadConfiguration)

        self.defaultButton = QPushButton('Set Default')
        self.defaultButton.clicked.connect(lambda: self.guiSave(self.settings))
        self.resetButton = QPushButton('Reset to Default')
        self.resetButton.clicked.connect(lambda: self.guiRestore(self.settings))

        self.sideBar = QVBoxLayout()
        self.sideBar.addSpacing(20)
        self.sideBar.addWidget(self.openButton)
        self.sideBar.addWidget(self.saveButton)
        self.sideBar.addWidget(self.openRoot)
        self.sideBar.addWidget(self.openDest)
        self.sideBar.addWidget(self.defaultButton)
        self.sideBar.addWidget(self.resetButton)
        self.sideBar.addStretch()
        self.sideBar.addWidget(self.showHelp)
        self.sideBar.addWidget(self.showInvalid)
    
    # SETUP UI

    def setupUi(self):
        self.setupSideBarSection()
        self.setupSetupTab()
        self.setupCustomizeTab()
        self.setupRunSection()

        self.mainTabs = QTabWidget()
        self.mainTabs.setTabPosition(QTabWidget.North)
        self.mainTabs.setMovable(True)
        self.mainTabs.addTab(self.setupTab, 'Setup')
        self.mainTabs.addTab(self.custTab, 'Filter')

        masterRow = QHBoxLayout()
        masterRow.addWidget(self.mainTabs)
        masterRow.addLayout(self.sideBar)
        
        masterLayout = QVBoxLayout()
        masterLayout.addLayout(masterRow)
        masterLayout.addLayout(self.runSection)

        self.setLayout(masterLayout)
        self.setWindowTitle('Default - Copy Random Files')
        self.show()

    # TOOL TIPS

    def setFileCountToolTip(self):
        isRandomFiles = self.randomFileG.isChecked()
        numFilesLo = self.numFilesLo.value()
        numFilesHi = self.numFilesHi.value()
        isShowHelp = self.showHelp.isChecked()

        if isShowHelp and not isRandomFiles:
            self.fileCountG.setToolTip(f'{self.noWrap}<font size=4><b>{numFilesLo}</b> file(s) will be copied from <b>{self.root}</b> to <b>{self.dest}</b>')
        elif isShowHelp and isRandomFiles and (numFilesLo <= numFilesHi):
            self.fileCountG.setToolTip(f'{self.noWrap}<font size=4><b>{numFilesLo}</b> to <b>{numFilesHi}</b> files will be copied from <b>{self.root}</b> to <b>{self.dest}</b>') 
        elif isShowHelp and isRandomFiles and (numFilesHi < numFilesLo):
            self.fileCountG.setToolTip(f'{self.noWrap}<font size=4><b>{numFilesHi}</b> to <b>{numFilesLo}</b> files will be copied from <b>{self.root}</b> to <b>{self.dest}</b>')
        else:
            self.fileCountG.setToolTip('')
    
    def setRandomizeFileToolTip(self):
        isRandomFiles = self.randomFileG.isChecked()
        numFilesLo = self.numFilesLo.value()
        numFilesHi = self.numFilesHi.value()
        isShowHelp = self.showHelp.isChecked()
        
        if isShowHelp and not isRandomFiles:
            self.randomFileG.setToolTip(f'{self.noWrap}<font size=5><i>Randomize</i></font>\n<font size=4>'
                                            f'    Uses a randomly selected number between the left ({numFilesLo}) and right ({numFilesHi}) boxes as the file count\n'
                                            f'<b>    Uses the number in the left ({numFilesLo}) box as the file count </b>')
        elif isShowHelp and isRandomFiles:
            self.randomFileG.setToolTip(f'{self.noWrap}<font size=5><i>Randomize</i></font><font size=4>\n'
                                            f'<b>    Uses a randomly selected number between the left ({numFilesLo}) and right ({numFilesHi}) boxes as the file count</b>\n'
                                            f'    Uses the number in the left ({numFilesLo}) box as the file count')
        else:
            self.randomFileG.setToolTip('')






    ### ROOT AND DESTINATION METHODS ###

    def resetPathToStart(self):
        os.chdir(self.root)
        return Path.cwd()

    def changeRoot(self):
        self.root = Path(self.rootCombo.currentText())
    
    def changeDestination(self):
        self.dest = Path(self.destCombo.currentText())

    def browseRoot(self):
        self.rootDirectory = QFileDialog.getExistingDirectory(self, "Select Root Folder", str(self.root))

        if self.rootDirectory:
            if self.rootCombo.findText(self.rootDirectory) == -1:
                self.rootCombo.addItem(self.rootDirectory)
            self.rootCombo.setCurrentIndex(self.rootCombo.findText(self.rootDirectory))
            self.root = Path(self.rootDirectory)

    def browseDestination(self):
        self.destDirectory = QFileDialog.getExistingDirectory(self, "Select Destination Folder",
                str(self.dest))

        if self.destDirectory:
            if self.destCombo.findText(self.destDirectory) == -1:
                self.destCombo.addItem(self.destDirectory)
            self.destCombo.setCurrentIndex(self.destCombo.findText(self.destDirectory))
            self.dest = Path(self.destDirectory)

    def deleteRootItem(self):
        if self.rootCombo.count() == 1:
            return
        else:
            self.rootCombo.removeItem(self.rootCombo.currentIndex())

    def deleteDestItem(self):
        if self.destCombo.count() == 1:
            return
        else:
            self.destCombo.removeItem(self.destCombo.currentIndex())

    ### RUN METHODS ###

    def assignGlobalVariables(self):
        # Global collections
        self.touchedFiles = collections.defaultdict(bool)  # type: ignore
        self.touchedFolders = collections.defaultdict(bool)  # type: ignore
        self.touchedByWeight = collections.defaultdict(bool) # type: ignore
        self.weighted = collections.defaultdict(int)  # type: ignore

        # File Count Variables
        self.isRandFiles = self.randomFileG.isChecked()
        self.numberOfFiles = self.numFilesCount.value()

        # Root and Destination
        self.root = Path(self.rootCombo.currentText())
        self.dest = Path(self.destCombo.currentText())

        # Keyword Variables
        if self.incKeysG.isChecked():
            self.keywords = self.stringToList(self.incKeysEdit.text())
        else:
            self.keywords = []
        
        if self.excKeysG.isChecked():
            self.notKeywords = self.stringToList(self.excKeysEdit.text())
        else:
            self.notKeywords = []

        # Extension Variables
        if self.incExtsG.isChecked():
            self.extensions = self.stringToList(self.incExtsEdit.text())
        else:
            self.extensions = []
        
        if self.excExtsG.isChecked():
            self.notExtensions = self.stringToList(self.excExtsEdit.text())
        else:
            self.notExtensions = []

        # File Size Variables
        self.isRemoveSizeLimit = not self.sizeButton.isChecked()
        if not self.isRemoveSizeLimit:
            self.minSize = self.sizeLo.value()
            self.maxSize = self.sizeHi.value()
            self.convertToBytes()

        # File Length Variables
        self.isRemoveLengthLimit = not self.lengthButton.isChecked()
        if  not self.isRemoveLengthLimit:
            self.maxDuration = self.durationHi.value()
            self.minDuration = self.durationLo.value()
            self.convertToSeconds()

        # Weight Variables
        if self.weightButton.isChecked():
            self.topWeightValue = self.topWeightSpinBox.value()
            self.bottomWeightValue = self.bottomWeightSpinBox.value()
        else:
            self.topWeightValue = 0
            self.bottomWeightValue = 0
        

        # Folder Variables
        self.makeFoldersUnique = self.makeFoldersUniqueCheck.isChecked()
        self.nameOfFolders = self.nameOfFoldersEntry.text()
        self.isCreateFolders = self.folderButton.isChecked()

        # Folder Count
        if self.isCreateFolders:
            self.numFolders = self.numFoldersCount.value()
        else:
            self.numFolders = 1
        
        # Filename Variables
        if self.fileNameButton.isChecked():
            self.indexFiles = self.indexFilesRadio.isChecked()
            self.renameFiles = self.renameFilesRadio.isChecked()
            self.renameName = self.renameNameEntry.text()
        else:
            self.indexFiles = False
            self.renameFiles = False
            self.renameName = ''
        
        # Trash Variables
        if self.trashButton.isChecked():
            self.trashEmptyFolders = self.isTrashEmpty.isChecked()
            self.trashSourceFiles = self.isTrashSource.isChecked()
            self.trashInvalidFiles = self.isTrashInvalid.isChecked()
        else:
            self.trashEmptyFolders = False
            self.trashSourceFiles = False
            self.trashInvalidFiles = False

        self.startAbsolute = os.path.abspath(self.root)
        self.rename2 = ' '
        self.isAppendLog = False
        self.count = 0
        self.bytesInCurrentFolder = 0
        self.startFolderTime = perf_counter() 
        self.startStallTime = perf_counter()

    def runMandala(self):
        self.assignGlobalVariables()

        for folder in range(self.numFolders):
            if self.stopTracker:
                self.stopMandala()
                return

            # If you don't want unique folders, clear the touched dictionaries and restart
            if self.makeFoldersUnique:
                self.touchedFolders[self.startAbsolute] = False
                for key in self.touchedByWeight.keys():
                    self.touchedFolders[key] = False
                    self.touchedFiles[key] = False  
            else:
                self.touchedFiles = collections.defaultdict(bool)  # type: ignore
                self.touchedFolders = collections.defaultdict(bool)  # type: ignore
            
            self.dest = Path(self.destCombo.currentText())
            
            topWeightMark = ''
            self.weighted = collections.defaultdict(int)
            self.touchedByWeight = collections.defaultdict(bool) # type: ignore

            self.bytesInCurrentFolder = 0
            self.count = 0
            self.dest = self.createFolders(self.dest)
            
            dummyFile = self.log.name + '.tmp'
            self.dummyLog = open(dummyFile, 'a', encoding='utf-8')

            self.startFolderTime = perf_counter() 
            self.startStallTime = perf_counter()
            mainPath = self.resetPathToStart() 

            # File Count
            if self.isRandFiles:
                self.numberOfFiles = random.randint(self.numFilesLo.value(), self.numFilesHi.value())
            self.progressBar.setRange(0, self.numberOfFiles)

            for currFile in range(self.numberOfFiles):
                if self.stopTracker:
                    self.stopMandala()
                    return
                if self.touchedFolders[self.startAbsolute] and self.isTimedOut(self.startStallTime):
                    break

                while not self.touchedFolders[self.startAbsolute] and not self.isTimedOut(self.startStallTime):
                    if self.stopTracker:
                        self.stopMandala()
                        return
                    mainPathAbsolute = os.path.abspath(mainPath)
                    # Try to get main path
                    try:
                        if not self.listOfPaths[mainPathAbsolute]:
                            self.listOfPaths[mainPathAbsolute] = os.listdir(mainPath)
                    except PermissionError: 
                        self.touchedFolders[mainPathAbsolute] = True 
                        mainPath = self.resetPathToStart()
                        continue
                        
                    # If folder is empty
                    if (len(self.listOfPaths[mainPathAbsolute]) == 0): 
                        self.touchedFolders[mainPathAbsolute] = True
                        if self.trashEmptyFolders: send2trash.send2trash(str(mainPathAbsolute))
                        mainPath = self.resetPathToStart()
                    # If the folder is not empty
                    else: 
                        # Chooses random path and stores absolute path
                        randomPath = Path(random.choice(self.listOfPaths[mainPathAbsolute]))
                        randomPathAbsolute = os.path.abspath(randomPath)
                        # If touched, try again:
                        if self.touchedFiles[randomPathAbsolute] or self.touchedFolders[randomPathAbsolute]:
                            self.touchFolderIfAllFilesTouched(self.listOfPaths[mainPathAbsolute], mainPathAbsolute)
                            mainPath = self.resetPathToStart()          
                        # If random path is folder
                        elif randomPath.is_dir():
                            try:
                                os.chdir(randomPath)
                                mainPath = Path.cwd()
                                if self.topWeightValue > 0 and Path(randomPathAbsolute).parent == self.root:
                                    topWeightMark = randomPathAbsolute

                            except PermissionError:
                                self.touchedFolders[randomPathAbsolute] = True 
                                mainPath = self.resetPathToStart()

                        # If random path is file:
                        elif randomPath.is_file():
                            # Touch the file and get size
                            self.touchedFiles[randomPathAbsolute] = True
                            randomPathSize = os.path.getsize(randomPath)
                            randomPathRelative = os.path.relpath(randomPath, self.root)
                            # If file is valid
                            if self.isValidFile(randomPath, randomPathSize) and self.copyFilesToTarget(currFile, randomPath, self.dest, randomPathSize):
                                if not self.isAppendLog:
                                    self.log.write(f'{currFile+1}: {randomPathRelative}\n')
                                    self.signals.logSignal.emit(f'{currFile+1}: {randomPathRelative}')
                                else:
                                    self.dummyLog.write(f'{currFile+1}: {randomPathRelative}\n')
                                    self.signals.logSignal.emit(f'{currFile+1}: {randomPathRelative}')
                                    
                                self.bytesInCurrentFolder += randomPathSize
                                self.count += 1
                                self.signals.countSignal.emit()
                                self.startStallTime = perf_counter()
                                self.signals.timeSignal.emit()

                                if self.trashSourceFiles: 
                                    send2trash.send2trash(str(randomPathAbsolute))
                                
                                if self.topWeightValue > 0:
                                    self.weighted[topWeightMark] += 1
                                    if self.weighted[topWeightMark] == self.topWeightValue:
                                        self.touchedFolders[topWeightMark] = True
                                        self.touchedByWeight[topWeightMark] = True

                                if self.bottomWeightValue > 0: 
                                    self.weighted[mainPathAbsolute] += 1
                                    if self.weighted[mainPathAbsolute] == self.bottomWeightValue:
                                        self.touchedFolders[mainPathAbsolute] = True
                                        self.touchedByWeight[mainPathAbsolute] = True
                                
                                #topWeightMark = ' '
                                mainPath = self.resetPathToStart()                               
                                break
                            # If file is invalid
                            else:
                                if self.showInvalid.isChecked() and self.count < 100:
                                    self.signals.logSignal.emit(f'**: {randomPathRelative}')
                                elif self.showInvalid.isChecked() and self.count >= 100:
                                    self.signals.logSignal.emit(f'***: {randomPathRelative}')
                                elif self.showInvalid.isChecked() and self.count >= 1000:
                                    self.signals.logSignal.emit(f'****: {randomPathRelative}')
                                
                                if self.trashInvalidFiles: 
                                    send2trash.send2trash(str(randomPathAbsolute))
                                
                                mainPath = self.resetPathToStart()      

            ##################################################   END OF FOLDER  ##################################################           
            # Create and write log at the end of folder
            self.dummyLog.close()
            self.log.close()
            self.signals.logSignal.emit(self.writeStatusLog())
            # Terminates the program if no files were collected
            if self.count == 0 and self.isCreateFolders: 
                shutil.rmtree(self.dest)
                break
            elif self.count == 0 and not self.isCreateFolders and not self.isAppendLog: 
                os.remove(self.log.name)

        self.stopMandala()
    
    def isValidFile(self, source, size):
        # If anything remains False the file is invalid
        isExtension = False
        isKeyword = False
        isWithinSizeRange = False
        isWithinDuration = False

        # If no limit, all valid, else checks valid size range. Returns immediately if neither
        if self.isRemoveSizeLimit:
            isWithinSizeRange = True
        elif self.minSize <= size <= self.maxSize:
            isWithinSizeRange = True
        else:
            return False

        # If a blacklist extension or keyword is found, immediately return invalid
        for notExtension in self.notExtensions:
            if re.compile(rf'\.{notExtension}$', re.I).search(source.suffix) != None:
                return False
        for notKeyword in self.notKeywords:
            if re.compile(rf'(.*){notKeyword}(.*)', re.I).search(source.stem) != None:
                return False

        # If no extension or keyword, all valid.
        # If whitelist item found, immediately breaks
        if not self.extensions:
            isExtension = True
        else:
            for extension in self.extensions:
                if re.compile(rf'\.{extension}$', re.I).search(source.suffix) != None:
                    isExtension = True
                    break
        if not self.keywords:
            isKeyword = True
        else:    
            for notKeyword in self.keywords:
                if re.compile(rf'(.*){notKeyword}(.*)', re.I).search(source.stem) != None:
                    isKeyword = True
                    break
        
        # If a duration can be get it will be checked, otherwise skips
        if self.isRemoveLengthLimit:
            isWithinDuration = True
        else:
            try:
                sound = soundfile.SoundFile(source)
                duration = len(sound) / sound.samplerate
                if self.minDuration <= duration <= self.maxDuration:
                    isWithinDuration = True
                else:
                    return False
            except RuntimeError:
                if source.suffix == '.mp3':
                    try:
                        duration = MP3(source).info.length
                        if self.minDuration <= duration <= self.maxDuration:
                            isWithinDuration = True
                        else:
                            return False
                    except:
                        isWithinDuration = True
                else:
                    isWithinDuration = True
            except:
                isWithinDuration = True
        
        # Checks that everything is True
        if isExtension and isKeyword and isWithinSizeRange and isWithinDuration:
            return True
        else:
            return False

    def copyFilesToTarget(self, fileNum, source, dest, sourceSize):
        sourceAbsolute = os.path.abspath(source)
        sourceName = source.name
        try:
            if self.indexFiles:
                shutil.copy(sourceAbsolute, dest / f'{fileNum+1}.{sourceName}')
            elif self.renameFiles:
                if not (dest / f'{self.renameName} {fileNum+1}{source.suffix}').exists():
                    shutil.copy(sourceAbsolute, dest / f'{self.renameName} {fileNum+1}{source.suffix}')
                    self.rename2 = f'{self.renameName} {fileNum+1}'
                else:
                    x = 1
                    while (dest / f'{self.renameName} {fileNum+x}{source.suffix}').exists():
                        x += 1
                    shutil.copy(sourceAbsolute, dest / f'{self.renameName} {fileNum+x}{source.suffix}')
                    self.rename2 = f'{self.renameName} {fileNum+x}'
            else:
                x = 2
                while (dest / f'{sourceName}').exists():
                    if sourceSize == os.path.getsize(dest / f'{sourceName}'):
                        return False
                    sourceName = source.stem + f' ({x})' + source.suffix
                    x += 1
                shutil.copy(sourceAbsolute, dest / f'{sourceName}')
            return True
        except PermissionError:
            return False
    
    def createFolders(self, target):
        if not self.isCreateFolders:
            if Path(target/f'!{target.name}_log.txt').exists():
                self.isAppendLog = True
            else:
                self.isAppendLog = False
            self.log = open(target/f'!{target.name}_log.txt', 'a', encoding='utf-8')
        else:
            try:
                Path(f'{target}/{self.nameOfFolders}').mkdir()
                target = target/f'{self.nameOfFolders}'
                self.log = open(target/f'!{self.nameOfFolders}_log.txt', 'a', encoding='utf-8')
            except FileExistsError:
                for x in range(len(os.listdir(target))):
                    try:
                        Path(f'{target}/{self.nameOfFolders} {x+2}').mkdir()
                        target = target/f'{self.nameOfFolders} {x+2}'
                        self.log = open(target/f'!{self.nameOfFolders} {x+2}_log.txt', 'a', encoding='utf-8')
                        break
                    except FileExistsError: 
                        continue
        return target

    def touchFolderIfAllFilesTouched(self, listOfPath, absolutePath):
        for fileFolder in listOfPath:
            path = os.path.abspath(fileFolder)
            if self.touchedFiles[path] or self.touchedFolders[path]:
                pass
            else:
                return
        self.touchedFolders[absolutePath] = True
    
    ### PROGRESS, TIMER METHODS ###

    def changeStallTimeSpinBox(self):
        self.stallLimit = self.stallTimeSpinBox.value()
        self.stallTimeCounter.setText(f'{self.stallLimit}0 s')

    def isTimedOut(self, startStallTime):
        endStallTime = perf_counter()
        if endStallTime - startStallTime > self.stallLimit: 
            return True
        else: 
            return False

    def updateTimer(self):
        self.stallTimeProgressBar.setValue(self.stallTimeProgressBar.value() - 1)
        self.stallTimeCounter.setText(f'{self.stallTimeProgressBar.value()/100} s')

    def runMandalaPush(self):
        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QWidget) and not (name in ['stopButton', 'logBlock']):
                self.wasEnabled[name] = obj.isEnabled()

        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QWidget) and not (name in ['stopButton', 'logBlock']):
                obj.setEnabled(False)

        self.progressBar.reset()
        self.stallTimeProgressBar.setRange(0, self.stallLimit * 100)
        self.stallTimeProgressBar.setValue(self.stallTimeProgressBar.maximum())
        self.stallTimeCounter.setText(f'{self.stallTimeProgressBar.value()/100} s')

        self.timer.start(10)

        self.runButton.setVisible(False)
        self.stopButton.setVisible(True)
        self.stallTimeCounter.setVisible(True)
        self.stallTimeSpinBox.setVisible(False)
        self.stopTracker = False

        self.threadpool.globalInstance().start(self.mandala)

    def stopMandalaPush(self):
        self.stopTracker = True
    
    def stopMandala(self):
        self.signals.finishedSignal.emit()

        self.dummyLog.close()
        self.log.close()
        self.signals.logSignal.emit(self.writeStatusLog())
        
        self.runButton.setVisible(True)
        self.stopButton.setVisible(False)
        self.stallTimeCounter.setVisible(False)
        self.stallTimeSpinBox.setVisible(True)
        self.stallTimeCounter.setText(f'{self.stallLimit}0 s')
        self.dest = Path(self.destCombo.currentText())
        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QWidget) and not (name in ['stopButton', 'logBlock']):
                obj.setEnabled(self.wasEnabled[name])
        


    ### LOG METHODS ###

    def writeStatusLog(self):
        endFolderTime = perf_counter()
        endStallTime = perf_counter()
        currentDate = datetime.datetime.now().strftime('%B %d, %Y')
        currentTime = datetime.datetime.now().strftime('%I:%M:%S%p')
        status = ''
        timeOut = self.isTimedOut(self.startStallTime)

        if self.count == self.numberOfFiles:
            status = f'SUCCESS: {self.count}/{self.numberOfFiles} files copied'
        elif timeOut and self.count == 0 and self.isCreateFolders: 
            status = f'NO FILES FOUND: timed out | folder deleted'
        elif self.touchedFolders[self.startAbsolute] and self.count == 0 and self.isCreateFolders: 
            status = f'NO FILES FOUND: all files searched | folder deleted'
        elif self.touchedFolders[self.startAbsolute]: 
            status = f'ALL FILES SEARCHED: {self.count}/{self.numberOfFiles} files copied'
        elif timeOut: 
            status = f'TIMED OUT: {self.count}/{self.numberOfFiles} files copied'
        elif self.stopTracker:
            status = f'STOPPED: {self.count}/{self.numberOfFiles} files copied'       
        statusLog = f'''------------------------------------------------------------------------
{status}
------------------------------------------------------------------------
Date:\t\t{currentDate}
Time:\t\t{currentTime}
Start:\t\t{self.root} 
Destination:\t{self.dest}
Extensions:\t{self.printExtensions()}
Keywords:\t{self.printKeywords()}
Total size:\t{self.byteToMbGb(self.bytesInCurrentFolder)}
Total runtime:\t{round(endFolderTime - self.startFolderTime, 2)}s      
------------------------------------------------------------------------'''
        statusLogApp = f'''------------------------------------------------------------------------
{status}
------------------------------------------------------------------------
Date:\t{currentDate}
Time:\t{currentTime}
Start:\t{self.root} 
Destination:\t{self.dest}
Extensions:\t{self.printExtensions()}
Keywords:\t{self.printKeywords()}
Total size:\t{self.byteToMbGb(self.bytesInCurrentFolder)}
Total runtime:\t{round(endFolderTime - self.startFolderTime, 2)}s      
------------------------------------------------------------------------'''
        self.prependStatusToLog(statusLog)
        return statusLogApp

    def prependStatusToLog(self, status):
        dummyFile = self.log.name + '.tmp'
        # IF ITS A NEW LOG, APPEND STATUS
        if not self.isAppendLog:
            with open(self.log.name, 'r', encoding='utf-8') as read_obj, open(dummyFile, 'w', encoding='utf-8') as write_obj:
                write_obj.write(status + '\n')
                for status in read_obj:
                    write_obj.write(status)
            os.remove(self.log.name)
            os.rename(dummyFile, self.log.name)
        else:
            with open(dummyFile, 'r', encoding='utf-8') as read_obj, open(self.log.name, 'a', encoding='utf-8') as write_obj:
                write_obj.write(status + '\n')
                for status in read_obj:
                    write_obj.write(status)
            os.remove(dummyFile)

    def printKeywords(self):
        KeywordsStatus = ''
        for keyword in self.keywords:
            if keyword != self.keywords[-1]:
                KeywordsStatus += '"' + keyword + '"' + ', '
            else:
                KeywordsStatus += '"' + keyword + '"'
                return KeywordsStatus

    def printExtensions(self):
        ExtensionsStatus = ''
        for extension in self.extensions:
            if extension != self.extensions[-1]: 
                ExtensionsStatus += '.' + extension + ', '
            else:
                ExtensionsStatus += '.' + extension
                return ExtensionsStatus

    ### FILE COUNT METHODS ###

    def switchFileCount(self):
        if not self.randomFileG.isChecked():
            return
        else:
            lo = self.numFilesLo.value()
            hi = self.numFilesHi.value()
            if lo > hi:
                self.numFilesLo.setValue(hi)
                self.numFilesHi.setValue(lo)

    def changeFileLabelRand(self):
        r = self.randomFileG.isChecked()
        self.countFileG.setChecked(not r)
        for child in self.randomFileG.children():
            child.setEnabled(r)
        for child in self.countFileG.children():
            child.setEnabled(not r)
    
    def changeFileLabelCount(self):
        r = self.countFileG.isChecked()
        self.randomFileG.setChecked(not r)
        for child in self.countFileG.children():
            child.setEnabled(r)
        for child in self.randomFileG.children():
            child.setEnabled(not r)

    ### FILE SIZE METHODS ###
    
    def switchSize(self):
        lo = self.sizeLo.value()
        hi = self.sizeHi.value()
        if lo > hi:
            self.sizeLo.setValue(hi)
            self.sizeHi.setValue(lo)

    def convertToBytes(self):
        byteInKilobyte = 1024
        byteInMegabyte = 1048576
        byteInGigabyte = 1073741824
        currentText = self.sizeType.currentText()

        if currentText == 'B':
            self.minSize = round(self.sizeLo.value(), 2)
            self.maxSize = round(self.sizeHi.value(), 2)
        elif currentText == 'KB':
            self.minSize = round(self.sizeLo.value() * byteInKilobyte, 2)
            self.maxSize = round(self.sizeHi.value() * byteInKilobyte, 2)
        elif currentText == 'MB':
            self.minSize = round(self.sizeLo.value() * byteInMegabyte, 2)
            self.maxSize = round(self.sizeHi.value() * byteInMegabyte, 2)  
        elif currentText == 'GB':
            self.minSize = round(self.sizeLo.value() * byteInGigabyte, 2)
            self.maxSize = round(self.sizeHi.value() * byteInGigabyte, 2)

    def byteToMbGb(self, bytesInCurrentFolder):
        BYTE_TO_MEGABYTE = 9.53674316406 * 10**(-7)
        BYTE_TO_GIGABYTE = 9.31322575 * 10**(-10)
        byteInGigabyte = 1073741824
        if bytesInCurrentFolder < byteInGigabyte - 1:
            return f'{round(bytesInCurrentFolder * BYTE_TO_MEGABYTE, 2)} MB'
        else:
            return f'{round(bytesInCurrentFolder * BYTE_TO_GIGABYTE, 2)} GB'

    ### FILE DURATION METHODS ###
    
    def switchDuration(self):
        lo = self.durationLo.value()
        hi = self.durationHi.value()
        if lo > hi:
            self.durationLo.setValue(hi)
            self.durationHi.setValue(lo)
    
    def convertToSeconds(self):
        secondsInMinute = 60
        if self.durationType.currentText() == 'm':
            self.minDuration = self.durationLo.value() * secondsInMinute
            self.maxDuration = self.durationHi.value() * secondsInMinute

    ### KEYWORDS AND EXTENSION METHODS ###

    def switchKeys(self):
        include = self.incKeysEdit.text()
        self.incKeysEdit.setText(self.excKeysEdit.text())
        self.excKeysEdit.setText(include)

    def switchExts(self):
        include = self.incExtsEdit.text()
        self.incExtsEdit.setText(self.excExtsEdit.text())
        self.excExtsEdit.setText(include)

    def stringToList(self, string):
        li = list(string.split(' '))
        if len(li) == 1 and li[0] == '':
            return []
        else:
            return li

    ### SETTINGS METHODS ###

    def closeEvent(self, event):
        # Saves geometry, help, invalid and tab position
        self.globalSettingsSave()

    def globalSettingsSave(self):
        # Save geometry
        self.settings.setValue('size', self.size())
        self.settings.setValue('pos', self.pos())

        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QCheckBox) and (name in ['showInvalid', 'showHelp']):
                value = obj.isChecked()
                self.settings.setValue(name, value)

            if isinstance(obj, QTabWidget):
                value = obj.currentIndex()
                self.settings.setValue(name, value)

    def globalSettingsRestore(self):
        # Restore geometry  
        self.resize(self.settings.value('size', QSize(500, 500)))
        self.move(self.settings.value('pos', QPoint(60, 60)))

        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QCheckBox) and (name in ['showInvalid', 'showHelp']):
                value = self.settings.value(name)
                if value != None:
                    obj.setChecked(strtobool(value))

            if isinstance(obj, QTabWidget):
                value = self.settings.value(name)
                if value != None:
                    obj.setCurrentIndex(int(value))

    def saveConfiguration(self):
        saveFile, config = QFileDialog.getSaveFileName(self, 'Save Current Configuration', 'config.ini',('Configuration (*.ini)'))
        if saveFile:
            with open(saveFile, 'w', encoding='utf-8') as save:
                settings = QSettings(saveFile, QSettings.IniFormat)
                self.guiSave(settings)
            name = list(settings.fileName().split('/'))[-1][:-4]
            self.setWindowTitle(f'{name} - Copy Random Files')

    def loadConfiguration(self):
        openFile, config = QFileDialog.getOpenFileName(self, 'Load Configuration', '', ('Configuration (*.ini)'))
        if openFile:
            with open(openFile, 'r', encoding='utf-8') as load:
                settings = QSettings(openFile, QSettings.IniFormat)
                self.guiRestore(settings)
            name = list(settings.fileName().split('/'))[-1][:-4]
            self.setWindowTitle(f'{name} - Copy Random Files')

    def guiSave(self, settings):
        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QComboBox):
                items = []
                for item in range(obj.count()):
                    items.append(obj.itemText(item))
                settings.setValue(name, items)  # save combobox selection to registry

                index = obj.currentIndex()  # get current index from combobox
                text = obj.itemText(index)  # get the text for current index
                settings.setValue(f'current{name}', text)

            if isinstance(obj, QLineEdit):
                value = obj.text()
                settings.setValue(name, value)  # save ui values, so they can be restored next time
            
            if isinstance(obj, QCheckBox) and not (name in ['showInvalid', 'showHelp']):
                state = obj.isChecked()
                settings.setValue(name, state)
            
            if isinstance(obj, QRadioButton):
                value = obj.isChecked()  # get stored value from registry
                settings.setValue(name, value)

            if isinstance(obj, QSpinBox):
                value = obj.value()
                settings.setValue(name, value)
            
            if isinstance(obj, QDoubleSpinBox):
                value = obj.value()
                settings.setValue(name, value)

            if isinstance(obj, QPushButton):
                value = obj.isChecked()
                settings.setValue(name, value)

    def guiRestore(self, settings):
        for name, obj in inspect.getmembers(self):
            if isinstance(obj, QComboBox):
                obj.clear()
                allItems = (settings.value(name))
                if allItems != None:
                    obj.addItems(allItems)
                
                value = (settings.value(f'current{name}'))
                if obj.findText(value) == -1:
                    obj.addItem(value)
                obj.setCurrentIndex(obj.findText(value))

            if isinstance(obj, QLineEdit):
                value = settings.value(name)  # get stored value from registry
                obj.setText(value)  # restore lineEditFile
            
            if isinstance(obj, QCheckBox) and not (name in ['showInvalid', 'showHelp']):
                value = settings.value(name)  # get stored value from registry
                if value != None:
                    try:
                        obj.setChecked(value)
                    except TypeError:
                        obj.setChecked(strtobool(value))

            if isinstance(obj, QRadioButton):
                value = settings.value(name)  # get stored value from registry
                if value != None:
                    try:
                        obj.setChecked(value)
                    except TypeError:
                        obj.setChecked(strtobool(value))
            
            if isinstance(obj, QSpinBox):
                value = settings.value(name)
                if value != None:
                    try:
                        obj.setValue(value)
                    except TypeError:
                        obj.setValue(int(value))
            
            if isinstance(obj, QDoubleSpinBox):
                value = settings.value(name)
                if value != None:
                    try:
                        obj.setValue(value)
                    except TypeError:
                        obj.setValue(float(value))
            
            if isinstance(obj, QPushButton):
                value = settings.value(name)  # get stored value from registry
                if value != None:
                    try:
                        obj.setChecked(value)
                    except TypeError:
                        obj.setChecked(strtobool(value))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    with open('CRFStyleSheet.qss', 'r') as f:
        style = f.read()
        window.setStyleSheet(style)
    sys.exit(app.exec_())
