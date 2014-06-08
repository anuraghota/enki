# .. -*- coding: utf-8 -*-
#
# ********************************************
# preview.py - HTML, Markdown and ReST preview
# ********************************************

# Imports
# =======
# Library imports
# ---------------
import os.path
import collections
import Queue
import re
import subprocess
import traceback

# Third-party imports
# -------------------
from PyQt4.QtCore import pyqtSignal, QSize, Qt, QThread, QTimer, QUrl
from PyQt4.QtGui import QDesktopServices, QFileDialog, QIcon, QMessageBox, QWidget
from PyQt4.QtWebKit import QWebPage
from PyQt4 import uic
import StringIO
import traceback

# Local imports
# -------------
from enki.core.core import core
from enki.widgets.dockwidget import DockWidget
from enki.plugins.preview import isHtmlFile
from preview_sync import PreviewSync

# Likewise, attempt importing CodeChat; failing that, disable the CodeChat feature.
try:
    import CodeChat.CodeToRest as CodeToRest
    import CodeChat.LanguageSpecificOptions as LSO
except ImportError:
    CodeToRest = None
    LSO = None


class ConverterThread(QThread):
    """Thread converts markdown to HTML
    """
    htmlReady = pyqtSignal(unicode, unicode, unicode, QUrl)

    _Task = collections.namedtuple("Task", ["filePath", "language", "text"])

    def __init__(self):
        QThread.__init__(self)
        self._queue = Queue.Queue()
        self.start(QThread.LowPriority)
        # Executable to run the HTML builder.
        self.htmlBuilderCommandLine = (u'sphinx-build ' +
          # Place doctrees in the ``_build`` directory; by default, Sphinx places this in _build/html/.doctrees.
          u'-d _build\\doctrees ' +
          # Source directory
          u'. ' +
          # Build directory
          u'_build\\html')
        # Path to the root directory of an HTML builder.
        self.htmlBuilderRootPath = u'D:\\tp'
        # Path to the output produced by the HTML builder.
        self.htmlBuilderOutputPath = self.htmlBuilderRootPath + u'\\_build\\html'
        # Extension for resluting HTML files
        self.htmlBuilderExtension = u'.html'

    def process(self, filePath, language, text):
        """Convert data and emit result
        """
        self._queue.put(self._Task(filePath, language, text))

    def stop_async(self):
        self._queue.put(None)

    def hasContentsRst(self):
    	return 'contents.rst' in os.listdir(self.htmlBuilderRootPath)
    	
    def _getHtml(self, language, text, filePath):
        """Get HTML for document
        """
        if language == 'HTML':
            return text, None, QUrl()
        elif language == 'Markdown':
            return self._convertMarkdown(text), None, QUrl()
        elif language == 'Restructured Text':
            htmlUnicode, errString = self._convertReST(text)
            return htmlUnicode, errString, QUrl()
        else:
            # Use CodeToRest module to perform code to rst to html conversion,
            # if CodeToRest is installed.
            if filePath and LSO and CodeToRest and not self.hasContentsRst():
                # Use StringIO to pass codechat compilation information to UI.
                errStream = StringIO.StringIO()
                lso = LSO.LanguageSpecificOptions()
                fileName, fileExtension = os.path.splitext(filePath)
                # Check to seee if CodeToRest supportgs this file's extension.
                if fileExtension not in lso.extension_to_options.keys():
                    return 'No preview for this type of file', None
                # CodeToRest can render this file. Do so.
                lso.set_language(fileExtension)
                htmlString = CodeToRest.code_to_html_string(text, lso, errStream)
                errString = errStream.getvalue()
                errStream.close()
                return htmlString, errString, QUrl()
            # Look for HTML builder output. First, see if the current file is
            # within the subtree of self.htmlBuilderRootPath. See
            # http://stackoverflow.com/questions/7287996/python-get-relative-path-from-comparing-two-absolute-paths for more discussion.
            elif self.hasContentsRst():
				if filePath and  filePath.startswith(self.htmlBuilderRootPath):
                # Run the builder.
                self._runHtmlBuilder()
            
                    # Next, create an htmlPath as self.htmlBuilderOutputPath + remainder of htmlRelPath
                    htmlPath = os.path.join(self.htmlBuilderOutputPath + self._filePath[len(self.htmlBuilderRootPath):])
                
                    # See if htmlPath + self.htmlBuilderExtension exists. If so, use that.
                    htmlFile = htmlPath + self.htmlBuilderExtension
                    if os.path.exists(htmlFile):
                        return u'', errString, QUrl.fromLocalFile(htmlFile)
                
                # Otherwise, try replacing the extension with self.htmlBuilderExtension.
                # TODO
                
            # Can't find it.
            return 'No preview for this type of file in ' + htmlFile, None, QUrl()

    def _convertMarkdown(self, text):
        """Convert Markdown to HTML
        """
        try:
            import markdown
        except ImportError:
            return 'Markdown preview requires <i>python-markdown</i> package<br/>' \
                   'Install it with your package manager or see ' \
                   '<a href="http://packages.python.org/Markdown/install.html">installation instructions</a>'

        try:
            import mdx_mathjax
        except ImportError:
            pass  #mathjax doesn't require import statement if installed as extension

        extensions = ['fenced_code', 'nl2br']

        # version 2.0 supports only extension names, not instances
        if markdown.version_info[0] > 2 or \
           (markdown.version_info[0] == 2 and markdown.version_info[1] > 0):

            class _StrikeThroughExtension(markdown.Extension):
                """http://achinghead.com/python-markdown-adding-insert-delete.html
                Class is placed here, because depends on imported markdown, and markdown import is lazy
                """
                DEL_RE = r'(~~)(.*?)~~'
                def extendMarkdown(self, md, md_globals):
                    # Create the del pattern
                    delTag = markdown.inlinepatterns.SimpleTagPattern(self.DEL_RE, 'del')
                    # Insert del pattern into markdown parser
                    md.inlinePatterns.add('del', delTag, '>not_strong')

            extensions.append(_StrikeThroughExtension())

        try:
            return markdown.markdown(text,  extensions + ['mathjax'])
        except (ImportError, ValueError):  # markdown raises ValueError or ImportError, depends on version
                                           # it is not clear, how to distinguish missing mathjax from other errors
            return markdown.markdown(text, extensions) #keep going without mathjax

    def _convertReST(self, text):
        """Convert ReST
        """
        try:
            import docutils.core
        except ImportError:
            return 'Restructured Text preview requires <i>python-docutils</i> package<br/>' \
                   'Install it with your package manager or see ' \
                   '<a href="http://pypi.python.org/pypi/docutils"/>this page</a>', None

        errStream = StringIO.StringIO()
        htmlString = docutils.core.publish_string(text, writer_name='html', settings_overrides={
                     # Make sure to use Unicode everywhere.
                     'output_encoding': 'unicode',
                     'input_encoding' : 'unicode',
                     # Don't stop processing, no matter what.
                     'halt_level'     : 5,
                     # Capture errors to a string and return it.
                     'warning_stream' : errStream})
        errString = errStream.getvalue()
        errStream.close()
        return htmlString, errString

    def _runHtmlBuilder(self):
        if hasattr(subprocess, 'STARTUPINFO'):  # windows only
            # On Windows, subprocess will pop up a command window by default when run from
            # Pyinstaller with the --noconsole option. Avoid this distraction.
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            # Windows doesn't search the path by default. Pass it an environment so it will.
            env = os.environ
        else:
            si = None
            env = None
    
        try:
            # On Windows, running this from the binary produced by Pyinstller
            # with the ``--noconsole`` option requires redirecting everything
            # (stdin, stdout, stderr) to avoid a OSError exception
            # "[Error 6] the handle is invalid."
            popen = subprocess.Popen(self.htmlBuilderCommandLine,
                      cwd=self.htmlBuilderRootPath,
                      stdin=subprocess.PIPE,
                      stderr=subprocess.PIPE,
                      stdout=subprocess.PIPE,
                      startupinfo=si, env=env)
        except Exception as ex:
            print 'Failed to execute HTML builder console utility "{}": {}\n'\
                        .format(self.htmlBuilderExecutable, str(ex)) + \
                   'Go to Settings -> Settings -> Navigator to set path to HTML builder'

        stdout, stderr = popen.communicate()
        print(stdout)
        print(stderr)

    def run(self):
        """Thread function
        """
        while True:  # exits with break
            # wait task
            task = self._queue.get()
            # take the last task
            while self._queue.qsize():
                task = self._queue.get()

            if task is None:  # None is a quit command
                break

            try:
                html, errString, url = self._getHtml(task.language, task.text, task.filePath)
            except Exception:
                traceback.print_exc()

            if not self._queue.qsize():  # Do not emit results, if having new task
                self.htmlReady.emit(task.filePath, html, errString, url)


