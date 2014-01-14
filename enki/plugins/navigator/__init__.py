"""Navigator dock widget and functionality
"""

import os.path
import threading

from PyQt4.QtCore import pyqtSignal, QObject, Qt, QThread, QTimer
from PyQt4.QtGui import QFileDialog, QIcon, QWidget
from PyQt4 import uic


from enki.core.core import core
from enki.core.uisettings import TextOption

import ctags
from dock import NavigatorDock


# source map. 1 ctags language is mapped to multiply Qutepart languages
# NOTE this map must be updated after new languages has been added to ctags or Qutepart
#  Initially filled on Qutepart 1.1.0 and Ctags 5.9~svn20110310
_CTAGS_TO_QUTEPART_LANG_MAP = {
    "Asm": ("AVR Assembler", "GNU Assembler", "MIPS Assembler",
            "Asm6502", "Intel x86 (NASM)", "Motorola 68k (VASM/Devpac)", "PicAsm"),
    "Asp": ("ASP",),
    "Awk": ("AWK",),
    "Basic": ("FreeBASIC", "KBasic", "MonoBasic", "PureBasic", "TI Basic"),
    "C": ("C",),
    "C#": ("C#",),
    "C++": ("C++",),
    "DosBatch": ("MS-DOS Batch",),
    "Eiffel": ("Eiffel",),
    "Erlang": ("Erlang",),
    "Flex": ("Lex/Flex",),
    "Fortran": ("Fortran",),
    "Go": ("Go",),
    "HTML": ("Django HTML Template", "HTML", "Ruby/Rails/RHTML"),
    "Java": ("Java",),
    "JavaScript": ("JavaScript",),
    "Lisp": ("Common Lisp",),
    "Lua": ("Lua",),
    "Make": ("Makefile",),
    "Matlab": ("Matlab",),
    "ObjectiveC": ("Objective-C", "Objective-C++"),
    "OCaml": ("Objective Caml",),
    "Pascal": ("Pascal",),
    "Perl": ("Perl",),
    "PHP": "PHP/PHP",
    "Python": ("Python",),
    "REXX": ("REXX",),
    "Ruby": ("Ruby",),
    "Scheme": ("Scheme",),
    "Sh": ("Zsh", "Bash"),
    "SML": ("SML",),
    "SQL": ("SQL", "SQL (MySQL)", "SQL (PostgreSQL)"),
    "Tcl": ("Tcl/Tk",),
    "Tex": ("LaTeX", "Texinfo"),
    "Vera": ("Vera",),
    "Verilog": ("Verilog",),
    "VHDL": ("VHDL",),
    "YACC": ("Yacc/Bison",)
}

# build reverse map
_QUTEPART_TO_CTAGS_LANG_MAP = {}
for ctagsLang, qutepartLangs in _CTAGS_TO_QUTEPART_LANG_MAP.iteritems():
    for qutepartLang in qutepartLangs:
        _QUTEPART_TO_CTAGS_LANG_MAP[qutepartLang] = ctagsLang



class ProcessorThread(QThread):
    """Thread processes text with ctags and returns tags
    """
    tagsReady = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self):
        QThread.__init__(self)
        self._ctagsLang = None
        self._text = None
        self._haveData = False
        self._lock = threading.Lock()

    def process(self, ctagsLang, text):
        """Parse text and emit tags
        """
        with self._lock:
            self._ctagsLang = ctagsLang
            self._haveData = True
            self._text = text
            if not self.isRunning():
                self.start(QThread.LowPriority)

    def run(self):
        """Thread function
        """
        while True:  # exits with break
            with self._lock:
                ctagsLang = self._ctagsLang
                text = self._text
                self._haveData = False

            result = ctags.processText(ctagsLang, text)

            if isinstance(result, basestring):
                self.error.emit(result)
                break
            else:
                tags = result

                with self._lock:
                    if not self._haveData:
                        self.tagsReady.emit(tags)
                        break
                    # else - next iteration




