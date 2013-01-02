"""
Run all tests in this module.
"""

import os
import sys
import unittest

unittest.main(argv=sys.argv[:1] + ['discover', '-s',
        __package__.replace('.', os.path.sep)] + sys.argv[1:])
