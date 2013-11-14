#!/usr/bin/env python

import unittest
import os.path
import sys

sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), ".."))
import base

from PyQt4.QtTest import QTest
from PyQt4.QtGui import QDockWidget

from enki.core.core import core


class Test(base.TestCase):
    def _widget(self):
        for dock in core.mainWindow().findChildren(QDockWidget):
            if dock.windowTitle().startswith('&Preview'):
                return dock.widget()
        else:
            self.fail('Preview dock not found')

    def _showDock(self):
        core.actionManager().action('mView/aPreview').trigger()

    def _visibleText(self):
        return self._widget().webView.page().mainFrame().toPlainText()

    def _html(self):
        return self._widget().webView.page().mainFrame().toHtml()

    def _do_basic_test(self, extension):
        text = 'The preview text'
        document = self.createFile('file.' + extension, text)
        
        self._showDock()
        QTest.qWait(500)
        self.assertTrue(text in self._visibleText())

    def test_html(self):
        self._do_basic_test('html')

    def test_rst(self):
        self._do_basic_test('rst')

    def test_markdown(self):
        self._do_basic_test('md')
    
    def test_markdown_templates(self):
        core.config()['Preview']['Template'] = 'WhiteOnBlack'
        document = self.createFile('test.md', 'foo')
        self._showDock()
        
        combo = self._widget().cbTemplate
        
        QTest.qWait(500)
        self.assertEqual(combo.currentText(), 'WhiteOnBlack')
        self.assertFalse('body {color: white; background: black;}' in self._visibleText())
        self.assertTrue('body {color: white; background: black;}' in self._html())
        
        combo.setCurrentIndex(combo.findText('MathJax'))
        QTest.qWait(500)
        self.assertFalse('http://cdn.mathjax.org/mathjax/latest/MathJax.js' in self._visibleText())
        self.assertTrue('http://cdn.mathjax.org/mathjax/latest/MathJax.js' in self._html())
        self.assertEqual(core.config()['Preview']['Template'], 'MathJax')

        combo = self._widget().cbTemplate
        combo.setCurrentIndex(combo.findText('Default'))
        QTest.qWait(500)
        self.assertFalse('http://cdn.mathjax.org/mathjax/latest/MathJax.js' in self._visibleText())
        self.assertFalse('http://cdn.mathjax.org/mathjax/latest/MathJax.js' in self._html())
        self.assertEqual(core.config()['Preview']['Template'], 'Default')

    def test_markdown_templates_help(self):
        core.config()['Preview']['Template'] = 'WhiteOnBlack'
        document = self.createFile('test.md', 'foo')
        self._showDock()
        
        combo = self._widget().cbTemplate

        def inDialog(dialog):
            self.assertEqual(dialog.windowTitle(), 'Custom templaes help')
            dialog.accept()
        
        self.openDialog(lambda: combo.setCurrentIndex(combo.count() - 1), inDialog)

if __name__ == '__main__':
    unittest.main()