class SettingsWidget(QWidget):
    """Settings widget. Insertted as a page to UISettings
    """
    def __init__(self, *args):
        QWidget.__init__(self, *args)
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'Settings.ui'), self)
        self.pbCtagsPath.clicked.connect(self._onPbCtagsPathClicked)

    def _onPbCtagsPathClicked(self):
        path = QFileDialog.getOpenFileName(core.mainWindow(), 'Ctags path')
        if path:
            self.leCtagsPath.setText(path)


class Plugin(QObject):
    """Main class. Interface for the core.
    """
    def __init__(self):
        QObject.__init__(self)
        self._dock = None
        core.workspace().currentDocumentChanged.connect(self._onDocumentChanged)
        core.workspace().textChanged.connect(self._onTextChanged)

        core.uiSettingsManager().aboutToExecute.connect(self._onSettingsDialogAboutToExecute)

        # If we update Tree on every key pressing, freezes are sensible (GUI thread draws tree too slowly
        # This timer is used for drawing Preview 1000 ms After user has stopped typing text
        self._typingTimer = QTimer()
        self._typingTimer.setInterval(1000)
        self._typingTimer.setSingleShot(True)
        self._typingTimer.timeout.connect(self._scheduleDocumentProcessing)

        self._thread = ProcessorThread()

    def del_(self):
        """Uninstall the plugin
        """
        if self._dock is not None:
            self._thread.tagsReady.disconnect(self._dock.setTags)
            self._thread.error.disconnect(self._dock.onError)
            self._dock.remove()
        self._typingTimer.stop()
        self._thread.wait()

    def _createDock(self):
        self._dock = NavigatorDock()
        self._dock.setVisible(False)
        self._dock.closed.connect(self._onDockClosed)

        self._dock.showAction().triggered.connect(self._onDockShown)
        self._thread.tagsReady.connect(self._dock.setTags)
        self._thread.error.connect(self._dock.onError)

    def _isEnabled(self):
        return core.config()['Navigator']['Enabled']

    def _isSupported(self, document):
        return document is not None and \
               document.qutepart.language() in _QUTEPART_TO_CTAGS_LANG_MAP

    def _onDockClosed(self):
        """Dock has been closed by a user. Change Enabled option
        """
        core.config()['Navigator']['Enabled'] = False
        core.config().flush()

    def _onDockShown(self):
        """Dock has been shown by a user. Change Enabled option
        """
        core.config()['Navigator']['Enabled'] = True
        core.config().flush()
        self._scheduleDocumentProcessing()

    def _onDocumentChanged(self, old, new):
        if self._isSupported(new):
            if self._dock is None:
                self._createDock()
            self._dock.install()
            if self._isEnabled():
                self._dock.show()
                self._scheduleDocumentProcessing()
        else:
            self._clear()
            if self._dock is not None:
                self._dock.remove()

    def _onTextChanged(self):
        if self._isEnabled():
            self._typingTimer.stop()
            self._typingTimer.start()

    def _clear(self):
        if self._dock is not None:
            self._dock.setTags([])

    def _scheduleDocumentProcessing(self):
        """Start document processing with the thread.
        """
        self._typingTimer.stop()

        document = core.workspace().currentDocument()
        if document is not None and \
           document.qutepart.language() in _QUTEPART_TO_CTAGS_LANG_MAP:
            ctagsLang = _QUTEPART_TO_CTAGS_LANG_MAP[document.qutepart.language()]
            self._thread.process(ctagsLang, document.qutepart.text)

    def _onSettingsDialogAboutToExecute(self, dialog):
        """UI settings dialogue is about to execute.
        Add own options
        """
        widget = SettingsWidget(dialog)

        dialog.appendPage(u"Navigator", widget, QIcon(':/enkiicons/goto.png'))

        # Options
        dialog.appendOption(TextOption(dialog, core.config(),
                                       "Navigator/CtagsPath", widget.leCtagsPath))