class PreviewDock(DockWidget):
    """GUI and implementation
    """
    closed = pyqtSignal()

    def __init__(self):
        DockWidget.__init__(self, core.mainWindow(), "Previe&w", QIcon(':/enkiicons/internet.png'), "Alt+W")
        self._widget = QWidget(self)

        uic.loadUi(os.path.join(os.path.dirname(__file__), 'Preview.ui'), self._widget)

        self._loadTemplates()

        self._widget.webView.page().setLinkDelegationPolicy(QWebPage.DelegateAllLinks)
        self._widget.webView.page().linkClicked.connect(self._onLinkClicked)

        self._widget.webView.page().mainFrame().titleChanged.connect(self._updateTitle)
        self.setWidget(self._widget)
        self.setFocusProxy(self._widget.webView )

        self._widget.cbEnableJavascript.clicked.connect(self._onJavaScriptEnabledCheckbox)

        core.workspace().currentDocumentChanged.connect(self._onDocumentChanged)
        core.workspace().textChanged.connect(self._onTextChanged)

        self._scrollPos = {}
        self._vAtEnd = {}
        self._hAtEnd = {}

        self._thread = ConverterThread()
        self._thread.htmlReady.connect(self._setHtml)

        self._visiblePath = None

        # If we update Preview on every key pressing, freezes are sensible (GUI thread draws preview too slowly
        # This timer is used for drawing Preview 300 ms After user has stopped typing text
        self._typingTimer = QTimer()
        self._typingTimer.setInterval(300)
        self._typingTimer.timeout.connect(self._scheduleDocumentProcessing)

        self._widget.cbTemplate.currentIndexChanged.connect(self._onCurrentTemplateChanged)

        self._scheduleDocumentProcessing()
        self._applyJavaScriptEnabled(self._isJavaScriptEnabled())

        self._widget.tbSave.clicked.connect(self.onSave)

        self.previewSync = PreviewSync(self._widget.webView)

    def del_(self):
        """Uninstall themselves
        """
        self.previewSync.del_()
        self._typingTimer.stop()
        self._thread.htmlReady.disconnect(self._setHtml)
        self._thread.stop_async()
        self._thread.wait()

    def closeEvent(self, event):
        """Widget is closed. Clear it
        """
        self.closed.emit()
        self._clear()
        return DockWidget.closeEvent(self, event)

    def _onLinkClicked(self, url):
        res = QDesktopServices.openUrl(url)
        if res:
            core.mainWindow().statusBar().showMessage("{} opened in a browser".format(url.toString()), 2000)
        else:
            core.mainWindow().statusBar().showMessage("Failed to open {}".format(url.toString()), 2000)

    def _updateTitle(self, pageTitle):
        """Web page title changed. Update own title
        """
        if pageTitle:
            self.setWindowTitle("Previe&w - " + pageTitle)
        else:
            self.setWindowTitle("Previe&w")

    def _saveScrollPos(self):
        """Save scroll bar position for document
        """
        frame = self._widget.webView .page().mainFrame()
        if frame.contentsSize() == QSize(0, 0):
            return # no valida data, nothing to save

        pos = frame.scrollPosition()
        self._scrollPos[self._visiblePath] = pos
        self._hAtEnd[self._visiblePath] = frame.scrollBarMaximum(Qt.Horizontal) == pos.x()
        self._vAtEnd[self._visiblePath] = frame.scrollBarMaximum(Qt.Vertical) == pos.y()

    def _restoreScrollPos(self, ok):
        """Restore scroll bar position for document
        """
        if core.workspace().currentDocument() is None:
            return  # nothing to restore if don't have document

        try:
            self._widget.webView .page().mainFrame().loadFinished.disconnect(self._restoreScrollPos)
        except TypeError:  # already has been disconnected
            pass

        if not self._visiblePath in self._scrollPos:
            return  # no data for this document

        frame = self._widget.webView .page().mainFrame()

        frame.setScrollPosition(self._scrollPos[self._visiblePath])

        if self._hAtEnd[self._visiblePath]:
            frame.setScrollBarValue(Qt.Horizontal, frame.scrollBarMaximum(Qt.Horizontal))

        if self._vAtEnd[self._visiblePath]:
            frame.setScrollBarValue(Qt.Vertical, frame.scrollBarMaximum(Qt.Vertical))

        # Re-sync the re-loaded text.
        self.previewSync.syncTextToPreview()

    def _onDocumentChanged(self, old, new):
        """Current document changed, update preview
        """
        self._typingTimer.stop()
        if new is not None:
            if new.qutepart.language() == 'Markdown':
                self._widget.cbTemplate.show()
                self._widget.lTemplate.show()
            else:
                self._widget.cbTemplate.hide()
                self._widget.lTemplate.hide()

        if new is not None and core.config()['Preview']['Enabled']:
            self._scheduleDocumentProcessing()
        else:
            self._clear()

    _CUSTOM_TEMPLATE_PATH = '<custom template>'
    def _loadTemplates(self):
        for path in [os.path.join(os.path.dirname(__file__), 'templates'),
                     os.path.expanduser('~/.enki/markdown-templates')]:
            if os.path.isdir(path):
                for fileName in os.listdir(path):
                    fullPath = os.path.join(path, fileName)
                    if os.path.isfile(fullPath):
                        self._widget.cbTemplate.addItem(fileName, fullPath)

        self._widget.cbTemplate.addItem('Custom...', self._CUSTOM_TEMPLATE_PATH)

        self._restorePreviousTemplate()

    def _restorePreviousTemplate(self):
        # restore previous template
        index = self._widget.cbTemplate.findText(core.config()['Preview']['Template'])
        if index != -1:
            self._widget.cbTemplate.setCurrentIndex(index)

    def _getCurrentTemplatePath(self):
        index = self._widget.cbTemplate.currentIndex()
        if index == -1:  # empty combo
            return ''

        return unicode(self._widget.cbTemplate.itemData(index))

    def _getCurrentTemplate(self):
        path = self._getCurrentTemplatePath()
        if not path:
            return ''

        try:
            with open(path) as file:
                text = file.read()
        except Exception as ex:
            text = 'Failed to load template {}: {}'.format(path, ex)
            core.mainWindow().statusBar().showMessage(text)
            return ''
        else:
            return text

    def _onCurrentTemplateChanged(self):
        """Update text or show message to the user"""
        if self._getCurrentTemplatePath() == self._CUSTOM_TEMPLATE_PATH:
            QMessageBox.information(core.mainWindow(),
                                   'Custom templaes help',
                                   '<html>See <a href="https://github.com/hlamer/enki/wiki/Markdown-preview-templates">'
                                   'this</a> wiki page for information about custom templates')
            self._restorePreviousTemplate()

        core.config()['Preview']['Template'] = self._widget.cbTemplate.currentText()
        core.config().flush()
        self._scheduleDocumentProcessing()

    def _onTextChanged(self, document):
        """Text changed, update preview
        """
        if core.config()['Preview']['Enabled']:
            self._typingTimer.stop()
            self._typingTimer.start()

    def show(self):
        """When shown, update document, if posible
        """
        DockWidget.show(self)
        self._scheduleDocumentProcessing()

    def _scheduleDocumentProcessing(self):
        """Start document processing with the thread.
        """
        self._typingTimer.stop()

        document = core.workspace().currentDocument()
        if document is not None:
            qp = document.qutepart
            language = qp.language()
            text = qp.text
            if isMarkdownFile(document):
                language = 'Markdown'
                text = self._getCurrentTemplate() + text
            elif isHtmlFile(document):
                language = 'HTML'
            elif language == 'reStructuredText':
                pass
            else:
                # Save any changes before HTML builder processing.
                if qp.document().isModified():
                    document.saveFile()
            self._setHtmlProgress(-1)
            # for rest language is already correct
            self._thread.process(document.filePath(), language, text)

    def _setHtml(self, filePath, html, errString=None, baseUrl):
        """Set HTML to the view and restore scroll bars position.
        Called by the thread
        """
        self._saveScrollPos()
        self._visiblePath = filePath
        self._widget.webView.page().mainFrame().loadFinished.connect(self._restoreScrollPos)
        if baseUrl.isEmpty():
            self._widget.webView.setHtml(html, baseUrl=QUrl.fromLocalFile(filePath))
        else:
            self._widget.webView.setUrl(baseUrl)
        self._widget.teLog.clear()
        self._setHtmlProgress(-1)
        if errString:
            # This code parses the error string to determine get the number of
            # warnings and errors. A common error message reads::
            #
            #  <string>:1589: (ERROR/3) Unknown interpreted text role "ref".
            #
            # Each error/warning occupies one line. The following `regular
            # expression
            # <https://docs.python.org/2/library/re.html#regular-expression-syntax>`_
            # is designed to find the error position (1589) and message
            # type (ERROR). Extra spaces are added to show which parts of the
            # example string it matches::
            #
            #  ^<\w+>  :(\d+): \s\((\w+)/\d+\)
            #  <string>:1589: (ERROR/3)         Unknown interpreted text role "ref".
            #
            # Examining this expression one element at a time:
            #
            # ``^<\w+>``: From the start of a line, match a pair of angle
            # brackets similar to <string>.
            #
            # ``:(\d+):\s``: next match a pair of colons with number in
            # it, follwed by a single space. Place the number in a group. For
            # example, this pattern matches the stirng ":1589: ". The syntax
            # ``\s`` denotes a trailing space.
            #
            # ``\((\w+)/\d+\)``: next match a pair of parentheses which contain
            # a word followed by a forward slash ``/`` followed by a number.
            # For example, this expression matches the string "(ERROR/3)".
            #
            # For more details about python regular expressions, refer to the
            # `re docs <https://docs.python.org/2/library/re.html>`_.
            regex = re.compile("^<\w+>:(\d+):\s\((\w+)/\d+\)",
                               re.MULTILINE)
            result = regex.findall(errString)
            # The variable ``result`` now contains a list of tuples, where each
            # tuples contains the two matches groups (line number, error_string).
            # For example::
            #
            #  [('1589', 'ERROR')]
            #
            # Therefeore, the second element of each tuple, represented as x[1],
            # is the error_string. The next two lines of code will collect all
            # ERRORs and WARNINGs found in the error_string separately.
            errNum = len(filter(lambda x: 'ERROR' in x[1], result))
            warningNum = len(filter(lambda x: 'WARNING' in x[1], result))
            # Report these results this to the user.
            status = 'Warning(s): ' + str(warningNum) + ' Error(s): ' + str(errNum)
            self._widget.teLog.appendPlainText(errString + '\n' + status)
            # Update the progress bar.
            color = 'red' if errNum else 'yellow'
            self._setHtmlProgress(100, color)
        else:
            self._setHtmlProgress(100)

    def _setHtmlProgress(self, progress=None, color=None):
        """Set progress bar and status label.
        if progress is -1: use an indefinite progress bar
        if progress is 0: stop progress bar
        if progress is anyvalue between 0 and 100: display progress bar
        """
        if color:
            style = 'QProgressBar::chunk {\nbackground-color: '+color+'\n}'
        else:
            style = 'QProgressBar::chunk {}'
        self._widget.prgStatus.setStyleSheet(style)
        if progress == -1:
            self._widget.prgStatus.setRange(0, 0)
        elif progress == 0 or not progress:
            self._widget.prgStatus.reset()
        else:
            assert progress >= 0 and progress <= 100
            self._widget.prgStatus.setRange(0, 100)
            self._widget.prgStatus.setValue(progress)

    def _clear(self):
        """Clear themselves.
        Might be necesssary for stop executing JS and loading data
        """
        self._setHtml('', '', QUrl())

    def _isJavaScriptEnabled(self):
        """Check if JS is enabled in the settings
        """
        return core.config()['Preview']['JavaScriptEnabled']

    def _onJavaScriptEnabledCheckbox(self, enabled):
        """Checkbox clicked, save and apply settings
        """
        core.config()['Preview']['JavaScriptEnabled'] = enabled;
        core.config().flush()

        self._applyJavaScriptEnabled(enabled)

    def _applyJavaScriptEnabled(self, enabled):
        """Update QWebView settings and QCheckBox state
        """
        self._widget.cbEnableJavascript.setChecked(enabled)

        settings = self._widget.webView.settings()
        settings.setAttribute(settings.JavascriptEnabled, enabled)

        self._scheduleDocumentProcessing()

    def onSave(self):
        """Save contents of the preview"""
        path = QFileDialog.getSaveFileName(self, 'Save Preview as HTML', filter='HTML (*.html)')
        if path:
            text = self._widget.webView.page().mainFrame().toHtml()
            data = text.encode('utf8')
            try:
                with open(path, 'w') as openedFile:
                    openedFile.write(data)
            except (OSError, IOError) as ex:
                    QMessageBox.critical(self, "Failed to save HTML", unicode(str(ex), 'utf8'))
