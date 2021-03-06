#!/usr/bin/env python
import unittest


# Import just to check that dependencies are installed
import markdown
import docutils
import mock


if __name__ == "__main__":
    # Look for all tests. Using test_* instead of test_*.py finds modules (test_syntax and test_indenter).
    suite = unittest.TestLoader().discover('.', pattern = "test_*")
    unittest.TextTestRunner(verbosity=2).run(suite)
