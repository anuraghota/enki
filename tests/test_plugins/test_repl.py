#!/usr/bin/env python

import unittest
import os.path
import sys
import time

sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), ".."))

import base

from PyQt4.QtCore import Qt, QTimer
from PyQt4.QtTest import QTest

from enki.core.core import core


class Test(base.TestCase):

    def _browserText(self, replName):
        term = self.findDock(replName + ' &Interpreter').widget()
        return term._browser.toPlainText()

    def _waitForText(self, text, replName):
        for i in range(50):
            if text in self._browserText(replName):
                break
            else:
                self.sleepProcessEvents(0.1)
        else:
            self.fail("Text doesn't contain '{}'".format(text))

    @base.requiresCmdlineUtility('scheme')
    @base.inMainLoop
    def test_1(self):
        # Scheme
        return # TODO
        self.createFile('test.scm', '(+ 17 10)')
        self.keyClick('Ctrl+E')
        self._waitForText('27', 'MIT Scheme')

    @base.requiresCmdlineUtility('sml -h')
    @base.inMainLoop
    def test_2(self):
        # SML
        self.createFile('test.sml', '1234 * 567;')
        self.keyClick('Ctrl+E')

        self._waitForText('699678', 'Standard ML')

    @base.requiresCmdlineUtility('python -h')
    @base.inMainLoop
    def test_3(self):
        # Python
        self.createFile('test.py', 'print 1234 * 567\n')
        self.keyClick('Ctrl+E')

        self._waitForText('699678', 'Python')


if __name__ == '__main__':
    unittest.main()
